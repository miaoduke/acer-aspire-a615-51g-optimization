#!/bin/bash
# =============================================================================
# check_ctl_consistency.sh — thermal_ctl.sh 分支 ↔ controller.py 调用方 一致性检查
# =============================================================================
# 背景: 本项目曾出现"UI/controller 已调用某子命令, 但后端脚本无对应分支"的缺陷
#        (pl / camera 两个控件点了必失败), 且 controller docstring 还声称支持。
#        本脚本把该缺陷转为可自动检出项, 防止再次发生。
#
# 用法:
#   bash backend/check_ctl_consistency.sh                     # 检查本包源码副本
#   bash backend/check_ctl_consistency.sh /usr/local/bin/thermal_ctl.sh \
#                                         /path/to/controller.py
#                                                             # 检查真机部署副本
#        (部署副本可能与源码不同版本 —— 用它可确认真机实际能力)
#
# 退出码: 0=一致  1=发现缺失分支  2=用法/文件错误
# =============================================================================
set -u

DIR="$(cd "$(dirname "$0")" && pwd)"
CTL="${1:-$DIR/thermal_ctl.sh}"
PY="${2:-$DIR/../controller.py}"

[ -f "$CTL" ] || { echo "错误: 找不到 thermal_ctl.sh: $CTL" >&2; exit 2; }
[ -f "$PY" ]  || { echo "错误: 找不到 controller.py: $PY" >&2; exit 2; }

echo "=== thermal_ctl 一致性检查 ==="
echo "后端脚本: $CTL"
echo "控制层  : $PY"
echo ""

# 后端实际实现的分支(顶层 case, 形如 "  分支名)")
BRANCHES=$(grep -oE '^  [a-z_0-9]+\)' "$CTL" | tr -d ' )' | sort -u)
# controller 实际调用的子命令(形如 thermal("xxx")
CALLS=$(grep -oE 'thermal\("[a-z_0-9]+"' "$PY" | sed 's/thermal("//; s/"//' | sort -u)

if [ -z "$BRANCHES" ]; then
    echo "⚠ 未从后端提取到任何分支 —— 检查脚本的分支缩进格式是否为两空格" >&2
    exit 2
fi

echo "后端分支 ($(echo "$BRANCHES" | wc -l | tr -d ' ')):"
echo "$BRANCHES" | sed 's/^/    /' | tr '\n' ' '; echo; echo

echo "控制层调用 ($(echo "$CALLS" | wc -l | tr -d ' ')):"
echo "$CALLS" | sed 's/^/    /' | tr '\n' ' '; echo; echo

# 差集: 被调用但后端未实现
MISSING=$(comm -13 <(echo "$BRANCHES") <(echo "$CALLS") | grep -v '^$')
# 差集: 已实现但无人调用(仅提示, 不算错误)
UNUSED=$(comm -23 <(echo "$BRANCHES") <(echo "$CALLS") | grep -v '^$')

RC=0
if [ -n "$MISSING" ]; then
    echo "❌ 缺失分支 (controller 调用但后端未实现 —— 对应 UI 控件点了必失败):"
    echo "$MISSING" | sed 's/^/    ✗ /'
    RC=1
else
    echo "✅ 无缺失分支: 所有被调用的子命令后端均已实现"
fi

if [ -n "$UNUSED" ]; then
    echo ""
    echo "ℹ 未被调用 (后端已实现但 controller 未使用 —— 可能是预留或遗留):"
    echo "$UNUSED" | sed 's/^/    · /'
fi

echo ""
if [ "$RC" -eq 0 ]; then
    echo "=== 检查通过 ==="
else
    echo "=== 检查失败: 请补全 thermal_ctl.sh 分支, 或移除对应的 UI 控件 ==="
fi
exit $RC
