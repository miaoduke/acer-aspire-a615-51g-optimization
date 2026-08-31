#!/bin/bash
# 06_性能验证测试.sh — 优化前后对比测试
# 无需 root,复用 Linux对比/bench 二进制
# 修正: 温度字段第4列, bench存在性检查

# 相对定位(沿用 bench_compare.sh 范式): 目录改名/重组后仍可用, 不再依赖硬编码时间戳路径
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
RESULT="$BASE_DIR/验证结果.csv"
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

get_temp() {
    sensors 2>/dev/null | awk '/^Package/{print $4}' | tr -d '+°C' | head -1
}

echo "=== i5-8250U 性能验证测试 ==="
echo "测试条件: 8线程 LCG 20秒满载"
echo ""

# 记录当前配置
GOV=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)
EPP=$(cat /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference)
PL1=$(cat /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw)
TEMP=$(get_temp)

echo "当前配置: governor=$GOV epp=$EPP PL1=$(($PL1/1000000))W temp=${TEMP:-N/A}°C"
echo ""

echo "开始测试(约 20 秒)..."
T0=$(date +%H:%M:%S.%3N)
RES=$($BENCH)
T1=$(date +%H:%M:%S.%3N)
ITERS=$(echo "$RES" | awk '/^total=/{sub("total=","");print}')
KPS=$(awk "BEGIN{printf \"%.1f\", $ITERS/20/10000}")

echo ""
echo "=== 测试结果 ==="
echo "迭代次数: $ITERS"
echo "吞吐量: ${KPS}万/s"
echo "耗时: $T0 → $T1"
echo "配置: governor=$GOV epp=$EPP PL1=$(($PL1/1000000))W"

# 追加到结果文件
echo "$(date +%Y-%m-%d_%H:%M),$GOV,$EPP,$(($PL1/1000000)),$ITERS,$KPS,$TEMP" >> $RESULT
echo ""
echo "结果已追加到: $RESULT"