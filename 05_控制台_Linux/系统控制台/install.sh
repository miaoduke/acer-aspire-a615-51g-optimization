#!/bin/bash
# install.sh — 一键安装/重装系统控制台（换机/重装系统后在此目录运行一次即可）
# 用法: sudo bash install.sh
# 功能: sudo 免密白名单(相对路径动态生成) + RAPL 读权限 + acdc 服务 + 桌面启动器(.desktop)
# 所有路径基于本脚本所在目录动态生成 -> 程序文件夹整体复制到任何位置都可重装
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
SCENE_SCRIPT="$APP_DIR/scripts/场景管理.sh"
M3_SCRIPT="$APP_DIR/backend/m3_gui.sh"
ACDC_SCRIPT="$APP_DIR/backend/acdc-profile.sh"
SUDOERS="/etc/sudoers.d/system-console"
RAPL_SVC="/etc/systemd/system/console-rapl-perm.service"
ACDC_SVC="/etc/systemd/system/acdc-profile.service"
# 真实调用用户（sudo bash 时 whoami=root，必须用 SUDO_USER）
REAL_USER="${SUDO_USER:-$(whoami)}"

echo "=== 系统控制台安装（APP_DIR=$APP_DIR）==="

# 1. sudo 免密白名单（严格限定路径，无通配符）
echo "[1/5] 配置 sudo 白名单..."
[ -f "$SCENE_SCRIPT" ] || { echo "❌ 场景管理.sh 不存在: $SCENE_SCRIPT"; exit 1; }
[ -f "$M3_SCRIPT" ] || { echo "❌ m3_gui.sh 不存在: $M3_SCRIPT"; exit 1; }
cat > "$SUDOERS" <<EOF
# 系统控制台（System Console）免密白名单 — 严格限定以下命令
# 2026-08-31 增补: timeshift(快照) / adapt_test(跨机适配) / efibootmgr(临时切Win)
$REAL_USER ALL=(root) NOPASSWD: $SCENE_SCRIPT
$REAL_USER ALL=(root) NOPASSWD: $M3_SCRIPT
$REAL_USER ALL=(root) NOPASSWD: /usr/bin/prime-select
$REAL_USER ALL=(root) NOPASSWD: /usr/sbin/ras-mc-ctl
$REAL_USER ALL=(root) NOPASSWD: /usr/bin/timeshift
$REAL_USER ALL=(root) NOPASSWD: $APP_DIR/backend/adapt_test.sh
$REAL_USER ALL=(root) NOPASSWD: /usr/sbin/efibootmgr
EOF
chmod 440 "$SUDOERS"
echo "  ✓ 已写入 $SUDOERS"

# 1b. 散热控制脚本白名单（fan_boost/tcc/pclamp/maxperf/usb/wifi，安装到系统工具位）
[ -f /usr/local/bin/thermal_ctl.sh ] || { echo "❌ thermal_ctl.sh 不存在"; exit 1; }
cat > /etc/sudoers.d/system-console-thermal <<EOF
$REAL_USER ALL=(root) NOPASSWD: /usr/local/bin/thermal_ctl.sh
EOF
chmod 440 /etc/sudoers.d/system-console-thermal

# 2. RAPL 读权限（所有用户可读功耗限制，供 GUI 显示）
echo "[2/5] 配置 RAPL 读权限..."
cat > "$RAPL_SVC" <<EOF
[Unit]
Description=Console RAPL read permission
After=local-fs.target
[Service]
Type=oneshot
ExecStart=/bin/chmod -R a+r /sys/class/powercap/intel-rapl:0
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable console-rapl-perm.service >/dev/null 2>&1
systemctl start console-rapl-perm.service 2>/dev/null || true

# 3. AC/DC 自动场景切换服务（指向本程序文件夹，动态路径）
echo "[3/5] 配置 acdc-profile 服务..."
[ -f "$ACDC_SCRIPT" ] || { echo "❌ acdc-profile.sh 不存在: $ACDC_SCRIPT"; exit 1; }
cat > "$ACDC_SVC" <<EOF
[Unit]
Description=AC/DC auto scene switch (v4, 相对路径)
After=multi-user.target
[Service]
Type=simple
ExecStart=$ACDC_SCRIPT
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable acdc-profile.service >/dev/null 2>&1
systemctl restart acdc-profile.service

# 4. 桌面启动器（.desktop -> start.sh，双击即启动）
# 注意: sudo 下 $HOME=/root, 必须用真实用户解析桌面路径
echo "[4/5] 创建桌面启动器..."
DESKTOP_DIR="$(sudo -u "$REAL_USER" xdg-user-dir DESKTOP 2>/dev/null || echo "/home/$REAL_USER/Desktop")"
cat > "$DESKTOP_DIR/系统控制台.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=系统控制台
Comment=Acer 电源与散热控制台
Exec=$APP_DIR/start.sh
Icon=utilities-system-monitor
Terminal=false
Categories=Utility;System;
EOF
chmod +x "$DESKTOP_DIR/系统控制台.desktop"
echo "  ✓ $DESKTOP_DIR/系统控制台.desktop"

# 5. 自启动（开机自动运行 GUI，可选；存在则跳过）
echo "[5/5] 检查自启动..."
AUTOSTART="/home/$REAL_USER/.config/autostart/system-console.desktop"
if [ ! -f "$AUTOSTART" ]; then
  mkdir -p "/home/$REAL_USER/.config/autostart"
  cp "$DESKTOP_DIR/系统控制台.desktop" "$AUTOSTART"
  sed -i "s|^Exec=.*|Exec=$APP_DIR/start.sh|" "$AUTOSTART"
  echo "  ✓ 已添加开机自启动 $AUTOSTART"
else
  echo "  - 自启动已存在，跳过"
fi

echo ""
echo "=== 安装完成 ==="
echo "程序目录: $APP_DIR（整体复制到新电脑后重新运行本脚本即可）"
echo "启动: 双击桌面「系统控制台」 或 $APP_DIR/start.sh"
echo "验证: sudo visudo -c; systemctl status acdc-profile"