#!/bin/bash
# =============================================================================
# uv_safeguard.sh — 降压安全网：异常关机后自动回退保守值（P1-1 三级判定版）
# =============================================================================
# 为什么需要它（2026-08-30）：
#   -80mV 持久化后，undervolt.service 写死 -80mV。若后续因降压导致硬死机，
#   重启后会再次应用 -80mV → 可能陷入「死机→重启→又死机」的循环，
#   而本项目硬死机【无 pstore 转储】，排查困难。
#   本脚本在开机时检测上次是否异常关机（硬死机/掉电），若是则自动回退到
#   保守值 -50mV 并留下标记文件，供用户判断。
#
# P1-1 重构（2026-09-04）— 三级判定，解决「手动重启被误回退」：
#   旧逻辑: journal 末尾无关机序列 → 一律判异常 → 回退 -50mV。
#     问题: 用户长按电源键/强制重启同样来不及写关机序列，
#           2026-09-04 09:13 的手动重启即被误判 → 回退 → 用户每天手动恢复。
#   新逻辑:
#     CLEAN         上次启动有系统级关机序列（systemd-shutdown[ / Journal stopped
#                   / systemd[1] 的 Shutdown|Reboot target / Powering off）
#                   → 不动作，并清除 watch strike（翻篇）
#                   注: 排除用户级 systemd[N] 实例的 "Reached target
#                   shutdown.target" 行 —— 2026-09-04 实测 boot -1 中
#                   systemd[1339] 的该行会被旧正则误匹配为系统关机。
#     CRASH_REVERT  无关机序列 + journal 有崩溃特征（kernel panic / oops /
#                   BUG: / GPF / machine check / soft lockup / NVRM Xid，
#                   噪声过滤正则与 P0-1 一致：排除 mcelog 注册行、rasdaemon
#                   订阅行、PCIe AER、msr-undervolt 警告）
#                   → 立即回退 -50mV（真硬死机，高置信）
#     WATCH         无关机序列 + 无崩溃特征 → 疑似手动重启:
#                     第 1 次: 不回退，仅记 strike + 轻量提醒（🟡）
#                              （用户确认后: sudo rm -f /var/lib/uv-safeguard/watch_strike）
#                     第 2 次（7 天内）: 升级回退 -50mV（反复异常才动手）
#                     strike 超 7 天自动过期（按首次重新计）
#
# 判定单一来源: 本脚本把判定写入 /var/lib/uv-safeguard/verdict
#   （CLEAN | WATCH | CRASH_REVERT | STRIKE_REVERT | SKIP），
#   uv_daily_check.sh 的「上次启动未正常结束」检查改为读该文件，
#   不再各自维护同款 grep 逻辑（旧版两处复制已发生过漂移）。
#
# 安装（一次性，需 root）：
#   sudo cp uv_safeguard.sh /usr/local/bin/ && sudo chmod +x /usr/local/bin/uv_safeguard.sh
#   sudo cp uv-safeguard.service /etc/systemd/system/
#   sudo systemctl daemon-reload && sudo systemctl enable uv-safeguard.service
#   （install.sh 已含 [P1-1] 部署段）
#
# 回退后如何恢复 -100mV：
#   sudo systemctl restart undervolt     （或手动 undervolt --core -100 ...）
#
# 人工交叉核对（verdict 存疑时）:
#   journalctl -b -1 -n 20    # 上次启动日志末尾（看有无 systemd-shutdown 序列）
#   last -x reboot shutdown   # wtmp 关机/重启账本
# =============================================================================

set -u

SAFE_MV=50          # 异常时回退到的保守值
TEMP_TARGET=98
MARK=/var/log/uv_safeguard.triggered
LOG=/var/log/uv_safeguard.log
CONF_DIR=/var/lib/uv-safeguard
VERDICT_FILE=$CONF_DIR/verdict
STRIKE_FILE=$CONF_DIR/watch_strike
STRIKE_WINDOW=$((7 * 24 * 3600))   # strike 有效窗口 7 天

