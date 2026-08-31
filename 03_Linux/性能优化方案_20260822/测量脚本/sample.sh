#!/bin/bash
# sample.sh <logfile> <seconds> - 采样频率/温度/RAPL功耗/电池功耗
LOG=$1
DUR=$2
[ -z "$DUR" ] && DUR=30
E0=$(cat /sys/class/powercap/intel-rapl:0/energy_uj 2>/dev/null)
END=$(( $(date +%s%N) / 1000000 + DUR * 1000 ))
while [ $(( $(date +%s%N) / 1000000 )) -lt $END ]; do
  FREQ=0; N=0
  for f in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq; do
    V=$(cat $f 2>/dev/null); [ -n "$V" ] && { FREQ=$((FREQ+V)); N=$((N+1)); }
  done
  [ $N -gt 0 ] && FREQ=$((FREQ/N))
  TEMP=$(cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null | awk '$1>30000' | sort -n | tail -1)
  E1=$(cat /sys/class/powercap/intel-rapl:0/energy_uj 2>/dev/null)
  W=""; [ -n "$E0" ] && [ -n "$E1" ] && W=$(( (E1-E0) / 250000 ))
  MA=$(cat /sys/class/power_supply/BAT1/uevent 2>/dev/null | awk -F= '/CURRENT_NOW/{print $2}')
  MV=$(cat /sys/class/power_supply/BAT1/uevent 2>/dev/null | awk -F= '/VOLTAGE_NOW/{print $2}')
  BW=""; [ -n "$MA" ] && [ -n "$MV" ] && BW=$(awk "BEGIN{printf \"%.1f\", $MA*$MV/1000000000000}")
  echo "$(date +%H:%M:%S.%3N) freq=${FREQ}kHz temp=${TEMP} rapW=${W} batW=${BW}"
  E0=$E1
  sleep 0.25
done