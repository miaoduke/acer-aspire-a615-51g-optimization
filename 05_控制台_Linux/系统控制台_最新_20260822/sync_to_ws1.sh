#!/bin/bash
# sync_to_ws1.sh — 控制台同步备份到 WS1（铁律：每次更新桌面控制台后执行）
# 用法: bash sync_to_ws1.sh
# 功能:
#   1. 同步 ~/.local/share/系统控制台 → <数据盘>/AItest/系统控制台_最新_YYYYMMDD/
#      （目录名含日期；日期变化时新建目录，旧的保留为历史）
#      挂载点自动探测(2026-08-30): 盘标签 WS, 但 udisks2 重名时会变成 WS1/WS2,
#      故不再硬编码, 依次尝试 ~/WS ~/WS1 ~/WS2 /media/<USER>/WS /media/<USER>/WS1
#   2. 只保留最近 3 个日期副本，更早的自动清理

SRC="$HOME/.local/share/系统控制台"
TODAY=$(date +%Y%m%d)
KEEP=3

# 自动探测数据盘挂载点(2026-08-30 修正):
# 盘标签为 WS, 但 udisks2 在出现同名挂载点时会自动加序号(WS1/WS2...),
# 历史曾出现过 WS1。硬编码任一个都会在另一次启动时失效。
WS1=""
for cand in "$HOME/WS" "$HOME/WS1" "$HOME/WS2" /media/<USER>/WS /media/<USER>/WS1; do
    if [ -d "$cand/AItest" ]; then
        WS1="$cand/AItest"
        break
    fi
done
# 兜底: 全盘找 AItest(较慢, 仅在上面都没命中时)
if [ -z "$WS1" ]; then
    WS1=$(find /media /mnt /run/media -maxdepth 4 -type d -name AItest 2>/dev/null | head -1)
fi

DEST="$WS1/系统控制台_最新_$TODAY"

[ -d "$SRC" ] || { echo "✗ 源目录不存在: $SRC"; exit 1; }
if [ -z "$WS1" ] || [ ! -d "$WS1" ]; then
    echo "✗ 数据盘未找到(已尝试 WS/WS1/WS2 及全盘搜索): $WS1"
    echo "  请先挂载: sudo mount -t ntfs-3g /dev/sdb1 /media/<USER>/WS"
    exit 1
fi
echo "数据盘: $WS1"

# 同步（-a 保留属性, --delete 使目标与源一致）
mkdir -p "$DEST"
rsync -a --delete \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude='opencode_data' --delete-excluded \
    --exclude 'session' \
    "$SRC/" "$DEST/"

COUNT=$(find "$DEST" -type f | wc -l)
echo "✓ 已同步 $COUNT 个文件 → $DEST"

# 清理旧日期副本（保留最近 KEEP 个）
cd "$WS1" || exit 1
OLD=$(ls -d 系统控制台_最新_* 2>/dev/null | sort -r | tail -n +$((KEEP + 1)))
for d in $OLD; do
    rm -rf "$d"
    echo "🧹 清理旧副本: $d"
done

# 更新 latest 软链接（指向最新）
ln -sfn "$DEST" "$WS1/系统控制台_latest"
echo "✓ 完成（$(date '+%F %T')）"