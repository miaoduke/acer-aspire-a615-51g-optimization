#!/bin/bash
# 05_一键性能模式.sh — 快速切换插电/离电/安静模式
# 需要 root 权限(部分); sysfs 写入统一走 sudo
# 修正: sysfs写入加sudo, WLAN接口自动检测

WLAN=$(iw dev 2>/dev/null | awk '/Interface/{print $2; exit}')

case "$1" in
  ac|perf|plug)
    echo "=== 插电最大性能模式 ==="
    powerprofilesctl set performance 2>/dev/null
    for cpu in /sys/devices/system/cpu/cpu*/cpufreq/; do
      echo performance | sudo tee ${cpu}scaling_governor > /dev/null 2>&1
      echo performance | sudo tee ${cpu}energy_performance_preference > /dev/null 2>&1
    done
    for usb in /sys/bus/usb/devices/*/power/autosuspend; do
      echo -1 | sudo tee "$usb" > /dev/null 2>&1
    done
    [ -n "$WLAN" ] && sudo iw dev "$WLAN" set power_save off 2>/dev/null
    echo "✓ 已切换到性能模式"
    ;;

  balanced|bal|norm)
    echo "=== 日常平衡模式 ==="
    powerprofilesctl set balanced 2>/dev/null
    for cpu in /sys/devices/system/cpu/cpu*/cpufreq/; do
      echo powersave | sudo tee ${cpu}scaling_governor > /dev/null 2>&1
      echo balance_performance | sudo tee ${cpu}energy_performance_preference > /dev/null 2>&1
    done
    echo "✓ 已切换到平衡模式"
    ;;

  bat|save|eco)
    echo "=== 离电省电模式 ==="
    powerprofilesctl set power-saver 2>/dev/null
    for cpu in /sys/devices/system/cpu/cpu*/cpufreq/; do
      echo powersave | sudo tee ${cpu}scaling_governor > /dev/null 2>&1
      echo power | sudo tee ${cpu}energy_performance_preference > /dev/null 2>&1
    done
    [ -n "$WLAN" ] && sudo iw dev "$WLAN" set power_save on 2>/dev/null
    echo "✓ 已切换到省电模式"
    ;;

 *)
    echo "用法: $0 {ac|balanced|bat}"
    echo "  ac/balanced/perf  → 插电最大性能"
    echo "  balanced/bal/norm → 日常平衡"
    echo "  bat/save/eco      → 离电省电"
    ;;
esac