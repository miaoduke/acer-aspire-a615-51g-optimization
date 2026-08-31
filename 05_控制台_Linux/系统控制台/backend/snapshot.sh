#!/bin/bash
# snapshot.sh — Timeshift 快照管理（铁律分级触发）
# 用法:
#   snapshot.sh create <说明>   创建快照（L1/L2 任务前必做）
#   snapshot.sh list            列出快照
#   snapshot.sh note <编号>     查看回滚指引
#
# 铁律分级:
#   L1 系统级修改前（GRUB/内核/批量服务/驱动）→ 必须快照
#   L2 高风险实验前（undervolt/C-state/EC）  → 必须快照 + 记录回滚步骤
#   L3 日常代码编辑 → 不快照（靠 WS1 同步 + 备份脚本）

ACTION="${1:-list}"

case "$ACTION" in
    create)
        DESC="${2:-手动快照}"
        echo "创建系统快照（btrfs CoW，秒级完成）..."
        sudo timeshift --create --comments "$DESC" 2>&1 | tail -3
        # 记录到项目日志
        LOG="/home/<USER>/.local/share/系统控制台/data/snapshot_log.txt"
        mkdir -p "$(dirname "$LOG")"
        echo "$(date '+%F %T') | $DESC" >> "$LOG"
        echo "✓ 已记录到 $LOG"
        ;;
    list)
        sudo timeshift --list 2>&1 | head -20
        ;;
    note)
        cat <<'EOF'
=== 快照恢复指引 ===
1. GUI:   打开 Timeshift → 选择快照 → 恢复
2. 命令行: sudo timeshift --restore  （交互选择）
3. 应急（进不了系统）: Live USB → 挂载 btrfs → 
   /run/timeshift/.../snapshots/<时间>/@ 为完好系统根

⚠ 注意: Timeshift 只保护 @（系统子卷）
   /home 数据保障 = WS1 同步 (sync_to_ws1.sh) + 备份脚本
EOF
        ;;
    *)
        echo "用法: $0 {create <说明>|list|note}"
        ;;
esac