mkdir -p "$(dirname "$MARK")" "$CONF_DIR" 2>/dev/null

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG" 2>/dev/null; }

write_verdict() {  # write_verdict <CLEAN|WATCH|CRASH_REVERT|STRIKE_REVERT|SKIP> [详情]
    # 格式自描述（KEY=VAL），消费方用 awk -F'=' 读字段，不受详情字段数量影响
    echo "ts=$(date '+%Y-%m-%d %H:%M:%S')"
    echo "verdict=$1"
    echo "boot=${PREV_BOOT:-?}"
    echo "boot_id=${PREV_BID:-unknown}"
    echo "detail=${2:-}"
} > "$VERDICT_FILE" 2>/dev/null

# 当前 boot 的 index（journalctl 中当前总是 0，上一次为 -1）
CUR_BOOT=$(journalctl --list-boots --no-pager 2>/dev/null | tail -1 | awk '{print $1}')
PREV_BOOT=$((CUR_BOOT - 1))

# 首次安装：至少要有 2 条 boot 记录才能比较（当前 + 上一次）
# 注意: CUR_BOOT=0 是【正常值】(当前启动恒为 0)，不能用作"首次运行"判据。
BOOT_COUNT=$(journalctl --list-boots --no-pager 2>/dev/null | grep -cE '^\s*-?[0-9]+ ')
if [ "${BOOT_COUNT:-0}" -lt 2 ]; then
    log "启动记录不足 2 条（首次安装或 journal 被清空），跳过检查"
    write_verdict SKIP "boot_count=${BOOT_COUNT:-0}"
    exit 0
fi
# 校验上一次启动的 journal 可读
if [ -z "$(journalctl -b "$PREV_BOOT" --no-pager 2>/dev/null | head -1)" ]; then
    log "上一次启动(${PREV_BOOT}) 的 journal 不可读，跳过检查"
    write_verdict SKIP "journal_unreadable"
    exit 0
fi

# ---------- P1-1: 三级判定（纯函数，供单测 mock） ----------
# stdout: CLEAN | CRASH | SUSPECT
verdict_last_boot() {
    local last
    # 1) 系统级关机序列（journal 尾部）
    #    注意特征必须限定系统级来源:
    #      systemd-shutdown[N]  — 关机专用进程，只会系统级出现
    #      Journal stopped      — journald 收 SIGTERM 后的最后遗言（系统级）
    #      systemd[1] 限定的 Shutdown/Reboot target
    #    不用裸 "Reached target.*Shutdown": 用户级 systemd[1339] 也会打印
    #    "Reached target shutdown.target - Shutdown."（2026-09-04 boot -1 实测）
    last=$(journalctl -b "$PREV_BOOT" --no-pager 2>/dev/null | tail -20)
    if echo "$last" | grep -qE 'systemd-shutdown\[|Journal stopped|systemd\[1\].*(Reached target.*(Shutdown|Reboot)|Powering off|Rebooting)'; then
        echo CLEAN; return
    fi
    # 2) 崩溃特征（内核日志；噪声过滤与 P0-1 mce_cnt 回退路径同款）
    if journalctl -b "$PREV_BOOT" -k --no-pager 2>/dev/null \
        | grep -iE 'kernel panic|oops|BUG:|general protection fault|machine check|hardware error|mce.*bank|soft lockup|NVRM: Xid' \
        | grep -ivE 'mcelog|rasdaemon|event enabled|hash matches|aer|pcie|dellp|undervolt|write to unrecognized' \
        | grep -q .; then
        echo CRASH; return
    fi
    # 3) 两者皆无 → 疑似手动重启（长按电源/断电/复位）
    echo SUSPECT
}

