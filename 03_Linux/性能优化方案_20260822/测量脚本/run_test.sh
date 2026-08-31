#!/bin/bash
# run_test.sh <名称> - 运行 20s 8线程基准 + 8s 空闲, 全程采样 (0.25s)
# 重装后路径自动检测(原版硬编码 /media/dale 已修正)
# 用法: ./run_test.sh 标签
NAME=$1
[ -z "$NAME" ] && NAME=test

# 自动定位 bench 与结果目录(优先本文件夹内 bench, 其次 Linux对比/)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
COMPARE_DIR="$(dirname "$BASE_DIR")/Linux对比"
if [ -f "$SCRIPT_DIR/bench" ]; then
    BENCH="$SCRIPT_DIR/bench"
    DIR="$SCRIPT_DIR"
elif [ -f "$COMPARE_DIR/bench" ]; then
    BENCH="$COMPARE_DIR/bench"
    DIR="$COMPARE_DIR"
else
    echo "错误: 找不到 bench 程序(测量脚本/bench 或 Linux对比/bench)"
    exit 1
fi

GOVID_LINE=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor <(cat /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference 2>/dev/null) 2>/dev/null | paste -sd' ')
echo "[$NAME] 当前配置: gov=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor) epp=$(cat /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference)"
echo "[$NAME] START $(date '+%Y-%m-%d %H:%M:%S')"
"$SCRIPT_DIR/sample.sh" "$DIR/log_${NAME}_full.txt" 20 > "$DIR/log_${NAME}_full.txt" &
SP=$!
sleep 0.5
T0=$(date +%H:%M:%S.%3N)
RES=$("$BENCH")
T1=$(date +%H:%M:%S.%3N)
sleep 8
T2=$(date +%H:%M:%S.%3N)
kill $SP 2>/dev/null; wait $SP 2>/dev/null
ITERS=$(echo "$RES" | awk '/^total=/{sub("total=","");print}')
KPS=$(awk "BEGIN{printf \"%.1f\", $ITERS/20/10000}")
echo "$NAME,$GOVID_LINE,$T0,$T1,$T2,$ITERS,$KPS" >> "$DIR/results.csv"
echo "[$NAME] iters=$ITERS (${KPS}万/s) 完整采样见 log_${NAME}_full.txt"
tail -1 "$DIR/log_${NAME}_full.txt"
