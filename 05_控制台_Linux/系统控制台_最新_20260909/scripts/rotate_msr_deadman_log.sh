#!/bin/bash
# =============================================================================
# rotate_msr_deadman_log.sh — P1-3: MSR deadman 日志轮转
# =============================================================================
# 目的: 防止 /var/log/msr_deadman.log 无限增长
# 策略: 保留 7 天 + 压缩 30 天 + 清理 > 30 天
# 频率: 每日 1 次（用户手动或 cron）
# =============================================================================

set -e

LOG="/var/log/msr_deadman.log"
MAX_SIZE_MB=5
KEEP_DAYS=30

if [ ! -f "$LOG" ]; then
    echo "$(date '+%F %T') 日志不存在: $LOG" >&2
    exit 0
fi

# 1. 大小检查
SIZE_MB=$(du -m "$LOG" 2>/dev/null | awk '{print $1}')
if [ "${SIZE_MB:-0}" -gt "$MAX_SIZE_MB" ]; then
    # 轮转
    TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
    mv "$LOG" "${LOG}.${TIMESTAMP}"
    gzip "${LOG}.${TIMESTAMP}" 2>/dev/null || true
    touch "$LOG"
    echo "$(date '+%F %T') 轮转: ${LOG}.${TIMESTAMP}.gz"
fi

# 2. 清理 > 30 天的轮转文件
DELETED=$(find "$(dirname "$LOG")" -name "msr_deadman.log.*.gz" -mtime +${KEEP_DAYS} -delete -print 2>/dev/null | wc -l)
if [ "$DELETED" -gt 0 ]; then
    echo "$(date '+%F %T') 清理 ${DELETED} 个 > ${KEEP_DAYS} 天的旧日志"
fi

# 3. 当前状态
if [ -f "$LOG" ]; then
    SIZE=$(du -h "$LOG" | awk '{print $1}')
    LINES=$(wc -l < "$LOG")
    echo "$(date '+%F %T') 当前: $SIZE / $LINES 行"
fi
