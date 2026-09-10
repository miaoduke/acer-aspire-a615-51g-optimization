#!/bin/bash
# =============================================================================
# msr_deadman.sh — A-S3 实施: MSR 降压安全网 deadman switch
# =============================================================================
# 目的: 实时监控 CPU 温度，若超阈值且降压深度 >= -80mV，自动回退到 -50mV
#       防止"深降压 → 高温 → 死机"的循环
# 触发: 通过 systemd timer 每 30s 巡检
# 安全: 仅 root 运行；写 MSR 严格走 /usr/local/bin/undervolt 工具
# 安装: sudo cp backend/msr_deadman.sh /usr/local/bin/msr_deadman.sh
#       sudo chmod +x /usr/local/bin/msr_deadman.sh
#       sudo cp backend/msr_deadman.service /etc/systemd/system/
#       sudo cp backend/msr_deadman.timer /etc/systemd/system/
#       sudo systemctl daemon-reload
#       sudo systemctl enable --now msr_deadman.timer
# =============================================================================

set -e

# 配置（可被环境变量覆盖）
HIGH_TEMP=${MSR_DM_HIGH:-95000}    # 95°C 触发
LOW_TEMP=${MSR_DM_LOW:-80000}      # 80°C 恢复
SAFE_MV=${MSR_DM_SAFE:-50}         # 异常时回退到 -50mV
LOG=${MSR_DM_LOG:-/var/log/msr_deadman.log}
TEMP_FILE=/sys/class/thermal/thermal_zone2/temp  # CPU 封装温度

# 当前降压值
CURRENT_MV_FILE=/etc/systemd/system/undervolt.service
LOG_PREFIX="[$(date '+%F %T')]"

# 工具检查
if [ ! -x /usr/local/bin/undervolt ]; then
    echo "$LOG_PREFIX ❌ /usr/local/bin/undervolt 不可用" >> "$LOG"
    exit 1
fi

# 读温度（不可读则退出）
if [ ! -r "$TEMP_FILE" ]; then
    echo "$LOG_PREFIX ⚠ 无法读 $TEMP_FILE" >> "$LOG"
    exit 0
fi
TEMP=$(cat "$TEMP_FILE" 2>/dev/null || echo "0")

# 读当前降压值（从 systemd unit 解析）
CURRENT_MV=$(grep -oE -- '--core -?[0-9]+' "$CURRENT_MV_FILE" 2>/dev/null | head -1 | grep -oE -- '-?[0-9]+$')
if [ -z "$CURRENT_MV" ]; then
    CURRENT_MV=0
fi
CURRENT_MV=${CURRENT_MV#-}  # 去负号

# 状态判定
if [ "$TEMP" -ge "$HIGH_TEMP" ] && [ "$CURRENT_MV" -ge 80 ]; then
    # 触发条件: 高温 + 深降压
    echo "$LOG_PREFIX 🔴 高温 ${TEMP}°C + 降压 -${CURRENT_MV}mV → 回退到 -${SAFE_MV}mV" >> "$LOG"
    /usr/local/bin/undervolt --core "-$SAFE_MV" --cache "-$SAFE_MV" --gpu "-$SAFE_MV" --temp 98 >/dev/null 2>&1 || true
    # 写标记文件供 uv-safeguard 不重复处理
    touch /var/log/msr_deadman.triggered
    # 桌面通知（若可用）
    if command -v notify-send >/dev/null 2>&1; then
        sudo -u "${SUDO_USER:-$(logname 2>/dev/null || echo root)}" \
            DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u "${SUDO_USER:-root}")/bus" \
            notify-send "⚠ 降压已回退" "高温 ${TEMP}°C，降压从 -${CURRENT_MV}mV 回到 -${SAFE_MV}mV" \
            --urgency=critical 2>/dev/null || true
    fi
elif [ "$TEMP" -le "$LOW_TEMP" ] && [ -f /var/log/msr_deadman.triggered ]; then
    # 恢复条件: 温度回落到 LOW + 之前被回退过
    echo "$LOG_PREFIX 🟢 温度回落 ${TEMP}°C，清除 deadman 标记（用户需手动恢复原降压）" >> "$LOG"
    rm -f /var/log/msr_deadman.triggered
fi

exit 0
