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

EXPECT_MV="${EXPECT_MV:-100}"      # 期望降压值，可用环境覆盖
SAFE_MV=50
LOG=/var/log/uv_daily_check.log
ALERT=/var/log/uv_daily_check.alert
STATE_DIR=/var/lib/uv-daily-check
LOG_MAX_LINES=2000                # 日志保留上限，防无限增长

mkdir -p "$STATE_DIR" 2>/dev/null

ALERTS=""

# ---------- 采集 ----------
# P0-1 (2026-09-04): mce_cnt 重写 —— 原实现 `dmesg | grep -ciE "mce|machine check"`
# 把三类非 MCE 行误算成 CPU MCE，导致 uv-daily-check 每天误报：
#   1. 内核开机必打: "misc mcelog: hash matches"（mcelog 驱动注册，无符号表匹配提示）
#   2. rasdaemon 启动订阅: "mce:mce_record event enabled"（每次开机 8+ 行）
#   3. PCIe AER 校正错误: ath10k Wi-Fi 的 Receiver Error/Bad DLLP（累计 200+ 条，与降压无关）
# 实测 ras-mc-ctl --summary 显示 "No MCE errors."（真实 CPU MCE = 0）。
#
# 新逻辑（三层）:
#   A. 优先 ras-mc-ctl --summary（rasdaemon sqlite DB，权威区分 CPU MCE vs PCIe AER）
#      - "No MCE errors." → 0
#      - "MCE records summary:" 后的 "\t<count> <msg> errors" 行 → count 求和
#      - "MCE events:"（--errors 格式兜底）→ 事件条目行数
#   B. ras-mc-ctl 不可用/DB 未建时回退 journalctl -k -b -0：只匹配真正的
#      MCE 硬件事件行（行内须有 bank/状态寄存器/纠错动作等标志），并显式排除
#      mcelog 注册行、rasdaemon 订阅行、AER 行、acpi/exynos 等杂项
#   C. 都失败 → 返回 ""（上游按 0 处理，不误报）
mce_cnt() {
    local out cnt
    # --- A. ras-mc-ctl（root 跑本脚本时直接可用；sudoers 已白名单 /usr/sbin/ras-mc-ctl）---
    if out=$(ras-mc-ctl --summary 2>/dev/null); then
        # 无 MCE（最常见路径，含 PCIe AER 也返回 No）
        if echo "$out" | grep -q '^No MCE errors'; then
            echo 0; return
        fi
        # --summary 格式: "MCE records summary:" 后 "\t<count> <msg> errors" 行 → count 求和
        # awk 内置对制表符敏感度低于 grep -E（POSIX ERE 不解释 \t，曾致漏计）
        cnt=$(echo "$out" | awk '/^MCE records summary:/{f=1;next} f && /^[[:space:]]+[0-9]+/{s+=$1;next} f&&/^[^[:space:]]/{f=0} END{print s+0}')
        [ "$cnt" -gt 0 ] && { echo "$cnt"; return; }
        # "MCE events:" 格式（--errors 兼容）: 条目行 "<id> <time> error: ..."
        cnt=$(echo "$out" | awk '/^MCE events:/{f=1;next} f && /^[[:space:]]*[0-9]+ [0-9]{4}-/{c++} END{print c+0}')
        [ "$cnt" -gt 0 ] && { echo "$cnt"; return; }
        echo 0; return
    fi
    # --- B. 回退: journalctl 内核日志，严格白名单正则（排除项在前，避免先命中）---
    # 内核真实 MCE 行样例：
    #   mce: [Hardware Error]: CPU 0: Machine Check Exception: 5 Bank 4: b200000000070f0f
    #   mce: [Hardware Error]: Machine check events logged
    # 排除目标：mcelog 注册行 / rasdaemon 订阅行 / PCIe AER / msr-undervolt 警告
    journalctl -k -b 0 --no-pager 2>/dev/null \
        | grep -iE 'machine check|hardware error|mce.*bank' \
        | grep -ivE 'mcelog|rasdaemon|event enabled|hash matches|aer|pcie|dellp|undervolt|write to unrecognized' \
        | wc -l
}
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
CUR_MCE=${CUR_MCE:-0}   # P0-1: mce_cnt 全链路失败时按 0 处理，绝不误报
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

