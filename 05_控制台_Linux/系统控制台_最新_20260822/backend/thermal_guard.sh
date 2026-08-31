#!/bin/bash
# thermal-guard.sh — 温度→PL 自动限流（安全风扇替代，零 EC 交互）
# 逻辑: CPU 温度 ≥ HIGH 时降 PL1 至 DOWN_PL1W；回落到 LOW 后恢复原值。
# 不碰 EC/共享内存/ACPI 风扇——纯 RAPL sysfs 写入（死机史铁律安全区）。
# 配置: 环境变量覆盖（服务里设置）
TH=/sys/class/thermal/thermal_zone2/temp
RAPL=/sys/class/powercap/intel-rapl:0
HIGH=${TH_HIGH:-85000}    # 85°C 触发
LOW=${TH_LOW:-75000}      # 75°C 恢复
DOWN_PL1=${TH_DOWN_PL1:-15}  # 限流 PL1 (W)
LOG=/var/log/thermal-guard.log
POLL=${TH_POLL:-10}       # 秒

state=normal
saved=""
while true; do
  t=$(cat "$TH" 2>/dev/null)
  case "$state" in
    normal)
      if [ -n "$t" ] && [ "$t" -ge "$HIGH" ]; then
        saved=$(cat "$RAPL/constraint_0_power_limit_uw" 2>/dev/null)
        echo $((DOWN_PL1 * 1000000)) > "$RAPL/constraint_0_power_limit_uw" 2>/dev/null
        echo "$(date '+%F %T') 高温 $((t / 1000))°C -> PL1=${DOWN_PL1}W (原 $((saved / 1000000))W)" >> "$LOG"
        state=limited
      fi
      ;;
    limited)
      if [ -n "$t" ] && [ "$t" -le "$LOW" ]; then
        if [ -n "$saved" ]; then
          echo "$saved" > "$RAPL/constraint_0_power_limit_uw" 2>/dev/null
          echo "$(date '+%F %T') 回落 $((t / 1000))°C -> 恢复 PL1=$((saved / 1000000))W" >> "$LOG"
        fi
        state=normal
      fi
      ;;
  esac
  sleep "$POLL"
done