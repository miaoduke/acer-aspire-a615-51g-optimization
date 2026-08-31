#!/usr/bin/env bash
#
# 临时启动 Windows 工具
# ----------------------------------------------------------------------------
# 功能：
#   1. 临时把下一次重启切换到硬盘中的 Windows（使用 EFI BootNext，不影响
#      永久启动顺序，重启回 Linux 后自动恢复正常）。
#   2. 临时把 GRUB 等待时间设为 1 秒（可用 TIMEOUT 环境变量覆盖）并显示菜单，
#      超时后自动回到 Linux。
#   3. 在 GRUB 菜单中按 ESC 可“跳过等待”立即启动当前高亮项。
#
# 适用：UEFI + GRUB2 双系统（已确认当前机器 Windows Boot Manager 存在）。
#
# 用法：双击 .desktop 启动器 -> 输入密码提权 -> 确认 -> 自动重启进 Windows。
# ----------------------------------------------------------------------------

set -euo pipefail

# ---- 颜色 ----
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[信息]${NC} $*"; }
ok()    { echo -e "${GREEN}[完成]${NC} $*"; }
warn()  { echo -e "${YELLOW}[注意]${NC} $*"; }
err()   { echo -e "${RED}[错误]${NC} $*" >&2; }

# ---- 一次性提权：若非 root，重新以 root 执行本脚本自身（只弹一次密码） ----
if [ "$(id -u)" -ne 0 ]; then
    if command -v pkexec >/dev/null 2>&1; then
        exec pkexec "$0" "$@"
    elif command -v sudo >/dev/null 2>&1; then
        exec sudo "$0" "$@"
    else
        err "本脚本需要 root 权限，但未找到 pkexec 或 sudo。"
        exit 1
    fi
fi
# 到此已确保是 root，后续命令无需再加任何提权前缀。

# ---- 0. 前置检查 ----
if ! command -v efibootmgr >/dev/null 2>&1; then
    err "未找到 efibootmgr，请先安装：sudo apt install efibootmgr"
    exit 1
fi

# 确认是 UEFI 模式
if [ ! -d /sys/firmware/efi ]; then
    err "当前不是 UEFI 模式（/sys/firmware/efi 不存在），本脚本仅支持 UEFI。"
    exit 1
fi

# ---- 1. 自动探测 Windows Boot Manager 的启动项编号 ----
# 匹配策略：优先精确 "Windows Boot Manager"，否则匹配含 Windows 关键字，
# 再退而匹配 bootmgfw.efi 路径（覆盖中文固件等非常规命名）。
info "正在探测 Windows 启动项..."
WIN_NUM=""
detect_win() {
    local src="$1"
    # 1) 标准英文名
    WIN_NUM=$(echo "$src" | grep -i "Windows Boot Manager" | head -1 | grep -oE '^Boot[0-9A-Fa-f]{4}' | sed 's/Boot//')
    # 2) 含 Windows 关键字
    if [ -z "$WIN_NUM" ]; then
        WIN_NUM=$(echo "$src" | grep -i "Windows" | head -1 | grep -oE '^Boot[0-9A-Fa-f]{4}' | sed 's/Boot//')
    fi
    # 3) 匹配 bootmgfw.efi 路径
    if [ -z "$WIN_NUM" ]; then
        WIN_NUM=$(echo "$src" | grep -i "bootmgfw.efi" | head -1 | grep -oE '^Boot[0-9A-Fa-f]{4}' | sed 's/Boot//')
    fi
}
detect_win "$(efibootmgr)"

if [ -z "${WIN_NUM:-}" ]; then
    err "未在 EFI 启动项中找到 Windows Boot Manager。"
    err "请确认 Windows 已正确安装且 EFI 文件 (EFI/Microsoft/Boot/bootmgfw.efi) 存在。"
    exit 1
fi
ok "找到 Windows 启动项：Boot${WIN_NUM}"

# ---- 2. 临时设置 GRUB 超时与菜单显示 ----
GRUB_DEFAULT_CFG="/etc/default/grub"
GRUB_BAK="/etc/default/grub.compose-max.bak"
# GRUB 倒计时秒数：可用环境变量 TIMEOUT 覆盖，默认 1 秒
TIMEOUT="${TIMEOUT:-1}"

