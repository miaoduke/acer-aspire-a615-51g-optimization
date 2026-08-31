#!/bin/bash
# 03_GRUB性能参数.sh — 优化内核启动参数(交互式)
# 需要 root 权限
# 修正: 提供"性能/省电"两档,解决 max_cstate=1 与离电省电(C10)的永久冲突

GRUB_CFG=/etc/default/grub

echo "=== 当前 GRUB 配置 ==="
grep CMDLINE "$GRUB_CFG"
echo ""

echo "=== 选择优化档位 ==="
echo "  1) 性能档: mitigations=off (低延迟,牺牲安全)"
echo "  2) 省电档: 保持C-State深度(与离电省电场景兼容),仅关mitigations(可选)"
echo "  3) 恢复备份"
echo ""
echo "注: 2026-08-18 调研结论——intel_idle.max_cstate=1 不再推荐"
echo "    (Bugzilla 109051 为 Bay Trail 专属 bug, 不适用 KBL-R; 撤销实验见观察期日志)"
read -r -p "请输入 [1/2/3]: " CHOICE

case "$CHOICE" in
    1)
        NEW_CMD="quiet splash intel_pstate=active mitigations=off"
        echo ""
        echo "⚠️ 安全警告: mitigations=off 会关闭 Spectre/Meltdown 等缓解措施(+5-10%性能)"
        read -r -p "确定使用性能档? [y/N] " yn
        [ "$yn" != "y" ] && [ "$yn" != "Y" ] && { echo "已取消"; exit 0; }
        ;;
    2)
        echo ""
        read -r -p "是否同时关闭 mitigations(+5-10%性能,有安全风险)? [y/N] " yn
        if [ "$yn" = "y" ] || [ "$yn" = "Y" ]; then
            NEW_CMD="quiet splash intel_pstate=active mitigations=off"
        else
            NEW_CMD="quiet splash intel_pstate=active"
        fi
        echo "⚠️ 省电档: 保留深度C-State(如 C7s/C10),适合离电场景;intel_pstate 已为 active,无需改动亦可"
        ;;
    3)
        if [ -f "$GRUB_CFG.bak" ]; then
            cp "$GRUB_CFG.bak" "$GRUB_CFG"
            echo "✓ 已从备份恢复"
        else
            echo "未找到备份 $GRUB_CFG.bak"
        fi
        update-grub 2>/dev/null || sudo update-grub
        exit 0
        ;;
    *)
        echo "无效选择"
        exit 1
        ;;
esac

echo ""
echo "=== 执行 ==="
[ ! -f "$GRUB_CFG.bak" ] && cp "$GRUB_CFG" "$GRUB_CFG.bak" && echo "✓ 已备份 → $GRUB_CFG.bak"

if grep -q '^GRUB_CMDLINE_LINUX_DEFAULT=' "$GRUB_CFG"; then
    sed -i "s|^GRUB_CMDLINE_LINUX_DEFAULT=.*|GRUB_CMDLINE_LINUX_DEFAULT=\"$NEW_CMD\"|" "$GRUB_CFG"
else
    echo "GRUB_CMDLINE_LINUX_DEFAULT=\"$NEW_CMD\"" >> "$GRUB_CFG"
fi
echo "✓ 已写入: GRUB_CMDLINE_LINUX_DEFAULT=\"$NEW_CMD\""

echo ""
update-grub 2>/dev/null || sudo update-grub

echo ""
echo "=== 参数说明 ==="
echo "intel_pstate=active    : 强制 HWP 主动模式(本机已是active,冗余但无害)"
echo "mitigations=off        : 关闭安全补丁缓解(+5-10%性能)"
echo "C-State 限制(max_cstate=1)已移除: 2026-08-18 调研结论不适用本机, 见观察期日志_撤销cstate_20260818.md"
echo ""
echo "重启后生效: sudo reboot"
echo "恢复: 运行本脚本选 3,或手动编辑 $GRUB_CFG"