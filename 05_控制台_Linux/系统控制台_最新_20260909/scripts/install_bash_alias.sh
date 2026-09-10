#!/bin/bash
# install_bash_alias.sh — P2-C: 安装 syscon 别名到 ~/.bashrc
# 用法: bash scripts/install_bash_alias.sh

set -e

BASHRC="$HOME/.bashrc"
APP_DIR="$HOME/.local/share/系统控制台"

# 标记（避免重复添加）
MARKER="# >>> system-console alias >>>"
END_MARKER="# <<< system-console alias <<<"

# 检查是否已安装
if grep -q "$MARKER" "$BASHRC" 2>/dev/null; then
    echo "✓ syscon 别名已存在"
    exit 0
fi

# 添加 alias
cat >> "$BASHRC" << EOF

$MARKER
# 启动控制台
alias syscon='python3 $APP_DIR/console.py'
# 健康检查
alias syscon-check='bash $APP_DIR/scripts/phase1_health_check.sh'
# 状态快照
alias syscon-snap='python3 $APP_DIR/scripts/snapshot_quick.py'
# 冲突检测
alias syscon-conflict='python3 $APP_DIR/scripts/check_conflicts.py'
# profile 列表
alias syscon-profiles='python3 $APP_DIR/src/core/profile.py --list'
# plugin 列表
alias syscon-plugins='python3 $APP_DIR/src/core/plugin.py --list'
# double-sudo 检测
alias syscon-audit='python3 $APP_DIR/scripts/check_double_sudo.py $APP_DIR'
# 跑全部测试
alias syscon-test='cd $APP_DIR && for t in tests/test_*.py; do python3 "\$t"; done'
# 编辑控制台源码
alias syscon-edit='code $APP_DIR 2>/dev/null || geany $APP_DIR 2>/dev/null || \$EDITOR $APP_DIR'
$END_MARKER
EOF

echo "✓ syscon 别名已添加到 ~/.bashrc"
echo ""
echo "立即生效: source ~/.bashrc"
echo ""
echo "可用命令:"
echo "  syscon              启动 GUI"
echo "  syscon-check        健康检查"
echo "  syscon-snap         状态快照"
echo "  syscon-conflict     互斥工具检测"
echo "  syscon-profiles     profile 列表"
echo "  syscon-plugins      plugin 列表"
echo "  syscon-audit        double-sudo 检测"
echo "  syscon-test         跑全部测试"
echo "  syscon-edit         编辑源码"