if [ -f "$GRUB_DEFAULT_CFG" ]; then
    info "备份 GRUB 配置到 $GRUB_BAK ..."
    cp -f "$GRUB_DEFAULT_CFG" "$GRUB_BAK"

    info "将 GRUB 超时临时设置为 ${TIMEOUT} 秒并显示菜单..."
    # 修改/新增 GRUB_TIMEOUT
    if grep -q '^GRUB_TIMEOUT=' "$GRUB_DEFAULT_CFG"; then
        sed -i "s/^GRUB_TIMEOUT=.*/GRUB_TIMEOUT=${TIMEOUT}/" "$GRUB_DEFAULT_CFG"
    else
        bash -c "echo 'GRUB_TIMEOUT=${TIMEOUT}' >> $GRUB_DEFAULT_CFG"
    fi
    # 修改/新增 GRUB_TIMEOUT_STYLE=menu（显示菜单，否则 hidden 看不到）
    if grep -q '^GRUB_TIMEOUT_STYLE=' "$GRUB_DEFAULT_CFG"; then
        sed -i 's/^GRUB_TIMEOUT_STYLE=.*/GRUB_TIMEOUT_STYLE=menu/' "$GRUB_DEFAULT_CFG"
    else
        bash -c "echo 'GRUB_TIMEOUT_STYLE=menu' >> $GRUB_DEFAULT_CFG"
    fi

    # 更新 grub.cfg
    info "正在更新 grub 配置 (grub-mkconfig)..."
    if command -v update-grub >/dev/null 2>&1; then
        update-grub >/dev/null 2>&1 || grub-mkconfig -o /boot/grub/grub.cfg >/dev/null 2>&1 || true
    else
        grub-mkconfig -o /boot/grub/grub.cfg >/dev/null 2>&1 || true
    fi
    ok "GRUB 已设置为 ${TIMEOUT} 秒倒计时 + 显示菜单。"
else
    warn "未找到 $GRUB_DEFAULT_CFG，跳过 GRUB 调整（不影响 BootNext 切换）。"
fi

# ---- 3. 设置下一次启动为 Windows（BootNext，仅生效一次） ----
info "设置下一次重启进入 Windows（BootNext=Boot${WIN_NUM}）..."
if ! efibootmgr -n "$WIN_NUM"; then
    err "设置 BootNext 失败，请检查 EFI 变量权限（/sys/firmware/efi/efivars 是否对 root 可写）。"
    exit 1
fi
# 二次校验：确认 BootNext 确实已写入
if ! efibootmgr 2>/dev/null | grep -qi "BootNext: .*${WIN_NUM}"; then
    err "已执行 efibootmgr -n，但未能确认 BootNext=Boot${WIN_NUM} 已生效，中止以免误重启。"
    exit 1
fi
ok "已确认：下次重启将进入 Windows（BootNext=Boot${WIN_NUM}）。"

# ---- 4. 准备“返回 Linux 后自动还原 GRUB”的一次性服务 ----
# 思路：本次进 Windows 后，下一次启动回 Linux 时，由本服务检测标记并还原 grub。
# 注意：此处只写服务文件，不在确认前 enable，避免取消重启后残留还原逻辑。
FLAG_FILE="/var/lib/compose-max-reboot-windows.flag"
SERVICE_PATH="/etc/systemd/system/compose-max-restore-grub.service"
cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=Restore GRUB config after temporary Windows boot (compose-max)
After=multi-user.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/env bash -c '\\
if [ -f $FLAG_FILE ]; then \\
  BAK=\$(grep RESTORE_GRUB_BAK $FLAG_FILE | cut -d= -f2); \\
  if [ -n "\$BAK" ] && [ -f "\$BAK" ]; then \\
    cp -f "\$BAK" /etc/default/grub; \\
    rm -f "\$BAK"; \\
  fi; \\
  rm -f $FLAG_FILE; \\
  if command -v update-grub >/dev/null 2>&1; then update-grub >/dev/null 2>&1; fi; \\
fi'
ExecStartPost=/usr/bin/env systemctl disable compose-max-restore-grub.service

[Install]
WantedBy=multi-user.target
EOF
ok "已写入一次性还原服务文件（确认重启后才会启用）。"

# ---- 5. 确认并重启 ----
echo
warn "即将重启并临时进入 Windows。"
warn "返回说明：Windows 重启后会按原启动顺序回到 Linux；"
warn "GRUB 菜单有 ${TIMEOUT} 秒倒计时，按 ESC 可立即启动当前高亮项（跳过等待）。"
echo
read -r -p "确认现在重启进入 Windows？[Y/n] " ANS
ANS=${ANS:-Y}
if [[ "$ANS" =~ ^[Yy]$ ]]; then
    # 真正启用还原服务（仅确认重启时），并写入标记
    if [ -f "$GRUB_DEFAULT_CFG" ]; then
        echo "RESTORE_GRUB_BAK=$GRUB_BAK" > "$FLAG_FILE"
        systemctl daemon-reload
        systemctl enable compose-max-restore-grub.service
        ok "已启用一次性还原服务：下次回到 Linux 会自动恢复 GRUB 原配置。"
    fi
    info "正在重启..."
    reboot || systemctl reboot
else
    warn "已取消。将清理本次设置的临时状态..."
    # 清除 BootNext，避免残留导致下次重启误入 Windows
    if ! efibootmgr -N; then
        warn "清除 BootNext 失败（可能本就没有设置或 EFI 权限受限），请手动确认。"
    fi
    # 若尚未启用还原服务则无需处理；若已写 flag 则清理
    rm -f "$FLAG_FILE" 2>/dev/null || true
    ok "已尝试清除 BootNext 临时设置。GRUB 配置未改动（仍保持当前状态）。"
    warn "提示：如需彻底还原本次 GRUB 调整，可运行 'sudo cp $GRUB_BAK /etc/default/grub && sudo update-grub'。"
fi
