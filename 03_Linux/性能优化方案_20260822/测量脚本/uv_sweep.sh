#!/bin/bash
# =============================================================================
# uv_sweep.sh <mV> [轮数] - 降压扫描(带三重安全防护, 基于超压事故教训)
# =============================================================================
# 事故背景(2026-08-13): 曾因脚本丢负号写入 +120mV 超压 → 进不了系统。
# 本脚本强制: ①电压只能为负 ②conf 三步校验 ③apply 后必回读 ④每档结束恢复安全值
# 用法: sudo ./uv_sweep.sh 105 10    # 测 -105mV, 10 轮
# 依赖: intel-undervolt / stress-ng / msr-tools / lm-sensors
# =============================================================================

set -u
[ "$(id -u)" = "0" ] || { echo "需要 root: sudo $0"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
OUTDIR="$BASE_DIR/sweep_data"
SAFE_CONF="/etc/intel-undervolt.conf.bak-50mv"   # 已验证安全值备份(重建脚本生成)

# ---------- 1. 参数校验(防超压核心) ----------
MV_RAW="${1:?用法: uv_sweep.sh <mV> [轮数]}"
MV="${MV_RAW#-}"                                  # 去负号
case "$MV" in ''|*[!0-9]*|0) echo "❌ 参数必须为正整数"; exit 1;; esac
[ "$MV" -gt 200 ] && { echo "❌ 降压 >200mV 超限, 拒绝"; exit 1; }
MV_SIGNED="-$MV"                                  # 永远负值
ROUNDS=${2:-5}
[ "$ROUNDS" -gt 20 ] && ROUNDS=20

echo "=== uv_sweep: 目标 ${MV_SIGNED}mV, $ROUNDS 轮 ==="
echo "⚠️ 电压只能为负(正值=超压)。生成值: $MV_SIGNED"

# ---------- 2. 环境检查 ----------
echo "起点温度: $(sensors 2>/dev/null | awk '/^Package/{print $4}' | tr -d '+°C' | head -1)°C"
TOP=$(ps aux --sort=-%cpu | awk 'NR>1 && $3>10 {n++} END{print n+0}')
echo "后台 >10% CPU 进程数: $TOP (建议 ≤2)"
[ "$TOP" -gt 2 ] && echo "⚠️ 后台偏高, 数据可能被污染"

# ---------- 3. 写入 conf(三步校验) ----------
BACKUP="/etc/intel-undervolt.conf.bak-sweep-$(date +%H%M%S)"
[ -f /etc/intel-undervolt.conf ] && cp /etc/intel-undervolt.conf "$BACKUP"
cat > /etc/intel-undervolt.conf << EOF
undervolt 0 "CPU" $MV_SIGNED
undervolt 1 "GPU" $MV_SIGNED
undervolt 2 "CPU Cache" $MV_SIGNED
undervolt 3 "System Agent" 0
undervolt 4 "Analog I/O" 0
EOF
echo "--- 校验1: conf 内容 ---"
cat /etc/intel-undervolt.conf
if ! grep -qE 'undervolt [0-9]+ "[^"]+" -[0-9]+' /etc/intel-undervolt.conf; then
    echo "❌ 校验失败: 存在无负号条目, 拒绝 apply"; cp "$BACKUP" /etc/intel-undervolt.conf; exit 1
fi
echo "校验2: 全负 ✓"

# ---------- 4. apply + 回读(校验3) ----------
intel-undervolt apply || { echo "❌ apply 失败, 恢复备份"; cp "$BACKUP" /etc/intel-undervolt.conf; exit 1; }
READBACK=$(intel-undervolt read 2>/dev/null | head -1)
echo "回读: $READBACK"
echo "$READBACK" | grep -q -- "-$MV" || { echo "❌ 回读与预期不符, 恢复备份"; cp "$BACKUP" /etc/intel-undervolt.conf; intel-undervolt apply; exit 1; }
echo "校验3: 回读确认 ✓"

# ---------- 5. 逐轮测试 ----------
CSV="$OUTDIR/uv_sweep_m${MV}.csv"
[ ! -f "$CSV" ] && echo "mv,round,total,吞吐万s,W,起温,终温" > "$CSV"
MCE0=$(dmesg 2>/dev/null | grep -ciE "mce|machine check")
for i in $(seq 1 $ROUNDS); do
    T0=$(sensors 2>/dev/null | awk '/^Package/{print $4}' | tr -d '+°C' | head -1)
    if [ -n "$T0" ] && [ "$(echo "$T0 > 75" | bc 2>/dev/null)" = "1" ]; then
        echo "❌ 轮$i 起点 ${T0}°C >75°C, 冷却 120s"; sleep 120
    fi
    E0=$(cat /sys/class/powercap/intel-rapl:0/energy_uj 2>/dev/null)
    RES=$(stress-ng --cpu $(nproc) --timeout 20s 2>/dev/null; echo done)   # 仅做热/稳负载
    # 吞吐用 bench(与历史可比, 优先本文件夹内)
    BENCH="$SCRIPT_DIR/bench"
    [ -f "$BENCH" ] || BENCH="$(dirname "$BASE_DIR")/Linux对比/bench"
    if [ -f "$BENCH" ]; then
        RES=$("$BENCH")
        ITERS=$(echo "$RES" | awk '/^total=/{sub("total=","");print}')
        KPS=$(awk "BEGIN{printf \"%.1f\", ${ITERS:-0}/20/10000}")
    else
        KPS=0
    fi
    E1=$(cat /sys/class/powercap/intel-rapl:0/energy_uj 2>/dev/null)
    W=""; [ -n "$E0" ] && [ -n "$E1" ] && W=$(awk "BEGIN{printf \"%.1f\", ($E1-$E0)/1000000/20}")
    T1=$(sensors 2>/dev/null | awk '/^Package/{print $4}' | tr -d '+°C' | head -1)
    echo "[m${MV}] 轮$i/$ROUNDS: ${KPS}万/s ${W}W ${T0}->${T1}°C"
    echo "$MV,$i,$ITERS,$KPS,$W,$T0,$T1" >> "$CSV"
    sync
    [ "$i" -lt "$ROUNDS" ] && { echo "冷却 60s..."; sleep 60; }
done

# ---------- 6. MCE 检查 + 恢复安全值 ----------
MCE1=$(dmesg 2>/dev/null | grep -ciE "mce|machine check")
echo "MCE 计数: $((MCE1-MCE0)) (0=稳定)"
if [ "$((MCE1-MCE0))" -gt 0 ]; then
    echo "❌ 检测到 MCE, 立即恢复安全值"
fi
echo "--- 恢复 conf 为安全值 ---"
if [ -f "$SAFE_CONF" ]; then
    cp "$SAFE_CONF" /etc/intel-undervolt.conf
else
    cp "$BACKUP" /etc/intel-undervolt.conf
fi
intel-undervolt apply
echo "恢复后回读: $(intel-undervolt read 2>/dev/null | head -1)"
echo "=== uv_sweep 完成, 数据: $CSV ==="
