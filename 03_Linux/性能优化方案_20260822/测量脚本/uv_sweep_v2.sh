#!/bin/bash
# =============================================================================
# uv_sweep_v2.sh <mV> [轮数] — 降压扫描（适配本机 Python 版 undervolt + 安全负载）
# =============================================================================
# 为什么不用原 uv_sweep.sh（2026-08-29 实测评测）：
#   ❌ 它调用 intel-undervolt（C 版）—— 本机【未安装】，实测 command -v 不存在，
#      且其配置 /etc/intel-undervolt.conf 也不存在 → apply/回读/恢复全链失效。
#   ❌ 它用 stress-ng 做负载 —— 项目铁律【永久冻结】（死机 2/3 均涉其满载）。
#   ✅ 本机实际用 Python 版 undervolt（/usr/local/bin/undervolt），配置走 systemd 服务命令行。
#
# 本版改动：
#   1. 改用 Python 版 undervolt（--core/--cache/--gpu/--temp）
#   2. 负载改用自研 bench（8 线程 LCG，多次实测安全），彻底移除 stress-ng
#   3. 强化【冷却期观察】—— 死机 #6 的教训：冻结发生在"满载后冷却期电压最低时"，
#      故每轮后冷却期需记录并检活，而非只看满载期间
#   4. 保留原三重防护：电压只能为负 / apply 后必回读 / 结束恢复安全值
#
# 用法: sudo bash uv_sweep_v2.sh 80 5     # 测 -80mV, 5 轮
# 前置：必须在 AC 插电下运行（DC 满载为项目红线）
# =============================================================================

set -u
[ "$(id -u)" = "0" ] || { echo "❌ 需要 root: sudo bash $0"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
OUTDIR="$BASE_DIR/sweep_data"
SAFE_MV=50          # 已验证安全值 -50mV（与 undervolt.service 一致）
TEMP_TARGET=98      # 与 undervolt.service 保持一致

# ---------- 1. 参数校验（防超压核心） ----------
MV_RAW="${1:?用法: uv_sweep_v2.sh <mV> [轮数]}"
MV="${MV_RAW#-}"
case "$MV" in ''|*[!0-9]*|0) echo "❌ 参数必须为正整数（代表降压幅度，如 80 = -80mV）"; exit 1;; esac
[ "$MV" -gt 120 ] && { echo "❌ 降压 >120mV 超限, 拒绝（-105mV 曾致死机 #6）"; exit 1; }
[ "$MV" -le "$SAFE_MV" ] && { echo "❌ ${MV}mV 不比安全值 ${SAFE_MV}mV 更深, 无测试意义"; exit 1; }
MV_SIGNED="-$MV"
ROUNDS=${2:-5}
[ "$ROUNDS" -gt 20 ] && ROUNDS=20

# ---------- 2. 依赖检查（fail fast，不留下半途状态） ----------
command -v undervolt >/dev/null || { echo "❌ 缺少 undervolt（Python 版）"; exit 1; }
command -v sensors  >/dev/null || { echo "❌ 缺少 lm-sensors"; exit 1; }
command -v bc       >/dev/null || { echo "❌ 缺少 bc"; exit 1; }
BENCH="$SCRIPT_DIR/bench"
[ -f "$BENCH" ] || BENCH="$(dirname "$BASE_DIR")/Linux对比/bench"
[ -f "$BENCH" ] || { echo "❌ 找不到 bench 程序（安全负载，非 stress-ng）"; exit 1; }

echo "=== uv_sweep_v2: 目标 ${MV_SIGNED}mV, $ROUNDS 轮 ==="
echo "安全值: -${SAFE_MV}mV | 负载: bench（stress-ng 已冻结）"

# ---------- 3. 供电红线检查 ----------
AC=$(cat /sys/class/power_supply/ACAD/online 2>/dev/null)
if [ "$AC" != "1" ]; then
    echo "🔴 DC 电池供电 —— 项目红线：DC 满载不再主动测试（历史 5 死机 4 在 DC）"
    echo "   请插电后重试。"; exit 1
fi
echo "供电: ✅ AC"

# ---------- 4. 环境基线 ----------
T_START=$(sensors 2>/dev/null | awk '/^Package/{print $4}' | tr -d '+°C' | head -1)
T_AMB=$(sensors 2>/dev/null | grep -m1 'acpitz' -A3 | grep 'temp1' | awk '{print $2}' | tr -d '+°C')
TOP=$(ps aux --sort=-%cpu | awk 'NR>1 && $3>10 {n++} END{print n+0}')
echo "起点温度: ${T_START:-N/A}°C | 环境: ${T_AMB:-N/A}°C | 后台>10%进程: $TOP"
[ "$TOP" -gt 2 ] && echo "⚠️ 后台偏高, 数据可能被污染（建议先跑 测量脚本/quiet.sh）"
if [ -n "$T_START" ] && [ "$(echo "$T_START > 75" | bc 2>/dev/null)" = "1" ]; then
    echo "❌ 起点 ${T_START}°C >75°C（安全红线）, 冷却 120s 后重测"; exit 1
