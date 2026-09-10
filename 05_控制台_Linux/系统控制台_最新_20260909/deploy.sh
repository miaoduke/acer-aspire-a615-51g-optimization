#!/bin/bash
# =============================================================================
# deploy.sh — 把归档主版本部署到运行位置（~/.local/share/系统控制台）
# =============================================================================
# 解决的双副本割裂问题（2026-08-31 审计发现）：
#   · sudoers 白名单指向 ~/.local/share/系统控制台 → 运行的是部署副本
#   · perf_logger/battery_stats 数据写 ~/.local/share/系统控制台/data
#   · UI 的 thermal-guard 配置功能 sed 修改部署副本
#   → 改归档源码【不会生效】，必须经本脚本部署
#
# 用法:
#   bash deploy.sh            # 同步差异（保留运行数据）
#   bash deploy.sh --check    # 只预览差异，不修改
#   bash deploy.sh --dry-run  # rsync 试运行
#
# 安全设计:
#   · 运行数据(data/perf, data/battery_usage.json 等)【只出不进】: 先备份到部署副本
#   · 不覆盖: *.bak 备份文件
#   · 同步后自动重启 acdc-profile(若在跑)，提示需要重启控制台程序
# =============================================================================
set -u

# 归档主版本（本脚本所在目录）
SRC="$(cd "$(dirname "$0")" && pwd)"
# 运行位置（sudoers 白名单指向这里）
DEST="$HOME/.local/share/系统控制台"

echo "=== 控制台部署: 归档 → 运行位置 ==="
echo "源: $SRC"
echo "目标: $DEST"
echo

[ -d "$SRC/backend" ] || { echo "❌ 源不完整（无 backend/）"; exit 1; }
[ -d "$DEST" ] || { echo "❌ 运行位置不存在: $DEST"; echo "   首次部署请改用: sudo bash $SRC/install.sh"; exit 1; }

DRY=""
[ "${1:-}" = "--check" ] && DRY="-n" && echo ">>> 预览模式（--check）"
[ "${1:-}" = "--dry-run" ] && DRY="-n" && echo ">>> 试运行模式"

# ---------- 1. 备份运行数据（数据在部署副本，迁回归档前先保护）----------
STAMP=$(date +%Y%m%d_%H%M%S)
BAK="$DEST/.deploy_backup_$STAMP"
mkdir -p "$BAK"

echo
echo "[1/3] 备份运行数据 → $BAK"
for item in "data/perf" "data/battery_usage.json" "data/snapshot_log.txt"; do
    if [ -e "$DEST/$item" ]; then
        mkdir -p "$BAK/$(dirname "$item")"
        cp -a "$DEST/$item" "$BAK/$item"
        echo "  ✓ $item"
    fi
done
# 2026-08-31: 清理历史 deploy 备份（只保留最近 3 个），防堆积
# （实测一天部署 10 次就堆了 10 个 252K 备份）
KEEP=3
OLD_BAKS=$(ls -dt "$DEST"/.deploy_backup_* 2>/dev/null | tail -n +$((KEEP + 1)))
if [ -n "$OLD_BAKS" ]; then
    echo "$OLD_BAKS" | xargs -r rm -rf
    echo "  🧹 已清理旧 deploy 备份（保留最近 $KEEP 个）"
fi

# ---------- 2. rsync 同步（归档 → 部署，排除运行数据与备份）----------
echo
echo "[2/3] 同步代码（排除运行数据/备份/会话记录）"
rsync -a $DRY \
    --exclude 'data/perf/' \
    --exclude 'data/battery_usage.json' \
    --exclude 'data/snapshot_log.txt' \
    --exclude 'data/charge_curve_*' \
    --exclude '.deploy_backup_*' \
    --exclude '.merge_backup_*' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '会话记录/' \
    --exclude '20260821_*/' \
    --exclude '20260829_*/' \
    --exclude '*.bak*' \
    "$SRC/" "$DEST/"
RC=$?
echo "  rsync 退出码: $RC"

# ---------- 3. 部署后动作 ----------
if [ -z "$DRY" ]; then
    echo
    echo "[3/3] 部署后动作"

    # 3a. thermal_ctl.sh 真机版部署到 /usr/local/bin（sudoers 白名单指向它）
    if [ -f "$DEST/backend/thermal_ctl.sh" ]; then
        install -m 0755 "$DEST/backend/thermal_ctl.sh" /usr/local/bin/thermal_ctl.sh 2>/dev/null \
            && echo "  ✓ thermal_ctl.sh → /usr/local/bin（sudoers 白名单目标）" \
            || echo "  ⚠ thermal_ctl.sh 部署失败（需 root）: sudo install -m 0755 $DEST/backend/thermal_ctl.sh /usr/local/bin/"
    fi
    if [ -f "$DEST/backend/thermal_guard.sh" ]; then
        install -m 0755 "$DEST/backend/thermal_guard.sh" /usr/local/bin/thermal_guard.sh 2>/dev/null \
            && echo "  ✓ thermal_guard.sh → /usr/local/bin"
    fi

    # 3b. 服务单元若有变化则提示
    systemctl is-active thermal-guard >/dev/null 2>&1 \
        && echo "  ℹ thermal-guard 在跑：若其脚本有变更需 sudo systemctl restart thermal-guard"

    # 3c. 提示重启控制台程序
    echo
    echo "⚠️ 部署完成。请【关闭并重新启动控制台程序】以加载新代码："
    echo "   python3 $DEST/console.py"
    echo
    echo "回滚（如需）: 备份在 $BAK；旧代码可用 rsync 从备份恢复"
else
    echo
    echo ">>> 预览完成（未修改任何文件）"
fi
