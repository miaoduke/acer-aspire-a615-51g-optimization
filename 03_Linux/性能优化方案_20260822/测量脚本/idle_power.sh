#!/bin/bash
# idle_power.sh <EPP> - 空闲功耗测量(60s RAPL 窗口), 需 root
# 用法: sudo idle_power.sh performance|balance_performance|power
# 输出: EPP, 平均功率W, 包温度C, 平均频率kHz
EPP=${1:-performance}
RAPL=/sys/class/powercap/intel-rapl:0
echo "$EPP" > /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference
sleep 3   # 等 EPP 生效
E1=$(cat $RAPL/energy_uj)
F1=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq)
sleep 60
E2=$(cat $RAPL/energy_uj)
F2=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq)
TEMP=$(sensors 2>/dev/null | awk '/^Package/{print $4}' | tr -d '+°C')
W=$(awk "BEGIN{printf \"%.2f\", ($E2-$E1)/1000000/60}")
F=$(awk "BEGIN{printf \"%.0f\", ($F1+$F2)/2/1000}")
echo "$EPP, ${W}W, ${TEMP}°C, ${F}MHz"
