#!/bin/bash
# =============================================================================
# uv_daily_check.sh — 降压稳定性每日自检（观察期专用）
# =============================================================================
# 背景（2026-08-30）：
#   -80mV 已持久化，但 -105mV 当年的教训是「验证通过后【数天】才死机」。
#   单次测试不足以定论 → 需要长期、轻量、静默的日常巡检。
#
# 设计原则：
#   · 轻量：只读 sysfs/journal，不跑负载，耗时 <1s
#   · 静默：正常时仅写日志，【不发通知】
#   · 告警：仅在发现异常时发桌面通知 + 写告警文件
#
# 检查项：
#   1. MCE 累计计数（与上次自检对比，看增量）
#   2. 降压实际值是否等于期望值（防止服务未应用/被重置）
#   3. 上次启动是否异常关机（死机/掉电）
#   4. 关键服务是否 active（undervolt / turbo-enable / cpu-power-limit）
#   5. uv-safeguard 是否已触发回退
#   6. 电池温度可读性（顺带监控 acer-wmi-battery 模块，其曾因内核升级失效）
#   7. 内核版本变化（模块兼容性预警）
#
# 安装（一次性，需 root）：
#   sudo cp uv_daily_check.sh /usr/local/bin/ && sudo chmod +x /usr/local/bin/
#   sudo cp uv-daily-check.service uv-daily-check.timer /etc/systemd/system/
#   sudo systemctl daemon-reload && sudo systemctl enable --now uv-daily-check.timer
#
# 查看：cat /var/log/uv_daily_check.log
# 告警：cat /var/log/uv_daily_check.alert
# =============================================================================

set -u

EXPECT_MV="${EXPECT_MV:-80}"      # 期望降压值，可用环境覆盖
SAFE_MV=50
LOG=/var/log/uv_daily_check.log
ALERT=/var/log/uv_daily_check.alert
STATE_DIR=/var/lib/uv-daily-check
LOG_MAX_LINES=2000                # 日志保留上限，防无限增长

mkdir -p "$STATE_DIR" 2>/dev/null

ALERTS=""

# ---------- 采集 ----------
mce_cnt()   { dmesg 2>/dev/null | grep -ciE "mce|machine check"; }
uv_core()   { undervolt --read 2>/dev/null | awk '/^core:/{print $2}'; }
uv_gpu()    { undervolt --read 2>/dev/null | awk '/^gpu:/{print $2}'; }
uv_cache()  { undervolt --read 2>/dev/null | awk '/^cache:/{print $2}'; }
svc_st()    { systemctl is-active "$1" 2>/dev/null; }
kern()      { uname -r; }
batt_temp() { cat /sys/bus/wmi/drivers/acer-wmi-battery/temperature 2>/dev/null; }
noturbo()   { cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null; }
pl1w()      { echo $(( $(cat /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw 2>/dev/null || echo 0) / 1000000 )); }
ac_state()  { [ "$(cat /sys/class/power_supply/ACAD/online 2>/dev/null)" = "1" ] && echo AC || echo DC; }

CUR_MCE=$(mce_cnt)
CUR_CORE=$(uv_core)
CUR_GPU=$(uv_gpu)
CUR_CACHE=$(uv_cache)
CUR_KERN=$(kern)
CUR_TEMP=$(batt_temp)
CUR_DATE=$(date '+%Y-%m-%d %H:%M:%S')

# ---------- 1. MCE 增量 ----------
PREV_MCE_FILE="$STATE_DIR/prev_mce"
PREV_MCE=$(cat "$PREV_MCE_FILE" 2>/dev/null)
if [ -n "${PREV_MCE:-}" ] && [ "${PREV_MCE:-0}" -ge 0 ] 2>/dev/null; then
    MCE_DELTA=$((CUR_MCE - PREV_MCE))
    [ "$MCE_DELTA" -lt 0 ] && MCE_DELTA=0   # dmesg 环形缓冲被覆盖时计数会回退
else
    MCE_DELTA=0
fi
echo "$CUR_MCE" > "$PREV_MCE_FILE" 2>/dev/null
[ "$MCE_DELTA" -gt 0 ] && ALERTS="${ALERTS}🔴 MCE 新增 ${MCE_DELTA} 次（累计 ${CUR_MCE}）—— 硬件错误，建议回退降压\n"

# ---------- 2. 降压值是否符合期望 ----------
EXPECT_VAL="-$EXPECT_MV"
# 实测值形如 -80.08，允许 ±3mV 偏差（undervolt 量化误差）
if [ -n "${CUR_CORE:-}" ]; then
    DEVI=$(awk -v a="${CUR_CORE}" -v b="$EXPECT_VAL" 'BEGIN{d=a-b; if(d<0)d=-d; printf "%.2f", d}')
    if [ "$(awk -v d="$DEVI" 'BEGIN{print (d>3)?1:0}')" = "1" ]; then
        ALERTS="${ALERTS}🟠 降压值偏离期望：实测 ${CUR_CORE}mV，期望约 ${EXPECT_VAL}mV（偏差 ${DEVI}mV）\n"
    fi
