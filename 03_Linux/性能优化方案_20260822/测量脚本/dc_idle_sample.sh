#!/bin/bash
# dc_idle_sample.sh <标签> <秒数> - 离电空闲功耗采样(免root, 电池电流×电压)
# 用法: ./dc_idle_sample.sh M2_balanced 60
# 输出: 每5s一行: 时间 整机功耗W 平均频率MHz 包温度°C
LABEL=${1:-sample}
DUR=${2:-60}
echo "=== DC 空闲采样: $LABEL (${DUR}s) ==="
echo "时间, 整机功耗W, 频率MHz, 温度°C"
TOTAL_W=0; N=0
for i in $(seq 1 $((DUR/5))); do
  I=$(cat /sys/class/power_supply/BAT1/current_now 2>/dev/null)
  V=$(cat /sys/class/power_supply/BAT1/voltage_now 2>/dev/null)
  [ -z "$I" ] && I=0; [ -z "$V" ] && V=0
  W=$(awk "BEGIN{printf \"%.1f\", $I*$V/1e12}")
  F=$(awk '{s+=$1;n++}END{if(n)printf "%.0f", s/n/1000}' /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq 2>/dev/null)
  T=$(sensors 2>/dev/null | awk '/^Package/{print $4}' | tr -d '+°C' | head -1)
  echo "$(date +%H:%M:%S), ${W}W, ${F}MHz, ${T}°C"
  TOTAL_W=$(awk "BEGIN{printf \"%.1f\", $TOTAL_W+$W}"); N=$((N+1))
  sleep 5
done
AVG=$(awk "BEGIN{printf \"%.1f\", $TOTAL_W/$N}")
echo "=== $LABEL 平均整机功耗: ${AVG}W ==="