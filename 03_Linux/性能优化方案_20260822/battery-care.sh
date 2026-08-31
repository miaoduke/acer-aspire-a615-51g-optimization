#!/bin/bash
# ============================================================
# battery-care.sh — 电池保养提醒（v2.2，2026-08-19）
# 功能:
#   1. 充电 ≥80% 提醒拔电（科学依据: IOP 2025 限充 80% 循环寿命翻倍 6000+ EFC;
#      PHM 2025 窗口衰减表: 0-100 权重 1.0 vs 0-80 ≈ 0.5; CV 转变点实测 77-82%）
#   2. 浮充时间统计 + 每 60 分钟持续提醒（arXiv 2026: 25°C 满电 5 个月破 80% SoH）
#   3. 低电量保护: ≤20% 提醒充电 / ≤10% 强提醒（PHM 表: 25-0 深放窗口权重 1.0）
#   4. 充电高温提醒: 电池真实温度 ≥45°C（学术: 充电最佳 15-35°C, >45°C 加速老化）
#      温度源: acer-wmi-battery 模块 sysfs（WMBE Case 0x13 / method 19 SBS 索引 0x08）
#      回退: thermal_zone0 整机温度近似
#   5. 浮充统计 + 温度历史记录持久化（/var/lib/battery-care/）
# 部署: /usr/local/bin/battery-care.sh + systemd timer（每 10 分钟）
# ============================================================

BAT=/sys/class/power_supply/BAT1
AC=/sys/class/power_supply/ACAD/online
BAT_TEMP_SYSFS=/sys/bus/wmi/drivers/acer-wmi-battery/temperature
THERMAL=/sys/class/thermal/thermal_zone0/temp

THRESHOLD=${1:-80}          # 充电提醒阈值（默认 80%，科学最优）
RESET_AT=$((THRESHOLD - 5)) # 回落重置线
HEAT_ALARM=45               # 电池高温报警线（学术: 充电 >45°C 显著加速老化）
HEAT_RESET=40               # 高温状态回落线
STATE_DIR=/var/lib/battery-care
FLOAT_FILE=$STATE_DIR/float_minutes
ALERT_FLOAT=$STATE_DIR/alerted_float
ALERT_LOW=$STATE_DIR/alerted_low
ALERT_HEAT=$STATE_DIR/alerted_heat

[ -d "$BAT" ] || exit 0
mkdir -p "$STATE_DIR" 2>/dev/null

CAP=$(cat $BAT/capacity 2>/dev/null || echo 0)
STATUS=$(cat $BAT/status 2>/dev/null || echo Unknown)
AC_ON=$([ "$(cat $AC 2>/dev/null || echo 0)" = "1" ] && echo 1 || echo 0)
NOW=$(date +%s)

# 电池真实温度（milli°C → °C），模块不可用时回退整机温度
if [ -r "$BAT_TEMP_SYSFS" ]; then
    TEMP=$(( $(cat $BAT_TEMP_SYSFS 2>/dev/null || echo 0) / 1000 ))
    TEMP_SRC="电池"
else
    TEMP=$(awk '{print $1/1000}' $THERMAL 2>/dev/null || echo 0)
    TEMP_SRC="整机(近似)"
fi

notify() {
    local icon="$1" title="$2" msg="$3"
    for disp in "${DISPLAY:-:0}" :0 :1; do
        DISPLAY="$disp" notify-send -u normal -i "$icon" "$title" "$msg" 2>/dev/null && break
    done
    logger -t battery-care "$title: $msg"
}

# ---- 1. 充电 ≥80% 提醒（仅一次，回落重置）----
if [ "$STATUS" = "Charging" ] && [ "$CAP" -ge "$THRESHOLD" ]; then
    if [ ! -f "$STATE_DIR/alerted" ]; then
        notify battery-full-charged "电池保养提醒" \
            "电量已达 ${CAP}%（阈值 ${THRESHOLD}%）\n科学依据: 80% 后进入恒压高损伤区（CC-CV 转变 ~77-82%），限充 80% 循环寿命翻倍（6000+ vs 3000 EFC）\n建议拔掉电源"
        touch "$STATE_DIR/alerted"
    fi
fi

