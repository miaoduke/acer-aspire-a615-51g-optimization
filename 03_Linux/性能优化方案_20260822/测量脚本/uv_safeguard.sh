#!/bin/bash
# =============================================================================
# uv_safeguard.sh — 降压安全网：异常关机后自动回退保守值
# =============================================================================
# 为什么需要它（2026-08-30）：
#   -80mV 持久化后，undervolt.service 写死 -80mV。若后续因降压导致硬死机，
#   重启后会再次应用 -80mV → 可能陷入「死机→重启→又死机」的循环，
#   而本项目硬死机【无 pstore 转储】，排查困难。
#   本脚本在开机时检测上次是否异常关机（硬死机/掉电），若是则自动回退到
#   保守值 -50mV 并留下标记文件，供用户判断。
#
# 安装（一次性，需 root）：
#   sudo cp uv_safeguard.sh /usr/local/bin/ && sudo chmod +x /usr/local/bin/uv_safeguard.sh
#   sudo cp uv-safeguard.service /etc/systemd/system/
#   sudo systemctl daemon-reload && sudo systemctl enable uv-safeguard.service
#
# 逻辑：
#   · 上次启动以 systemd-shutdown / Journal stopped 正常结束 → 不动作
#   · 上次启动戛然而止（无正常关机序列）→ 判定异常 → 回退 -50mV + 写标记
#   · 标记文件：/var/log/uv_safeguard.triggered（用户确认稳定后删除）
#
# 回退后如何恢复 -80mV：
#   sudo systemctl restart undervolt     （或手动 undervolt --core -80 ...）
# =============================================================================

set -u

SAFE_MV=50          # 异常时回退到的保守值
TEMP_TARGET=98
MARK=/var/log/uv_safeguard.triggered
LOG=/var/log/uv_safeguard.log
CONF_DIR=/var/lib/uv-safeguard

mkdir -p "$(dirname "$MARK")" "$CONF_DIR" 2>/dev/null

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG" 2>/dev/null; }

# 当前 boot 的 index（journalctl 中当前总是 0，上一次为 -1）
CUR_BOOT=$(journalctl --list-boots --no-pager 2>/dev/null | tail -1 | awk '{print $1}')
PREV_BOOT=$((CUR_BOOT - 1))

# 首次安装：至少要有 2 条 boot 记录才能比较（当前 + 上一次）
# 注意: CUR_BOOT=0 是【正常值】(当前启动恒为 0)，不能用作"首次运行"判据。
BOOT_COUNT=$(journalctl --list-boots --no-pager 2>/dev/null | grep -cE '^\s*-?[0-9]+ ')
if [ "${BOOT_COUNT:-0}" -lt 2 ]; then
    log "启动记录不足 2 条（首次安装或 journal 被清空），跳过检查"
    exit 0
fi
# 校验上一次启动的 journal 可读
if [ -z "$(journalctl -b "$PREV_BOOT" --no-pager 2>/dev/null | head -1)" ]; then
    log "上一次启动(${PREV_BOOT}) 的 journal 不可读，跳过检查"
    exit 0
fi

# ---------- 判断上次是否正常关机 ----------
# 正常关机特征：journal 末尾出现 systemd-shutdown 或 "Journal stopped"
LAST_LINES=$(journalctl -b "$PREV_BOOT" --no-pager 2>/dev/null | tail -20)
if echo "$LAST_LINES" | grep -qE "systemd-shutdown|Journal stopped|Reached target.*Shutdown|Powering off|Rebooting"; then
    NORMAL_SHUTDOWN=1
else
    NORMAL_SHUTDOWN=0
fi

# 上次启动持续时长（过短可能是反复重启）
PREV_INFO=$(journalctl --list-boots --no-pager 2>/dev/null | awk -v b="$PREV_BOOT" '$1==b {print $5, $6, $7, $8}')

if [ "$NORMAL_SHUTDOWN" = "1" ]; then
    log "上次启动(${PREV_BOOT}) 正常结束，无需回退"
    # 若存在旧的触发标记，说明用户已确认过，保留供查阅（不自动删）
    exit 0
fi

# ---------- 异常：回退保守值 ----------
log "⚠️ 检测到上次启动(${PREV_BOOT}) 未正常结束，判定为异常关机（硬死机/掉电）"
log "   上次启动信息: ${PREV_INFO}"

# 读取当前配置值（供回退后对照）
CUR_MV=$(grep -o -- '--core [-0-9]*' /etc/systemd/system/undervolt.service 2>/dev/null | awk '{print $2}')

undervolt --core "-$SAFE_MV" --cache "-$SAFE_MV" --gpu "-$SAFE_MV" --temp "$TEMP_TARGET" 2>/dev/null
sleep 1
ACTUAL=$(undervolt --read 2>/dev/null | awk '/^core:/{print $2}')

log "   已回退: 目标 -${SAFE_MV}mV，实测 ${ACTUAL}mV（原配置 ${CUR_MV}mV）"

{
    echo "=============================================="
    echo " 降压安全网已触发 — $(date '+%Y-%m-%d %H:%M:%S')"
    echo "=============================================="
    echo ""
    echo "检测到上次启动(${PREV_BOOT}) 未正常结束 → 判定为异常关机。"
    echo "已自动将降压回退到保守值 -${SAFE_MV}mV（实测 ${ACTUAL}mV）。"
    echo "原持久化配置值为 ${CUR_MV}mV。"
    echo ""
    echo "【这意味着什么】"
    echo "  若此前 -80mV 运行期间无任何异常，可能是掉电/长按电源等外部原因，"
    echo "  回退是保守动作，可自行恢复 -80mV："
    echo "      sudo systemctl restart undervolt"
    echo ""
    echo "  若回退后仍反复触发本标记，则应维持 -${SAFE_MV}mV，"
    echo "  并检查: dmesg | grep -ci mce"
    echo ""
    echo "【恢复 -80mV 之前请确认】"
    echo "  1. MCE 计数为 0:  dmesg | grep -ci mce"
    echo "  2. 系统已连续稳定运行数小时"
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
            notify-send "降压安全网已触发" "检测到异常关机，已回退到 -${SAFE_MV}mV。详见 $MARK" 2>/dev/null
    done
fi

exit 0
