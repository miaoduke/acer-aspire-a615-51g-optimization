#!/bin/bash
# =============================================================================
# try_user_profile.sh — 用户试用自定义 profile 工具
# =============================================================================
# 用途: 让用户在不动生产配置的情况下，体验"创建自定义 profile"
# 流程: 在 /tmp/ 临时目录创建 profile，验证是否被 loader 识别
# 安全: 完全无破坏性，不修改任何 /etc 或 ~/.config 文件
# 清理: 脚本末尾自动清理 /tmp/test_user_profile
# =============================================================================

set -e

TEMP_PROFILE_DIR="/tmp/test_user_profile"
SAMPLE_PROFILE="my_test_scene"

echo "============================================================"
echo "用户自定义 profile 试用工具"
echo "============================================================"
echo ""

# 1. 创建临时目录 + 复制内置 balanced（单目录模式下 include 需基类在同目录）
mkdir -p "$TEMP_PROFILE_DIR/$SAMPLE_PROFILE"
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [ -d "$APP_DIR/profiles/balanced" ]; then
    cp -r "$APP_DIR/profiles/balanced" "$TEMP_PROFILE_DIR/balanced"
fi
echo "[1/4] 创建临时目录: $TEMP_PROFILE_DIR/$SAMPLE_PROFILE（含内置 balanced 基类）"

# 2. 写示例 profile
cat > "$TEMP_PROFILE_DIR/$SAMPLE_PROFILE/tuned.conf" << 'EOF'
[main]
summary=试用场景 — 继承 balanced + 略高 PL
include=balanced
version=1

[cpu]
# 覆盖：从 balanced.powersave 改为 performance
governor=performance
# 覆盖：从 balanced.15 改为 20
pl1_watts=20
# 保留：turbo=1 继承自 balanced
EOF
echo "[2/4] 写示例 profile: $SAMPLE_PROFILE"
echo ""

# 3. 验证
echo "[3/4] 验证 profile..."
python3 src/core/profile.py --dir "$TEMP_PROFILE_DIR" --validate "$SAMPLE_PROFILE"
echo ""

# 4. 显示完整内容
echo "[4/4] 显示完整内容（合并后）..."
python3 src/core/profile.py --dir "$TEMP_PROFILE_DIR" --show "$SAMPLE_PROFILE"
echo ""

echo "============================================================"
echo "✓ 试用完成！"
echo "============================================================"
echo ""
echo "实际效果："
echo "  - 你可以在 ~/.config/system-console/profiles/<name>/tuned.conf 创建真实自定义 profile"
echo "  - loader 会优先用用户目录，fallback 到内置，再 fallback 到硬编码"
echo "  - GUI 会在'电源场景'页底部显示你创建的所有 profile（标 👤）"
echo ""
echo "清理临时文件..."
rm -rf "$TEMP_PROFILE_DIR"
echo "✓ 已清理 $TEMP_PROFILE_DIR"