# ---- 2. 浮充统计 + 持续提醒 ----
if [ "$STATUS" = "Full" ] && [ "$AC_ON" = "1" ]; then
    FLOAT=$(( $(cat $FLOAT_FILE 2>/dev/null || echo 0) + 10 ))
    echo "$FLOAT" > "$FLOAT_FILE"
    LAST=$(cat $ALERT_FLOAT 2>/dev/null || echo 0)
    if [ $((NOW - LAST)) -ge 3600 ]; then
        notify battery-full "浮充时间提醒" \
            "电池已满电插电浮充 ${FLOAT} 分钟\n日历老化模型（arXiv 2026）: 25°C 满电存放约 5 个月跌破 80% 健康度\n建议拔电改用电池供电"
        echo "$NOW" > "$ALERT_FLOAT"
    fi
fi

# ---- 3. 低电量保护 ----
if [ "$STATUS" = "Discharging" ]; then
    if [ "$CAP" -le 10 ] && [ ! -f "$ALERT_LOW" ]; then
        notify battery-caution "电池低电量警告" "电量仅剩 ${CAP}%\n深度放电显著加速衰减（PHM 2025: 25-0 深放窗口衰减权重 1.0），请立即充电"
        touch "$ALERT_LOW"
    elif [ "$CAP" -le 20 ] && [ ! -f "$ALERT_LOW" ]; then
        notify battery-low "电池低电量提醒" "电量 ${CAP}%\n建议尽快充电（避免进入 <20% 深放区，PHM 表: 25-0 窗口权重 1.0 vs 62.5-37.5 窗口 0.28）"
        touch "$ALERT_LOW"
    fi
else
    [ "$CAP" -ge 25 ] && rm -f "$ALERT_LOW"
fi

# ---- 4. 充电高温提醒（电池真实温度 ≥45°C）----
if [ "$STATUS" = "Charging" ] && [ "${TEMP%.*}" -ge $HEAT_ALARM ]; then
    if [ ! -f "$ALERT_HEAT" ]; then
        notify battery-caution "充电高温提醒" \
            "充电中${TEMP_SRC}温度 ${TEMP}°C（≥${HEAT_ALARM}°C）\n学术: 充电最佳 15-35°C，>45°C 显著加速老化\n建议降低负载或暂停充电"
        touch "$ALERT_HEAT"
    fi
else
    [ "${TEMP%.*}" -le $HEAT_RESET ] 2>/dev/null && rm -f "$ALERT_HEAT"
fi

# ---- 状态重置（充电提醒）----
if [ "$CAP" -le "$RESET_AT" ]; then
    rm -f "$STATE_DIR/alerted"
fi

# ---- 浮充统计日志（每天一行，供控制台/跟踪）----
TODAY=$(date +%F)
LOG=$STATE_DIR/float_log.tsv
[ -f "$LOG" ] || echo -e "date\tfloat_minutes" > "$LOG"
grep -q "^$TODAY" "$LOG" 2>/dev/null || echo -e "$TODAY\t$(cat $FLOAT_FILE 2>/dev/null || echo 0)" >> "$LOG"

# ---- 温度历史记录（每次 tick 一行: 时间 状态 电量 温度 电流mA）----
TLOG=$STATE_DIR/temp_log.tsv
[ -f "$TLOG" ] || echo -e "time\tstatus\tcap_pct\ttemp_c\tcurrent_mA" > "$TLOG"
CUR=$(cat $BAT/current_now 2>/dev/null || echo 0)
echo -e "$(date '+%F %T')\t$STATUS\t$CAP\t${TEMP%.*}\t$((CUR/1000))" >> "$TLOG"

# ---- 健康度协议采样（严谨版: Discharging 且 40-60% SOC，中等区间 BMS 估算最稳定）----
# 2026-08-20 实测: 放电初期(97%)读数 2553mAh(79.3%) vs 充电中 2618mAh(81.4%) — 漂移 ±2.5%
# → 统一在 40-60% SOC 区间采样，每天最多 2 次
HLOG=$STATE_DIR/health_log.tsv
HLAST=$STATE_DIR/health_last
LASTDAY=$([ -f $HLAST ] && cat $HLAST || echo "none")
if [ "$STATUS" = "Discharging" ] && [ "$CAP" -ge 40 ] && [ "$CAP" -le 60 ] && [ "$LASTDAY" != "$TODAY" ]; then
    [ -f "$HLOG" ] || echo -e "date\ttemp_c\tcharge_full_uAh\thealth_pct" > "$HLOG"
    echo -e "$(date +%F\ %T)\t${TEMP%.*}\t$(cat $BAT/charge_full 2>/dev/null || echo 0)\t$(python3 -c "print(f\"{$(cat $BAT/charge_full 2>/dev/null || echo 0)/3220000*100:.2f}\")" 2>/dev/null)" >> "$HLOG"
    date +%F > "$HLAST"
fi

exit 0
