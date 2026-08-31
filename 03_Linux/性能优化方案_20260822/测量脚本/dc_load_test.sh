#!/bin/bash
# =============================================================================
# dc_load_test.sh — DC(离电)满载渐进式安全测试
# =============================================================================
# ⚠️ 本测试触及项目红线(DC 满载, 历史 5 死机 4 在 DC), 故设计为渐进式 + 可定位。
#
# 安全网(已验证):
#   1. undervolt.service 为 oneshot 且写死 -50mV → 死机重启后自动应用安全值,
#      不会卡在测试值。**前提: 测试期间不得持久化 -80mV。**
#   2. kernel.panic=10 (仅对 kernel panic 有效)
#   3. rasdaemon active (MCE 落盘; 硬死机时通常来不及)
#   4. pstore 不写盘 → 硬死机无转储, 靠本脚本的进度文件定位
#
# 渐进式(避免一上来就 8 线程满载):
#   L1 = 2 核 → L2 = 4 核 → L3 = 8 核(标准满载)
#   任一级死机即中止(重启后不再继续), 由进度文件记录死在哪一级。
#
# 用法:
#   PW_FILE=/tmp/.uvpw bash dc_load_test.sh 80      # 测 -80mV
#   PW_FILE=/tmp/.uvpw bash dc_load_test.sh 50      # 先测日常值 -50mV 作对照
#   不带参数 = 检查上次是否死机并报告(重启后运行)
# =============================================================================

set -u

SAFE_MV=50
TEMP_TARGET=98
PW_FILE="${PW_FILE:-/tmp/.uvpw}"
# 全部路径用相对定位(2026-08-30 修正): 原硬编码 /media/<USER>/WS1/... ,
# 数据盘挂载点会在 WS/WS1 间变化(udisks2 重名加序号), 硬编码必然失效。
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTDIR="$(dirname "$SCRIPT_DIR")/sweep_data"
PROG="$OUTDIR/.dc_load_progress"
ACF=/sys/class/power_supply/ACAD/online
BENCH="$SCRIPT_DIR/bench"
CUR_BOOT=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | cut -c1-13)

srun() { sudo -S -p '' "$@" 2>/dev/null < "$PW_FILE"; }
uv_core() { srun undervolt --read 2>/dev/null | awk '/^core:/{print $2}'; }
mce_cnt() { dmesg 2>/dev/null | grep -ciE "mce|machine check"; }
pkg_temp() { sensors 2>/dev/null | awk '/^Package/{print $4}' | tr -d '+°C' | head -1; }
ac_state() { [ "$(cat "$ACF" 2>/dev/null)" = "1" ] && echo AC || echo DC; }
batt() { cat /sys/class/power_supply/BAT1/capacity 2>/dev/null; }
now() { date '+%H:%M:%S'; }

# ---------- 模式: 无参数 = 死机检查 ----------
if [ $# -eq 0 ]; then
    echo "=== DC 满载测试 · 死机检查 ==="
    if [ ! -f "$PROG" ]; then
        echo "✅ 无未完成的测试记录（上次测试正常结束，或从未运行）"
        echo "   当前降压: $(uv_core 2>/dev/null || echo '需root')"
        exit 0
    fi
    . "$PROG"
    echo "发现未完成的测试记录："
    echo "  测试值:    -${MV}mV"
    echo "  死机时级:  ${STAGE:-未知} ($(case "${STAGE:-}" in L1) echo '2核'; echo;; L2) echo '4核';; L3) echo '8核满载';; *) echo '未开始加载';; esac))"
    echo "  记录时间:  ${TS:-未知}"
    echo "  记录boot:  ${BOOT:-未知}"
    echo "  当前boot:  $CUR_BOOT"
    if [ "${BOOT:-x}" != "$CUR_BOOT" ]; then
        echo ""
        echo "🔴 boot id 不同 → 系统在测试期间【重启过】，判定为死机"
        echo "   死机发生在: $STAGE 阶段"
        echo ""
        echo "【归因指引】"
        if [ "$MV" = "50" ]; then
            echo "   测试值是日常值 -50mV → 死机与 -80mV 无关，属【DC 满载本身】的风险。"
            echo "   → 说明日常配置在 DC 满载下即不安全，应立即停止测试，维持红线。"
        else
            echo "   测试值 -${MV}mV。若此前 -50mV 同级通过，则问题出在降压深度；"
            echo "   若 -50mV 未测，请先跑 -50mV 对照以区分归因。"
            echo "   → 结论: 不应持久化 -${MV}mV"
        fi
    else
        echo "⚠️ boot id 相同，但测试标记未完成 → 可能上次被中断(Ctrl+C)而非死机"
    fi
    echo ""
    echo "当前降压: $(uv_core 2>/dev/null || echo '需root')"
    exit 0
fi

# ---------- 参数校验 ----------
UV_MV="${1:?需要降压值}"
case "$UV_MV" in ''|*[!0-9]*) echo "❌ 需正整数"; exit 1;; esac
[ -f "$PW_FILE" ] || { echo "❌ 缺少密码文件"; exit 1; }
[ -f "$BENCH" ] || { echo "❌ 找不到 bench"; exit 1; }
[ "$(ac_state)" = "AC" ] || { echo "❌ 请在 AC 下启动，脚本会等待你拔电"; exit 1; }

