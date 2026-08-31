#!/bin/bash
# 性能对比测试 — 优化前后对比
# 用法: ./性能对比.sh [标签]
# 修正: BAT0→自动检测, AC→ACAD自动检测, 温度字段第4列

# 相对定位(沿用 bench_compare.sh 范式): 目录改名/重组后仍可用, 不再依赖硬编码时间戳路径
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
RESULT="$BASE_DIR/性能对比结果.csv"
# bench 优先取同级 测量脚本/, 回退到上级 Linux对比/
if [ -f "$BASE_DIR/测量脚本/bench" ]; then
    BENCH="$BASE_DIR/测量脚本/bench"
elif [ -f "$(dirname "$BASE_DIR")/Linux对比/bench" ]; then
    BENCH="$(dirname "$BASE_DIR")/Linux对比/bench"
else
    BENCH="/nonexistent/bench"
fi

if [ ! -f "$BENCH" ]; then
    echo "错误: 测试程序不存在: $BENCH"
    exit 1
fi

LABEL=${1:-"$(date +%Y%m%d_%H%M)"}

detect_ac() {
    for d in /sys/class/power_supply/*; do
        [ "$(cat "$d/type" 2>/dev/null)" = "Mains" ] && [ "$(cat "$d/online" 2>/dev/null)" = "1" ] && { echo 1; return; }
    done
    echo 0
}

detect_bat_cap() {
    for d in /sys/class/power_supply/BAT*; do
        [ -d "$d" ] && cat "$d/capacity" 2>/dev/null && return
    done
}

get_temp() {
    sensors 2>/dev/null | awk '/^Package/{print $4}' | tr -d '+°C' | head -1
}

echo "=== i5-8250U 性能对比测试 ==="
echo "标签: $LABEL"
echo "测试条件: 8线程 LCG 20秒满载"
echo ""

# 记录当前配置
GOV=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)
EPP=$(cat /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference 2>/dev/null)
PL1=$(cat /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw 2>/dev/null)
PL2=$(cat /sys/class/powercap/intel-rapl:0/constraint_1_power_limit_uw 2>/dev/null)
TURBO=$(cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null)
TEMP_START=$(get_temp)
BAT=$(detect_bat_cap)
AC=$(detect_ac)

echo "配置: AC=$([ "$AC" = "1" ] && echo '是' || echo '否') Battery=${BAT:-N/A}% Temp=${TEMP_START:-N/A}°C"
echo "Governor=$GOV EPP=$EPP PL1=$((${PL1:-15000000}/1000000))W PL2=$((${PL2:-25000000}/1000000))W Turbo=$([ "$TURBO" = "0" ] && echo 'ON' || echo 'OFF')"
echo ""

# 运行测试
echo "开始测试(约20秒)..."
T0=$(date +%H:%M:%S.%3N)
RES=$($BENCH)
T1=$(date +%H:%M:%S.%3N)

# 解析结果
ITERS=$(echo "$RES" | awk '/^total=/{sub("total=","");print}')
KPS=$(awk "BEGIN{printf \"%.1f\", $ITERS/20/10000}")

# 测试后温度
TEMP_END=$(get_temp)

echo ""
echo "=== 测试结果 ==="
echo "标签: $LABEL"
echo "迭代次数: $ITERS"
echo "吞吐量: ${KPS}万/s"
echo "耗时: $T0 → $T1"
echo "温度变化: ${TEMP_START:-N/A}°C → ${TEMP_END:-N/A}°C"
echo "配置: AC=$([ "$AC" = "1" ] && echo '是' || echo '否') Gov=$GOV EPP=$EPP PL1=$((${PL1:-15000000}/1000000))W"

# 写入结果文件(如果不存在则创建表头)
if [ ! -f "$RESULT" ]; then
    echo "时间戳,标签,AC,电池%,温度开始,温度结束,Governor,EPP,PL1(W),PL2(W),Turbo,迭代次数,吞吐量(万/s)" > "$RESULT"
fi

echo "$(date +%Y-%m-%d_%H:%M),$LABEL,$([ "$AC" = "1" ] && echo 'AC' || echo 'DC'),${BAT:-N/A},${TEMP_START:-N/A},${TEMP_END:-N/A},$GOV,$EPP,$((${PL1:-15000000}/1000000)),$((${PL2:-25000000}/1000000)),$([ "$TURBO" = "0" ] && echo 'ON' || echo 'OFF'),$ITERS,$KPS" >> "$RESULT"

echo ""
echo "结果已保存到: $RESULT"
echo ""
echo "=== 历史对比 ==="
column -t -s',' "$RESULT" 2>/dev/null || cat "$RESULT"