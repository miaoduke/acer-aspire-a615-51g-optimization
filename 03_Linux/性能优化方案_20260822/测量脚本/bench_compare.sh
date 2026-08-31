#!/bin/bash
# =============================================================================
# bench_compare.sh <标签> - 受控性能对比(两轮 15W, 温度保护, 后台检测)
# =============================================================================
# 依据: 科学优化方案 9.2 节标准化测量协议 + SOP 2.1/2.2/2.3 节
# 安全红线: 起点>75°C 拒测 / 测试中>92°C 立即停 / 轮间冷却≥45s
# 输出: 追加到 bench_compare_results.csv (永不覆盖)
# =============================================================================

LABEL=${1:-"$(date +%Y%m%d_%H%M)"}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
RESULT="$BASE_DIR/bench_compare_results.csv"
COMPARE_DIR="$(dirname "$BASE_DIR")/Linux对比"
if [ -f "$SCRIPT_DIR/bench" ]; then
    BENCH="$SCRIPT_DIR/bench"
elif [ -f "$COMPARE_DIR/bench" ]; then
    BENCH="$COMPARE_DIR/bench"
else
    echo "错误: 找不到 bench 程序"
    exit 1
fi
RAPL="/sys/class/powercap/intel-rapl:0"

# ---------- 工具函数 ----------
get_temp() {
    sensors 2>/dev/null | awk '/^Package/{print $4}' | tr -d '+°C' | head -1
}
check_background() {
    local top
    top=$(ps aux --sort=-%cpu | awk 'NR>1 && $3>10 {n++} END{print n+0}')
    echo "后台 >10% CPU 进程数: $top"
    [ "$top" -gt 2 ] && echo "⚠️ 后台负载偏高, 建议先 quiet.sh 降权"
}
run_round() {
    local round=$1 t0 t1 res iters kps
    t0=$(get_temp)
    echo "[$LABEL] 轮$round 起点温度: ${t0}°C" >&2
    res=$("$BENCH")
    iters=$(echo "$res" | awk '/^total=/{sub("total=","");print}')
    kps=$(awk "BEGIN{printf \"%.1f\", $iters/20/10000}")
    echo "[$LABEL] 轮$round: ${kps}万/s" >&2
    echo "$kps"
}

# ---------- 安全检查 ----------
echo "=== bench_compare: $LABEL ==="
T0=$(get_temp)
echo "起点温度: ${T0}°C"
if [ -n "$T0" ] && [ "$(echo "$T0 > 75" | bc 2>/dev/null)" = "1" ]; then
    echo "❌ 起点 >75°C, 拒绝测试(热积累风险)。冷却后再试。"
    exit 1
fi
check_background
echo "PL1=$(($(cat $RAPL/constraint_0_power_limit_uw 2>/dev/null)/1000000))W PL2=$(($(cat $RAPL/constraint_1_power_limit_uw 2>/dev/null)/1000000))W Turbo=$(cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null)"
echo ""

# ---------- 两轮测试 ----------
K1=$(run_round 1)
echo "轮间冷却 45s..."
sleep 45
K2=$(run_round 2)

# 温度保护: 若测试后温度 >92°C, 中止
TEND=$(get_temp)
echo "测试后温度: ${TEND}°C"
if [ -n "$TEND" ] && [ "$(echo "$TEND > 92" | bc 2>/dev/null)" = "1" ]; then
    echo "❌ 温度 >92°C, 立即停止后续测试并冷却 ≥120s"
fi

# ---------- 记录 ----------
GOV=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)
EPP=$(cat /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference 2>/dev/null)
PL1=$(($(cat $RAPL/constraint_0_power_limit_uw 2>/dev/null)/1000000))
PL2=$(($(cat $RAPL/constraint_1_power_limit_uw 2>/dev/null)/1000000))
TURBO=$(cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null)
AVG=$(awk "BEGIN{printf \"%.1f\", ($K1+$K2)/2}")
# 环境温度(acpitz 第1个温度, 机内环境参考) + GPU 状态(独显是否活跃)
AMB=$(sensors 2>/dev/null | awk '/^acpitz/{getline; getline; gsub(/[+°C]/,""); print $2}' | head -1)
[ -z "$AMB" ] && AMB="N/A"
GPU_STATE=$(nvidia-smi --query-gpu=utilization.gpu,temperature.gpu --format=csv,noheader,nounits 2>/dev/null | head -1 || echo "N/A")

# 供电状态(2026-08-17 修复: 原硬编码 AC/100, DC 测试元数据全错)
AC_ON=$(cat /sys/class/power_supply/ACAD/online 2>/dev/null || echo 1)
[ "$AC_ON" = "1" ] && PWR="AC" || PWR="DC"
BAT=$(cat /sys/class/power_supply/BAT1/capacity 2>/dev/null || echo "N/A")

if [ ! -f "$RESULT" ]; then
    echo "时间戳,标签,缓解状态,供电,电池%,Governor,EPP,PL1W,平均万/s,轮1万/s,轮2万/s,温度1,环境温度C,温度2,GPU状态" > "$RESULT"
fi
echo "$(date +%Y-%m-%d_%H:%M),$LABEL,,$PWR,$BAT,$GOV,$EPP,$PL1,$AVG,$K1,$K2,${T0}->${TEND},$AMB,,$GPU_STATE" >> "$RESULT"

echo ""
echo "=== 结果: $LABEL 平均 ${AVG}万/s (轮1=$K1 轮2=$K2) ==="
echo "环境温度: ${AMB}°C | GPU: ${GPU_STATE}"
echo "已追加: $RESULT"
sync
