#!/bin/bash
# =============================================================================
# sync_and_stamp.sh — 控制台更新后：同步归档 + 更新目录时间戳（一键）
# =============================================================================
# 背景（2026-09-01）：
#   每次改代码后，必须确保 ①归档源码与运行位置一致 ②归档目录名时间戳更新。
#   此前手工执行 deploy.sh + 改目录名，容易遗漏（已多次发生"改了归档没部署"）。
#   本脚本将两件事合一，并自动维护 系统控制台_latest 链接。
#
# 用法：
#   bash sync_and_stamp.sh --dry-run   # 预览要做什么
#   bash sync_and_stamp.sh             # 执行（同步 + 更新时间戳 + 更新链接）
#
# 流程：
#   1. 部署归档 → 运行位置（新代码先进运行位置，或运行位置回填归档）
#   2. 更新归档目录名时间戳为今日（如 _20260822 → _20260901）
#   3. 更新 系统控制台_latest 链接指向新目录
#   4. 校验一致性
# =============================================================================
set -u

# 数据盘挂载点自动探测（WS/WS1 漂移兼容，参考 sync_to_ws1.sh；换机/改名不失效）
R=""
for cand in "$HOME/WS" "$HOME/WS1" /media/<USER>/WS /media/<USER>/WS1; do
  [ -d "$cand/acer 性能优化方案" ] && { R="$cand/acer 性能优化方案"; break; }
done
[ -n "$R" ] || { echo "❌ 找不到归档根（数据盘未挂载？请先 sudo mount ...）"; exit 1; }
CD="$R/05_控制台_Linux"
RUN="$HOME/.local/share/系统控制台"
TODAY=$(date +%Y%m%d)

# 当前归档目录（系统控制台_最新_*）
CUR=$(ls -d "$CD"/系统控制台_最新_* 2>/dev/null | head -1)
[ -n "$CUR" ] || { echo "❌ 找不到归档目录"; exit 1; }
CUR_NAME=$(basename "$CUR")
NEW_NAME="系统控制台_最新_$TODAY"
NEW_DIR="$CD/$NEW_NAME"

DRY=""
[ "${1:-}" = "--dry-run" ] && DRY="dry"

echo "=== 控制台同步 + 时间戳 ==="
echo "运行位置: $RUN"
echo "归档当前: $CUR_NAME"
echo "归档目标: $NEW_NAME"

# ---------- 1. 同步代码（双向：先归档→运行，再运行→归档回填）----------
echo
echo "[1/3] 同步代码..."
if [ "$DRY" = "dry" ]; then
    echo "  (dry) rsync 归档→运行: 排除数据/备份/快照"
else
    # 归档→运行（源码真源推送）
    rsync -a --delete \
        --exclude 'data/perf/' --exclude 'data/battery_usage.json' \
        --exclude 'data/snapshot_log.txt' --exclude 'data/charge_curve_*' \
        --exclude '.deploy_backup_*' --exclude '__pycache__' --exclude '*.pyc' \
        --exclude '20260821_*/' --exclude '20260829_*/' --exclude '会话记录/' \
        "$CUR/" "$RUN/" 2>/dev/null
    echo "  ✅ 归档 → 运行位置"
    # 运行→归档（运行中产生的数据变更回填，如 layout.json 等运行时文件）
    rsync -a "$RUN/" "$CUR/" 2>/dev/null
    echo "  ✅ 运行位置 → 归档"
fi

# ---------- 2. 更新时间戳目录名 ----------
echo
echo "[2/3] 更新目录时间戳..."
if [ "$CUR_NAME" = "$NEW_NAME" ]; then
    echo "  ℹ 时间戳已是今日（$NEW_NAME），无需改名"
else
    if [ "$DRY" = "dry" ]; then
        echo "  (dry) 将改名: $CUR_NAME → $NEW_NAME"
    else
        # 若目标已存在（当日多次运行），先备份旧目标
        if [ -e "$NEW_DIR" ]; then
            mv "$NEW_DIR" "${NEW_DIR}_$(date +%H%M%S)" 2>/dev/null
            echo "  ℹ 旧目标已备份"
        fi
        mv "$CUR" "$NEW_DIR" && echo "  ✅ $CUR_NAME → $NEW_NAME"
    fi
fi

# ---------- 3. 更新 系统控制台_latest 链接 ----------
echo
echo "[3/3] 更新链接..."
LINK="$R/系统控制台_latest"
if [ "$DRY" = "dry" ]; then
    echo "  (dry) ln -sfn 05_控制台_Linux/$NEW_NAME $LINK"
else
    ln -sfn "05_控制台_Linux/$NEW_NAME" "$LINK" && echo "  ✅ 链接已更新: → $NEW_NAME"
fi

# ---------- 4. 校验 ----------
echo
echo "=== 校验 ==="
if [ "$DRY" != "dry" ]; then
    echo "归档: $(ls -d "$CD"/系统控制台_最新_* | xargs -n1 basename)"
    echo "链接: $(readlink "$LINK") → $([ -e "$LINK" ] && echo '✅有效' || echo '❌失效')"
    echo "运行位置文件: $(find "$RUN" -type f | wc -l)"
else
    echo "(dry-run 结束，未做任何修改)"
fi