else
    ALERTS="${ALERTS}🔴 无法读取降压值 —— undervolt 可能未生效或未安装\n"
fi

# ---------- 3. 上次启动是否异常关机 ----------
# 与 uv_safeguard 同逻辑：检测上一次 boot 的 journal 是否正常结束
PREV_BOOT=-1
LAST_LINES=$(journalctl -b "$PREV_BOOT" --no-pager 2>/dev/null | tail -20)
BOOT_COUNT=$(journalctl --list-boots --no-pager 2>/dev/null | grep -cE '^\s*-?[0-9]+ ')
if [ "${BOOT_COUNT:-0}" -ge 2 ] && [ -n "$LAST_LINES" ]; then
    if ! echo "$LAST_LINES" | grep -qE "systemd-shutdown|Journal stopped|Reached target.*Shutdown|Powering off|Rebooting"; then
        ALERTS="${ALERTS}🔴 上次启动未正常结束 —— 可能死机或掉电\n"
        ABNORMAL=1
    else
        ABNORMAL=0
    fi
else
    ABNORMAL=0
fi

# ---------- 4. 关键服务 ----------
for s in undervolt turbo-enable cpu-power-limit acdc-profile; do
    ST=$(svc_st "$s")
    [ "$ST" != "active" ] && ALERTS="${ALERTS}🟠 服务 $s 状态异常：$ST\n"
done

# ---------- 5. safeguard 是否已触发 ----------
if [ -f /var/log/uv_safeguard.triggered ]; then
    ALERTS="${ALERTS}🔴 uv-safeguard 已触发回退（异常关机 → 已降至 -${SAFE_MV}mV），请查看 /var/log/uv_safeguard.triggered\n"
fi

# ---------- 6. 电池温度可读性 ----------
if [ -z "${CUR_TEMP:-}" ]; then
    ALERTS="${ALERTS}🟡 电池温度不可读 —— acer-wmi-battery 模块可能失效（曾因内核升级失效）\n"
fi

# ---------- 7. 内核变化 ----------
PREV_KERN_FILE="$STATE_DIR/prev_kern"
PREV_KERN=$(cat "$PREV_KERN_FILE" 2>/dev/null)
if [ -n "${PREV_KERN:-}" ] && [ "$PREV_KERN" != "$CUR_KERN" ]; then
    ALERTS="${ALERTS}🟡 内核已变更：${PREV_KERN} → ${CUR_KERN}，请确认 acer-wmi-battery(DKMS) 已重建\n"
fi
echo "$CUR_KERN" > "$PREV_KERN_FILE" 2>/dev/null

# ---------- 写日志 ----------
{
    echo "[$CUR_DATE] $(ac_state) | 降压 ${CUR_CORE:-N/A}mV (gpu ${CUR_GPU:-N/A} / cache ${CUR_CACHE:-N/A}) | MCE ${CUR_MCE}(+${MCE_DELTA}) | PL1 $(pl1w)W | no_turbo $(noturbo) | 内核 ${CUR_KERN} | 电池温度 ${CUR_TEMP:-N/A}"
    if [ -n "$ALERTS" ]; then
        printf '%b' "$ALERTS" | sed 's/^/    ⚠ /'
    else
        echo "    ✓ 正常"
    fi
} >> "$LOG" 2>/dev/null

# 日志轮转（防止无限增长）
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG" 2>/dev/null)" -gt "$LOG_MAX_LINES" ]; then
    tail -n $((LOG_MAX_LINES / 2)) "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG"
fi

# ---------- 告警处理 ----------
if [ -n "$ALERTS" ]; then
    {
        echo "=============================================="
        echo " 降压稳定性自检告警 — $CUR_DATE"
        echo "=============================================="
        printf '%b' "$ALERTS"
        echo ""
        echo "【建议动作】"
        echo "  1. 查看完整日志: cat $LOG"
        echo "  2. 回退到保守值 -${SAFE_MV}mV:"
        echo "     sudo sed -i 's/--core -[0-9]*/--core -${SAFE_MV}/; s/--cache -[0-9]*/--cache -${SAFE_MV}/; s/--gpu -[0-9]*/--gpu -${SAFE_MV}/' \\"
        echo "       /etc/systemd/system/undervolt.service /etc/systemd/system/undervolt-resume.service"
        echo "     sudo systemctl daemon-reload && sudo systemctl restart undervolt"
        echo "  3. 若 MCE 持续出现，优先排查硬件而非继续降压"
        echo "=============================================="
    } > "$ALERT" 2>/dev/null

    # 桌面通知（仅在有活跃用户会话时）
    if command -v notify-send >/dev/null 2>&1; then
        for u in $(users 2>/dev/null | tr ' ' '\n' | sort -u); do
            uid=$(id -u "$u" 2>/dev/null) || continue
            [ -S "/run/user/$uid/bus" ] || continue
            sudo -u "$u" DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
                notify-send -u critical "降压自检告警" "发现 $(printf '%b' "$ALERTS" | grep -c '🔴\|🟠\|🟡') 项异常，详见 $ALERT" 2>/dev/null
        done
    fi
    exit 1
else
    rm -f "$ALERT" 2>/dev/null
    exit 0
fi