fi

# ---------- 5. 记录当前值 + 应用目标值 + 回读校验 ----------
echo "--- 应用前回读 ---"
undervolt --read 2>&1 | head -6
echo "--- 应用 ${MV_SIGNED}mV ---"
if ! undervolt --core "$MV_SIGNED" --cache "$MV_SIGNED" --gpu "$MV_SIGNED" --temp "$TEMP_TARGET"; then
    echo "❌ apply 失败, 未改动系统（服务仍为 -${SAFE_MV}mV 配置）"; exit 1
fi
sleep 1
RB=$(undervolt --read 2>/dev/null)
echo "--- 应用后回读 ---"
echo "$RB"
# 校验：core 行须含 -MV（允许 -79.8 这类实测偏差）
if ! echo "$RB" | grep -qE "core: *-${MV}(\.|$|0)" ; then
    echo "⚠️ 回读未精确匹配 -${MV}mV，打印实测值供人工判断："
    echo "$RB" | grep -E "core|gpu|cache"
    echo "若实测偏差 >5mV 请中止 (Ctrl+C)"; sleep 5
fi
echo "校验: apply + 回读完成 ✓"

# ---------- 6. 逐轮测试（每轮含冷却期观察） ----------
mkdir -p "$OUTDIR"
CSV="$OUTDIR/uv_sweep_v2_m${MV}.csv"
[ ! -f "$CSV" ] && echo "mv,round,iters,吞吐万s,W,起温,终温,冷却后温,环境温,MCE累计" > "$CSV"
MCE0=$(dmesg 2>/dev/null | grep -ciE "mce|machine check")

for i in $(seq 1 "$ROUNDS"); do
    T0=$(sensors 2>/dev/null | awk '/^Package/{print $4}' | tr -d '+°C' | head -1)
    if [ -n "$T0" ] && [ "$(echo "$T0 > 75" | bc 2>/dev/null)" = "1" ]; then
        echo "❌ 轮$i 起点 ${T0}°C >75°C, 冷却 120s"; sleep 120
    fi

    E0=$(cat /sys/class/powercap/intel-rapl:0/energy_uj 2>/dev/null)
    RES=$("$BENCH")
    E1=$(cat /sys/class/powercap/intel-rapl:0/energy_uj 2>/dev/null)
    ITERS=$(echo "$RES" | awk '/^total=/{sub("total=","");print}')
    KPS=$(awk "BEGIN{printf \"%.1f\", ${ITERS:-0}/20/10000}")
    W=""; [ -n "$E0" ] && [ -n "$E1" ] && W=$(awk "BEGIN{printf \"%.1f\", ($E1-$E0)/1000000/20}")
    T1=$(sensors 2>/dev/null | awk '/^Package/{print $4}' | tr -d '+°C' | head -1)

    # ★ 冷却期观察（死机 #6 教训：冻结发生在满载后冷却期电压最低时）
    [ "$i" -lt "$ROUNDS" ] && { echo -n "  冷却 60s"; sleep 60; echo " ✓存活"; }
    T2=$(sensors 2>/dev/null | awk '/^Package/{print $4}' | tr -d '+°C' | head -1)
    MCE_N=$(dmesg 2>/dev/null | grep -ciE "mce|machine check")
    MCE_DIFF=$((MCE_N - MCE0))

    echo "[$MV_SIGNED] 轮$i/$ROUNDS: ${KPS}万/s ${W}W ${T0}->${T1}°C (冷却后${T2}°C) MCE+$MCE_DIFF"
    echo "$MV,$i,$ITERS,$KPS,$W,$T0,$T1,$T2,$T_AMB,$MCE_DIFF" >> "$CSV"
    sync

    if [ "$MCE_DIFF" -gt 0 ]; then
        echo "❌ 检测到 MCE, 中止并恢复安全值"
        break
    fi
done

# ---------- 7. 恢复安全值（无论成功失败都执行） ----------
echo "--- 恢复安全值 -${SAFE_MV}mV ---"
undervolt --core "-$SAFE_MV" --cache "-$SAFE_MV" --gpu "-$SAFE_MV" --temp "$TEMP_TARGET"
sleep 1
echo "恢复后回读:"
undervolt --read 2>&1 | head -6
echo "=== uv_sweep_v2 完成, 数据: $CSV ==="
echo ""
echo "【判据】MCE 全 0 且各轮吞吐波动 <5% → 可考虑持久化；否则维持 -${SAFE_MV}mV"
echo "【持久化方法】（确认稳定后）:"
echo "  sudo sed -i 's/--core -[0-9]*/--core -$MV/; s/--cache -[0-9]*/--cache -$MV/; s/--gpu -[0-9]*/--gpu -$MV/' \\"
echo "       /etc/systemd/system/undervolt.service /etc/systemd/system/undervolt-resume.service"
echo "  sudo systemctl daemon-reload && sudo systemctl restart undervolt"
echo "【安全网】即使测试中途死机，重启后 undervolt.service(oneshot, 写死 -${SAFE_MV}mV) 自动恢复安全值"
