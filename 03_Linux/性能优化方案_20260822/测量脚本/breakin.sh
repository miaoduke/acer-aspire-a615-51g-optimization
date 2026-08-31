#!/bin/bash
# breakin.sh - PTM7950 相变片磨合协议: 3 轮热循环(满载20s + 歇60s), 全程0.25s采样
# 用途: 换脂后首次开机执行; 同时作为正品诊断(正品逐轮峰值应下降, 假货平坦)
# 安全红线: 起点>75°C拒测 / 测试中>92°C停 / >95°C无条件冷却120s
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BENCH="$SCRIPT_DIR/bench"
LOG="$SCRIPT_DIR/log_breakin_$(date +%Y%m%d_%H%M%S).txt"

echo "=== PTM7950 磨合开始 $(date '+%F %T') ===" | tee "$LOG"
ACPITZ=$(sensors 2>/dev/null | awk '/temp1/{print $2}' | head -1)
EPP=$(cat /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference 2>/dev/null)
GPU=$(lsmod 2>/dev/null | grep -q nvidia && echo nvidia || echo intel)
AC=$(cat /sys/class/power_supply/ACAD/online 2>/dev/null)
echo "环境: acpitz=$ACPITZ EPP=$EPP GPU=$GPU AC=$AC" | tee -a "$LOG"

for CYCLE in 1 2 3; do
  T0=$(cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null | awk '$1>30000' | sort -n | tail -1)
  echo "轮$CYCLE 起点=$((T0/1000))°C" | tee -a "$LOG"
  if [ "$T0" -gt 75000 ]; then echo "起点>75°C 拒测!" | tee -a "$LOG"; exit 1; fi

  "$SCRIPT_DIR/sample.sh" "$LOG.tmp" 20 > "$LOG.tmp" 2>&1 &
  SP=$!
  sleep 0.5
  "$BENCH" > /dev/null 2>&1
  kill $SP 2>/dev/null; wait $SP 2>/dev/null
  [ -s "$LOG.tmp" ] || { echo "错误: 采样文件为空!" | tee -a "$LOG"; exit 1; }
  PEAK=$(awk '{print $3}' "$LOG.tmp" | sed 's/temp=//' | sort -n | tail -1)
  echo "轮$CYCLE 满载峰值=$((PEAK/1000))°C" | tee -a "$LOG"
  if [ "$PEAK" -gt 92000 ]; then echo ">92°C 停止!" | tee -a "$LOG"; exit 1; fi

  "$SCRIPT_DIR/sample.sh" "$LOG.tmp2" 60 > "$LOG.tmp2" 2>&1 &
  SP=$!
  sleep 60
  kill $SP 2>/dev/null; wait $SP 2>/dev/null
  [ -s "$LOG.tmp2" ] || { echo "错误: 歇后采样文件为空!" | tee -a "$LOG"; exit 1; }
  TEND=$(awk '{print $3}' "$LOG.tmp2" | sed 's/temp=//' | sort -n | tail -1)
  echo "轮$CYCLE 歇后=$((TEND/1000))°C" | tee -a "$LOG"
done
rm -f "$LOG.tmp" "$LOG.tmp2"
echo "=== 磨合完成 $(date '+%F %T') ===" | tee -a "$LOG"