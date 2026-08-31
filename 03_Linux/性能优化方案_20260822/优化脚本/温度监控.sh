#!/bin/bash
# 温度-频率-功耗 实时监控
# 用法: ./温度监控.sh [间隔秒数] [输出文件]
# 修正: 温度字段解析(sensors第4列), 功耗改为RAPL差值计算

INTERVAL=${1:-2}
OUTPUT=${2:-""}

RAPL="/sys/class/powercap/intel-rapl:0"

get_temp() {
    sensors 2>/dev/null | awk '/^Package/{print $4}' | tr -d '+°C' | head -1
}

read_energy() {
    cat "$RAPL/energy_uj" 2>/dev/null || sudo cat "$RAPL/energy_uj" 2>/dev/null
}

if [ -n "$OUTPUT" ]; then
    echo "时间,温度(°C),频率(MHz),功耗(W),Governor,EPP" > "$OUTPUT"
fi

echo "=== 温度-频率-功耗 实时监控 ==="
echo "按 Ctrl+C 停止"
echo ""

while true; do
    TS=$(date +%H:%M:%S)

    # 温度
    TEMP=$(get_temp)
    if [ -z "$TEMP" ]; then
        TEMP=$(cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null | head -1)
        TEMP=$(awk "BEGIN{printf \"%.1f\", $TEMP/1000}")
    fi

    # 频率(取CPU0)
    FREQ=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null)
    FREQ_MHz=$(awk "BEGIN{printf \"%.0f\", ${FREQ:-0}/1000}")

    # 功耗:RAPL差值法(采样间隔内的平均功率)
    E0=$(read_energy)
    sleep "$INTERVAL"
    E1=$(read_energy)
    if [ -n "$E0" ] && [ -n "$E1" ]; then
        POWER=$(awk "BEGIN{printf \"%.1f\", ($E1-$E0)/1000000/$INTERVAL}")
    else
        POWER=""
    fi

    # Governor和EPP
    GOV=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)
    EPP=$(cat /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference 2>/dev/null)

    # 温度颜色
    if [ -n "$TEMP" ] && [ "$(echo "$TEMP > 85" | bc 2>/dev/null)" = "1" ]; then
        TEMP_COLOR="\033[31m"  # 红色
    elif [ -n "$TEMP" ] && [ "$(echo "$TEMP > 70" | bc 2>/dev/null)" = "1" ]; then
        TEMP_COLOR="\033[33m"  # 黄色
    else
        TEMP_COLOR="\033[32m"  # 绿色
    fi

    printf "${TEMP_COLOR}%s  温度: %6s°C  频率: %4sMHz  功耗: %5sW  Gov: %-12s EPP: %-20s\033[0m\n" \
        "$TS" "${TEMP:-N/A}" "${FREQ_MHz:-N/A}" "${POWER:-N/A}" "$GOV" "$EPP"

    # 如果指定了输出文件,追加数据
    if [ -n "$OUTPUT" ]; then
        echo "$TS,$TEMP,$FREQ_MHz,$POWER,$GOV,$EPP" >> "$OUTPUT"
    fi
done