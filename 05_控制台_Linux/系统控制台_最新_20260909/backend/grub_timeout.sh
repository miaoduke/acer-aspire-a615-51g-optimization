#!/bin/bash
# =============================================================================
# grub_timeout.sh — GRUB 启动菜单时间设置（GUI 白名单落点，2026-09-11 新增）
# 改编自交互式工具《设置GRUB启动时间.sh》：参数化非交互版, 供控制台高级页调用
# =============================================================================
# 用法: sudo grub_timeout.sh <seconds> <menu|hidden>
#   seconds: 0=直接启动 / 任意非负整数
#   menu|hidden: 显示菜单 / 隐藏仅倒计时
# 安全设计（与原工具一致）:
#   · 备份 /etc/default/grub → .grubtime.bak（还原: cp 回去 + update-grub）
#   · GRUB_RECORDFAIL_TIMEOUT 同步, 避免异常关机后回退 30 秒默认
#   · 写入后 update-grub 重新生成 cfg, 并 grep 校验主段 timeout
# 退出码: 0=成功 / 1=参数拒绝 / 2=写入或校验失败
# =============================================================================
set -eu
GRUB_DEFAULT_CFG=/etc/default/grub
BAK="${GRUB_DEFAULT_CFG}.grubtime.bak"

[ $# -eq 2 ] || { echo "用法: grub_timeout.sh <seconds> <menu|hidden>"; exit 1; }
TIMEOUT=$1; STYLE=$2
[[ "$TIMEOUT" =~ ^[0-9]+$ ]] || { echo "❌ 秒数须为非负整数: $TIMEOUT"; exit 1; }
[ "$TIMEOUT" -le 300 ] || { echo "❌ 秒数过大(≤300): $TIMEOUT"; exit 1; }
case "$STYLE" in menu|hidden) ;; *) echo "❌ style 须为 menu|hidden: $STYLE"; exit 1;; esac

[ -f "$GRUB_DEFAULT_CFG" ] || { echo "❌ 未找到 $GRUB_DEFAULT_CFG(非 GRUB2 引导?)"; exit 2; }
command -v update-grub >/dev/null 2>&1 || command -v grub-mkconfig >/dev/null 2>&1 \
    || { echo "❌ 无 update-grub/grub-mkconfig"; exit 2; }

cp -f "$GRUB_DEFAULT_CFG" "$BAK"

set_grub_val() {
    if grep -q "^${1}=" "$GRUB_DEFAULT_CFG"; then
        sed -i "s/^${1}=.*/${1}=${2}/" "$GRUB_DEFAULT_CFG"
    else
        echo "${1}=${2}" >> "$GRUB_DEFAULT_CFG"
    fi
}
set_grub_val GRUB_TIMEOUT "$TIMEOUT"
set_grub_val GRUB_TIMEOUT_STYLE "$STYLE"
set_grub_val GRUB_RECORDFAIL_TIMEOUT "$TIMEOUT"

if command -v update-grub >/dev/null 2>&1; then
    update-grub >/dev/null 2>&1 || grub-mkconfig -o /boot/grub/grub.cfg >/dev/null 2>&1 || true
else
    grub-mkconfig -o /boot/grub/grub.cfg >/dev/null 2>&1 || true
fi

GEN=$(grep -aiE "^ *set timeout=" /boot/grub/grub.cfg 2>/dev/null | head -1 | grep -oE "[0-9]+$" || echo "")
[ "$GEN" = "$TIMEOUT" ] || { echo "❌ cfg 校验失败(生成值 $GEN ≠ $TIMEOUT), 备份: $BAK"; exit 2; }

echo "✓ GRUB_TIMEOUT=$TIMEOUT / STYLE=$STYLE / RECORDFAIL=$TIMEOUT"
echo "还原: sudo cp $BAK /etc/default/grub && sudo update-grub"
