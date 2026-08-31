#!/bin/bash
# =============================================================================
# dc_perf_load_test.sh — DC(离电) + bat-perf 性能场景 满载测试
# =============================================================================
# 这是本项目最后一块未知区域，也是历史死机的【真实条件】：
#   · 死机 #2: intel + DC + EPP=power 满载
#   · 死机 #5: 拔电 15s 后满载
#   二者共同点 = DC + 满载 +（Turbo 相关）。
#
# 与前一版 dc_load_test.sh 的区别：
#   前一版实测是在 bat-save 省电场景下跑的（PL1=10W, Turbo 被 turbo-guard 主动关闭，
#   因为 default_scene 里 LAST_DC=bat-save）。那【不是】历史死机的条件。
#   本脚本要求在 bat-perf 场景下运行：gov=performance, EPP=performance,
#   no_turbo=0(Turbo 开), PL1=15W —— 这才是触及红线的真实配置。
#
# 安全网：
#   · uv-safeguard.service: 异常关机后自动回退 -50mV（在 undervolt.service 之后运行）
#   · kernel.panic=10（仅对 panic 有效；硬死机需长按电源）
#
# 用法（需已处于 DC 且已切到 bat-perf）：
#   PW_FILE=/tmp/.uvpw bash dc_perf_load_test.sh [降压值，默认 80]
# =============================================================================

set -u

UV_MV="${1:-80}"
PW_FILE="${PW_FILE:-/tmp/.uvpw}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTDIR="$(dirname "$SCRIPT_DIR")/sweep_data"
BENCH="$SCRIPT_DIR/bench"
LOG="${LOG:-$OUTDIR/dc_perf_load_m${UV_MV}_$(date +%Y%m%d_%H%M).log}"

srun() { sudo -S -p '' "$@" 2>/dev/null < "$PW_FILE"; }
uv_core()  { srun undervolt --read 2>/dev/null | awk '/^core:/{print $2}'; }
mce_cnt()  { dmesg 2>/dev/null | grep -ciE "mce|machine check"; }
pkg_temp() { sensors 2>/dev/null | awk '/^Package/{print $4}' | tr -d '+°C' | head -1; }
ac_state() { [ "$(cat /sys/class/power_supply/ACAD/online 2>/dev/null)" = "1" ] && echo AC || echo DC; }
batt()     { cat /sys/class/power_supply/BAT1/capacity 2>/dev/null; }
pl1w()     { echo $(( $(cat /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw 2>/dev/null || echo 0) / 1000000 )); }
noturbo()  { cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null; }
epp()      { cat /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference 2>/dev/null; }
now()      { date '+%H:%M:%S'; }

[ -f "$PW_FILE" ] || { echo "❌ 缺少密码文件 $PW_FILE"; exit 1; }
[ -f "$BENCH" ]   || { echo "❌ 找不到 bench"; exit 1; }

out() { echo "$1" | tee -a "$LOG"; }

: > "$LOG"
out "=== DC + bat-perf 满载测试 (降压 -${UV_MV}mV) ==="
out "本测试触及项目红线(DC 满载), 历史死机 #2/#5 即此条件"
out ""

# ---------- 1. 场景校验（必须在 bat-perf）----------
out "--- [1/4] 场景校验 ---"
out "  供电: $(ac_state) | 电池: $(batt)%"
out "  EPP: $(epp) | PL1: $(pl1w)W | no_turbo: $(noturbo) (0=Turbo开)"
if [ "$(ac_state)" != "DC" ]; then
    out "❌ 未处于 DC，本测试要求离电"; exit 1
fi
if [ "$(noturbo)" != "0" ]; then
    out "⚠️ no_turbo=$(noturbo) → Turbo 未开。请确认已切到 bat-perf 场景："
    out "     sudo bash scripts/场景管理.sh bat-perf"
    out "   注: turbo-guard 在 bat-save 场景会主动关 Turbo(设计行为)"
    exit 1
fi
out "  ✅ 场景正确（DC + Turbo 开）"

# ---------- 2. 应用降压值 ----------
out ""
out "--- [2/4] 应用 -${UV_MV}mV ---"
srun undervolt --core "-$UV_MV" --cache "-$UV_MV" --gpu "-$UV_MV" --temp 98
sleep 1
out "  实测: $(uv_core)mV | MCE=$(mce_cnt) | 温度=$(pkg_temp)°C"

snap() {
    out "  [$(now)] $1: 降压=$(uv_core)mV MCE=$(mce_cnt) 温度=$(pkg_temp)°C 电池=$(batt)% PL1=$(pl1w)W no_turbo=$(noturbo)"
}

# ---------- 3. 渐进加载 ----------
out ""
out "--- [3/4] 渐进加载 L1=2核 → L2=4核 → L3=8核 ---"
BASE_MCE=$(mce_cnt)
for st in "0,1:L1" "0-3:L2" "0-7:L3"; do
    cores="${st%%:*}"; tag="${st##*:}"
    snap "$tag-启动前"
    out "  >>> $tag 启动 (CPU $cores)"
    taskset -c "$cores" "$BENCH" > "/tmp/.dcperf_$tag.txt" 2>&1
    rc=$?
    res=$(awk '/^total=/{sub("total=","");print}' "/tmp/.dcperf_$tag.txt" 2>/dev/null)
    kps=$(awk "BEGIN{printf \"%.1f\", ${res:-0}/20/10000}")
    out "  <<< $tag 完成 rc=$rc 吞吐=${kps}万/s"
    snap "$tag-完成"
    if [ $(( $(mce_cnt) - BASE_MCE )) -gt 0 ]; then
        out "  ⚠️ 检测到 MCE 增量，中止后续级别"; break
    fi
    [ "$tag" != "L3" ] && { out "     冷却 45s..."; sleep 45; }
done

# ---------- 4. 汇总 ----------
out ""
out "--- [4/4] 汇总 ---"
out "  MCE: 基线 $BASE_MCE → 结束 $(mce_cnt)"
out "  系统: $(uptime | sed 's/^.*up //; s/,.*user.*//')"
out ""
out "=== 测试结束 $(now) ==="
out ""
out "【判读】"
out "  · 三级全过 + MCE 0 → -${UV_MV}mV 在 DC 性能场景下安全"
out "  · 任一级死机 → 立即回退 -50mV，且不应持久化 -${UV_MV}mV"
out "  · 死机后请运行: bash 测量脚本/dc_load_test.sh  (无参数=死机检查)"
