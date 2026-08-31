#!/bin/bash
# ============================================================
# 调研行动 2026-08-18：撤销 max_cstate=1 实验 + 安装 rasdaemon
# 依据：调研文档_当前方案科学评估_20260818.md
#   - Bugzilla 109051 为 Bay Trail 专属，不适用本机（KBL-R）
#   - max_cstate=1 未阻止死机 #5/#6，且代价 +2.25W 待机
#   - 撤销后进入观察期（3-5 天），kernel.panic=10 兜底
# 用法：sudo bash 调研行动_20260818.sh
# ============================================================

set -e
TS=$(date +%Y%m%d_%H%M%S)
GRUB_CONF=/etc/default/grub

echo "==== 调研行动 2026-08-18 ===="
echo "时间戳: $TS"
echo

# ---------- [1/3] 撤销 intel_idle.max_cstate=1 ----------
echo "[1/3] 撤销 intel_idle.max_cstate=1（GRUB）"

if grep -q "intel_idle.max_cstate=1" "$GRUB_CONF"; then
    cp "$GRUB_CONF" "${GRUB_CONF}.bak_${TS}"
    echo "  -> 已备份: ${GRUB_CONF}.bak_${TS}"
    sed -i 's/ intel_idle.max_cstate=1//g' "$GRUB_CONF"
    echo "  -> 已移除内核参数 intel_idle.max_cstate=1"
else
    echo "  -> 未找到该参数，跳过（幂等）"
fi

echo "  当前 CMDLINE:"
grep "^GRUB_CMDLINE_LINUX_DEFAULT" "$GRUB_CONF"

echo "  执行 update-grub ..."
update-grub 2>&1 | tail -3

echo
# ---------- [2/3] 安装并启用 rasdaemon（MCE 事件落盘） ----------
echo "[2/3] 安装并启用 rasdaemon"

if command -v rasdaemon >/dev/null 2>&1; then
    echo "  -> rasdaemon 已安装，跳过安装"
else
    apt-get install -y rasdaemon
fi
systemctl enable --now rasdaemon 2>&1 | tail -2
systemctl is-active rasdaemon

echo
# ---------- [3/3] 状态确认 ----------
echo "[3/3] 状态确认"
echo "  系统: $(uname -r)"
echo "  GRUB: $(grep '^GRUB_CMDLINE_LINUX_DEFAULT' "$GRUB_CONF")"
echo "  rasdaemon: $(systemctl is-active rasdaemon)"
echo
echo "================================================"
echo "  完成。下一步："
echo "  1. 重启生效: sudo reboot"
echo "  2. 重启后确认 C-state 恢复:"
echo "     cat /sys/module/intel_idle/parameters/max_cstate   # 应为 9"
echo "  3. 进入观察期 3-5 天，记录到:"
echo "     性能优化方案/观察期日志_撤销cstate_20260818.md"
echo "  4. 待机功耗对比（预期省 ~2.25W）:"
echo "     独显空闲 23.7W -> 预期 ~21.4W"
echo "================================================"