# 上次启动持续时长（供日志参考）
PREV_INFO=$(journalctl --list-boots --no-pager 2>/dev/null | awk -v b="$PREV_BOOT" '$1==b {print $5, $6, $7, $8}')
# 上次启动的绝对 boot ID（跨重启唯一；strike 防重复计数必须用它 ——
# boot 索引是相对值，每次开机时 PREV_BOOT 恒为 -1，无法区分是否同一事件）
PREV_BID=$(journalctl --list-boots --no-pager 2>/dev/null | awk -v b="$PREV_BOOT" '$1==b {print $2}')

V=$(verdict_last_boot)

# ---------- 回退动作（CRASH / 二次 SUSPECT 共用） ----------
revert_and_mark() {  # revert_and_mark <原因>
    log "⚠️ 回退 -${SAFE_MV}mV（原因: $1；上次启动信息: ${PREV_INFO}）"

    # 读取当前配置值（供回退后对照）
    CUR_MV=$(grep -o -- '--core [-0-9]*' /etc/systemd/system/undervolt.service 2>/dev/null | awk '{print $2}')

    undervolt --core "-$SAFE_MV" --cache "-$SAFE_MV" --gpu "-$SAFE_MV" --temp "$TEMP_TARGET" 2>/dev/null
    sleep 1
    ACTUAL=$(undervolt --read 2>/dev/null | awk '/^core:/{print $2}')
    log "   已回退: 目标 -${SAFE_MV}mV，实测 ${ACTUAL}mV（原配置 ${CUR_MV}mV）"
    rm -f "$STRIKE_FILE" 2>/dev/null   # 已升级处理，strike 翻篇（用户清 triggered 时一并干净）

    {
        echo "=============================================="
        echo " 降压安全网已触发 — $(date '+%Y-%m-%d %H:%M:%S')"
        echo "=============================================="
        echo ""
        echo "检测到上次启动(${PREV_BOOT}) 未正常结束 → 判定为异常关机。"
        echo "触发原因: $1"
        echo "已自动将降压回退到保守值 -${SAFE_MV}mV（实测 ${ACTUAL}mV）。"
        echo "原持久化配置值为 ${CUR_MV}mV。"
        echo ""
        echo "【这意味着什么】"
        echo "  若此前 -100mV 运行期间无任何异常，可能是掉电/长按电源等外部原因，"
        echo "  回退是保守动作，可自行恢复 -100mV："
        echo "      sudo systemctl restart undervolt"
        echo ""
        echo "  若回退后仍反复触发本标记，则应维持 -${SAFE_MV}mV，"
        echo "  并检查: sudo ras-mc-ctl --summary   # 看 MCE 段（No MCE errors = 正常；PCIe AER 不算）"
        echo ""
        echo "【恢复 -100mV 之前请确认】"
        echo "  1. MCE 计数为 0:  sudo ras-mc-ctl --summary | grep -A2 'MCE records'"
        echo "     （2026-09-04 P0-1 注: 旧命令 'dmesg | grep -ci mce' 会把 mcelog 注册行/AER 误计入，已弃用）"
        echo "  2. 系统已连续稳定运行数小时"
        echo ""
        echo "【人工交叉核对（可选）】"
        echo "  journalctl -b $PREV_BOOT -n 20    # 上次日志末尾"
        echo "  last -x reboot shutdown           # wtmp 账本"
        echo ""
        echo "确认无误后可删除本标记文件："
        echo "  sudo rm -f $MARK"
        echo "=============================================="
    } > "$MARK" 2>/dev/null
    log "   标记文件已写入: $MARK"

    # 桌面通知（若有用户会话）
    if command -v notify-send >/dev/null 2>&1; then
        for u in $(users 2>/dev/null | tr ' ' '\n' | sort -u); do
            uid=$(id -u "$u" 2>/dev/null) || continue
            sudo -u "$u" DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
                notify-send "降压安全网已触发" "检测到异常关机（$1），已回退到 -${SAFE_MV}mV。详见 $MARK" 2>/dev/null
        done
    fi
}