# ---------- 3. 上次启动是否异常关机（P1-1: 改读 safeguard verdict 单一来源） ----------
# 旧版: 此处复制了 uv_safeguard 的同款 grep，两处逻辑已发生过漂移，
# 且会把“用户手动硬重启”（无关机序列但无崩溃特征）误报为 🔴 猛干扰。
# 新版: 直接读 /var/lib/uv-safeguard/verdict（uv_safeguard.sh 开机时已判定）：
#   CLEAN        正常关机序列 → 不告警
#   WATCH        疑似手动重启（safeguard 已记 strike 未回退）→ 仅 🟡 轻提醒（不 exit 1 级）
#   CRASH_REVERT / STRIKE_REVERT  safeguard 已回退 -50mV → 🟡 信息性（回退动作已发生）
#   SKIP         safeguard 未跑/不可读 → 🟡 提示（不是 🔴，避免连环误报）
# verdict 文件不存在 = safeguard 未安装或首次运行 → 回退到旧独立检测（保守但不升级为红）
VERDICT_FILE=/var/lib/uv-safeguard/verdict
if [ -r "$VERDICT_FILE" ]; then
    # P1-1 修复(13:57): 旧解析 awk '{print $2}' 取到的是时间戳字段 ——
    # 新格式 KEY=VAL 自描述，优先取 verdict= 行；兼容旧单行 "时间 VERDICT 详情"
    VERDICT=$(awk -F'=' '/^verdict=/{print $2; found=1} END{if(!found) print ""}' "$VERDICT_FILE" 2>/dev/null)
    if [ -z "$VERDICT" ]; then
        VERDICT=$(awk '{for(i=1;i<=NF;i++) if($i=="CLEAN"||$i=="WATCH"||$i=="CRASH_REVERT"||$i=="STRIKE_REVERT"||$i=="SKIP"){print $i; exit}}' "$VERDICT_FILE" 2>/dev/null)
    fi
    case "$VERDICT" in
        CLEAN) ABNORMAL=0 ;;
        WATCH) ABNORMAL=0; ALERTS="${ALERTS}🟡 safeguard 观察中：上次关机无崩溃证据（疑似手动重启，未回退 -100mV）；确认后 sudo rm -f /var/lib/uv-safeguard/watch_strike\n" ;;
        CRASH_REVERT|STRIKE_REVERT) ABNORMAL=0; ALERTS="${ALERTS}🟡 safeguard 已自动回退 -${SAFE_MV}mV（上次异常关机）—— 详情 /var/log/uv_safeguard.triggered\n" ;;
        SKIP|*) ABNORMAL=0; ALERTS="${ALERTS}🟡 safeguard verdict 异常（$VERDICT），建议 sudo systemctl start uv-safeguard 重判\n" ;;
    esac
else
    # safeguard 未部署/verdict 不可读 → 独立兜底检测（同新版三级：关机序列 + 崩溃特征）
    LAST_LINES=$(journalctl -b -1 --no-pager 2>/dev/null | tail -20)
    if echo "$LAST_LINES" | grep -qE 'systemd-shutdown\[|Journal stopped|systemd\[1\].*(Reached target.*(Shutdown|Reboot)|Powering off|Rebooting)'; then
        ABNORMAL=0
    elif journalctl -b -1 -k --no-pager 2>/dev/null \
        | grep -iE 'kernel panic|oops|BUG:|general protection fault|machine check|hardware error|mce.*bank|soft lockup|NVRM: Xid' \
        | grep -ivE 'mcelog|rasdaemon|event enabled|hash matches|aer|pcie|dellp|undervolt|write to unrecognized' \
        | grep -q .; then
        ABNORMAL=1
        ALERTS="${ALERTS}🔴 上次启动有崩溃特征（panic/oops/MCE）—— 可能死机，建议检查\n"
    else
        # 无关机序列但无崩溃特征 → 不再报 🔴（P1-1: 手动重启不应造成每日红告警）
        ABNORMAL=0
        ALERTS="${ALERTS}🟡 上次启动无关机序列且无崩溃特征（疑似手动重启；safeguard verdict 不可读）\n"
    fi
fi

# ---------- 4. 关键服务 ----------
# 2026-09-01 修复: M3 生效时 acdc-profile 会被主动 stop/disable（M3 设计如此），
# 此时不视为异常。仅当 M3 未生效时检查 acdc-profile。
M3_ON=$(systemctl is-enabled m3-power-saver 2>/dev/null)
for s in undervolt turbo-enable cpu-power-limit acdc-profile thermal-guard; do
    if [ "$s" = "acdc-profile" ] && [ "$M3_ON" = "enabled" ]; then
        continue  # M3 模式下 acdc-profile 本应禁用，跳过
    fi
    ST=$(svc_st "$s")
    if [ "$ST" != "active" ]; then
        EN=$(systemctl is-enabled "$s" 2>/dev/null)
        # 2026-09-01 增强: 附 enabled 状态 + 失败原因，便于直接定位（此前只报状态，看不出为何失败）
        REASON=$(systemctl show "$s" -p Result --value 2>/dev/null)
        LAST=$(systemctl status "$s" --no-pager -n 0 2>/dev/null | grep -oE "status=[0-9]+/[A-Z]+" | head -1)
        ALERTS="${ALERTS}🟠 服务 $s 状态异常：${ST}（开机自启=${EN:-?}${REASON:+ | result=$REASON}${LAST:+ | $LAST}）\n"
        [ "$EN" = "disabled" ] && ALERTS="${ALERTS}     可能原因：M3 退出未恢复 / 服务文件 ExecStart 路径失效\n"
    fi
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
# P1-1 告警分级: 只有 🔴/🟠 才 exit 1（服务 failed）；纯 🟡 提醒（safeguard
# 观察中/已自动处理）写 alert 文件但 exit 0 —— 避免手动重启后第二天仍标红 failed。
CRIT_N=$(printf '%b' "$ALERTS" 2>/dev/null | grep -c '🔴\|🟠')
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
                # 🔴/🟠 才弹 critical；纯 🟡 用 normal 级（不制造红色紧迫感）
                if [ "$CRIT_N" -gt 0 ]; then
                    notify-send -u critical "降压自检告警" "发现 ${CRIT_N} 项需处理 + $(printf '%b' "$ALERTS" | grep -c '🟡') 项提醒，详见 $ALERT" 2>/dev/null
                else
                    notify-send -u normal "降压自检提醒" "仅 🟡 轻提醒（safeguard 观察/已自动处理），详见 $ALERT" 2>/dev/null
                fi
        done
    fi
    # P1-1 分级退出: 只有真正需处理的 🔴/🟠 才算失败
    if [ "$CRIT_N" -gt 0 ]; then
        exit 1
    fi
    exit 0
else
    rm -f "$ALERT" 2>/dev/null
    exit 0
fi