# ---------- 安全网确认 ----------
SVC_MV=$(grep -o -- '--core [-0-9]*' /etc/systemd/system/undervolt.service 2>/dev/null | awk '{print $2}')
echo "=== DC 满载渐进测试 (目标 -${UV_MV}mV) ==="
echo "安全网检查:"
echo "  undervolt.service 值: ${SVC_MV:-未找到} $([ "$SVC_MV" = "-$SAFE_MV" ] && echo '✅ 安全值(重启后自动恢复)' || echo '⚠️ 非安全值! 建议先改回 -50')"
echo "  kernel.panic: $(sysctl -n kernel.panic 2>/dev/null)"
echo "  电池: $(batt)%  温度: $(pkg_temp)°C  MCE: $(mce_cnt)"
echo ""
[ "$SVC_MV" = "-$SAFE_MV" ] || { echo "❌ 安全网未就位(服务值非 -${SAFE_MV}mV), 拒绝执行"; exit 1; }

# 进度标记: 进入加载前先写(便于定位)
write_prog() {
    cat > "$PROG" << EOF
MV=$UV_MV
STAGE=$1
BOOT=$CUR_BOOT
TS=$(now)
EOF
    sync
}
cleanup() {
    echo ""
    echo ">>> 恢复安全值 -${SAFE_MV}mV <<<"
    srun undervolt --core "-$SAFE_MV" --cache "-$SAFE_MV" --gpu "-$SAFE_MV" --temp "$TEMP_TARGET"
    sleep 1
    echo "  实测: $(uv_core)mV"
    rm -f "$PROG" 2>/dev/null
    rm -f "$PW_FILE" 2>/dev/null
    echo "  进度标记已清除（= 正常结束）"
    exit 0
}
trap cleanup INT TERM EXIT

# ---------- 等待拔电 ----------
echo "--- 请【拔掉电源】(最多 180s) ---"
write_prog "WAIT_DC"
T0=$(date +%s)
while [ "$(ac_state)" = "AC" ]; do
    [ $(( $(date +%s) - T0 )) -gt 180 ] && { echo "⏱ 超时"; exit 0; }
    sleep 1
done
echo "  ✓ 已拔电 $(now), 电池 $(batt)%"

# ---------- 应用测试值 ----------
echo ""
echo "--- 应用 -${UV_MV}mV ---"
write_prog "APPLY"
if ! srun undervolt --core "-$UV_MV" --cache "-$UV_MV" --gpu "-$UV_MV" --temp "$TEMP_TARGET"; then
    echo "❌ apply 失败"; exit 1
fi
sleep 1
echo "  实测: $(uv_core)mV  MCE=$(mce_cnt)  温度=$(pkg_temp)°C"

# ---------- 渐进加载 ----------
echo ""
echo "--- 渐进加载（L1=2核 → L2=4核 → L3=8核）---"

run_stage() {
    local tag="$1" cores="$2"
    write_prog "$tag"
    local t0 m0
    t0=$(pkg_temp); m0=$(mce_cnt)
    echo "  [$tag] $(now) 启动 (CPU $cores) 起温=${t0}°C 电池=$(batt)%"
    taskset -c "$cores" "$BENCH" > /tmp/.dc_bench_$tag.txt 2>&1
    local rc=$?
    sleep 2
    local res iters kps
    res=$(awk '/^total=/{sub("total=","");print}' /tmp/.dc_bench_$tag.txt 2>/dev/null)
    iters=${res:-0}
    kps=$(awk "BEGIN{printf \"%.1f\", ${iters}/20/10000}")
    echo "  [$tag] $(now) 完成 rc=$rc 吞吐=${kps}万/s 温度=$(pkg_temp)°C MCE+$(($(mce_cnt)-m0)) 电池=$(batt)%"
    if [ $(( $(mce_cnt) - m0 )) -gt 0 ]; then
        echo "  ⚠️ 检测到 MCE 增量，中止后续级别"; return 1
    fi
    [ "$(ac_state)" = "DC" ] || echo "  ⚠️ 供电变为 AC"
    # 级间冷却 45s（DC 下温度低，但保险起见）
    [ "$tag" != "L3" ] && { echo "     冷却 45s..."; sleep 45; }
    return 0
}

run_stage L1 "0,1"      || exit 0
run_stage L2 "0-3"      || exit 0
run_stage L3 "0-7"      || exit 0

echo ""
echo "✅ 全部三级通过（DC 满载 -${UV_MV}mV）"
echo "   MCE 总计: $(mce_cnt)"
echo ""
echo "--- 请【插回电源】---"
T0=$(date +%s)
while [ "$(ac_state)" = "DC" ]; do
    [ $(( $(date +%s) - T0 )) -gt 180 ] && { echo "⏱ 超时(将恢复安全值)"; exit 0; }
    sleep 1
done
echo "  ✓ 已插电，恢复安全值"