# ---------- 主流程: 按 verdict 分派 ----------
case "$V" in
    CLEAN)
        log "上次启动(${PREV_BOOT}) 正常结束（系统级关机序列），无需回退"
        write_verdict CLEAN "boot=${PREV_BOOT}"
        rm -f "$STRIKE_FILE" 2>/dev/null   # 正常翻篇: 清除 watch strike
        # 若存在旧的触发标记，说明用户已确认过，保留供查阅（不自动删）
        exit 0
        ;;
    CRASH)
        write_verdict CRASH_REVERT "boot=${PREV_BOOT} 崩溃特征命中"
        revert_and_mark "崩溃特征（panic/oops/MCE/lockup）—— 高置信硬死机"
        exit 0
        ;;
    SUSPECT)
        NOW=$(date +%s)
        # strike 文件格式: "<unix_ts> <boot_id>"（P1-1 修正: 用绝对 boot_id 防同事件重复计数 ——
        # 同一异常 boot 的重判（服务重跑/手工补跑）只刷新时间不升级；
        # 不同 boot 的新异常事件且在 7 天窗口内 → 升级回退）
        STRIKE_LINE=$(cat "$STRIKE_FILE" 2>/dev/null)
        OLD_TS=$(echo "$STRIKE_LINE" | awk '{print $1}')
        OLD_BID=$(echo "$STRIKE_LINE" | awk '{print $2}')
        OLD_TS=${OLD_TS:-0}
        AGE=$((NOW - OLD_TS))
        if [ "$OLD_TS" -gt 0 ] && [ "$AGE" -lt "$STRIKE_WINDOW" ] && [ "$OLD_BID" != "${PREV_BID:-}" ]; then
            # 7 天内另一 boot 的第二次疑似异常 → 升级回退
            write_verdict STRIKE_REVERT "boot=${PREV_BOOT} 二次疑似异常（上次 strike ${AGE}s 前，boot_id ${OLD_BID}→${PREV_BID}）"
            revert_and_mark "7 天内第 2 次无关机序列且无崩溃特征 —— 反复异常升级回退"
        elif [ "$OLD_TS" -gt 0 ] && [ "$OLD_BID" = "${PREV_BID:-}" ]; then
            # 同一 boot 重判（uv-safeguard 服务重跑/手工补跑）→ 保持 WATCH，不重复计数
            write_verdict WATCH "boot=${PREV_BOOT} 同 boot 重判（strike 保持，不重复计数）"
            log "🟡 同一 boot_id(${PREV_BID}) 重判，保持 WATCH 不升级"
        else
            # 首次（或上次 strike 已过期）→ 仅记 strike，不回退
            echo "$NOW ${PREV_BID:-unknown}" > "$STRIKE_FILE" 2>/dev/null
            write_verdict WATCH "boot=${PREV_BOOT} 疑似手动重启 strike=1/2"
            log "🟡 上次启动(${PREV_BOOT}) 无关机序列但无崩溃特征 → 疑似手动重启，本次不回退（strike 1/2，7 天内再触发将回退）"
            # 轻量提醒（normal 级，非 critical）
            if command -v notify-send >/dev/null 2>&1; then
                for u in $(users 2>/dev/null | tr ' ' '\n' | sort -u); do
                    uid=$(id -u "$u" 2>/dev/null) || continue
                    sudo -u "$u" DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
                        notify-send "降压安全网（观察）" "上次关机无崩溃证据，判定疑似手动重启，未回退降压（-100mV 保持）。若非本人操作请检查系统。" 2>/dev/null
                done
            fi
        fi
        exit 0
        ;;
    *)
        # verdict_last_boot 输出异常（不应发生）→ 按 SUSPECT 处理会更安全，
        # 但宁可保守不误回退: 记 SKIP 供人工查看
        log "verdict_last_boot 返回异常值 '$V'，跳过"
        write_verdict SKIP "verdict_invalid=$V"
        exit 0
        ;;
esac
