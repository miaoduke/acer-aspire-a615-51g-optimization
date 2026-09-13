#!/bin/bash
# install.sh — 一键安装/重装系统控制台（换机/重装/改名后在此目录运行一次即可）
# 用法: sudo bash install.sh
# 功能: sudo 免密白名单 + RAPL 读权限 + acdc/thermal-guard/cpu-power-limit 服务 + 桌面启动器(三处)
# 所有路径基于本脚本所在目录动态生成 -> 程序文件夹整体复制到任何位置都可重装
# 2026-09-01: 服务文件(acdc/thermal-guard)与 .desktop 全部由本脚本动态生成(APP_DIR)，
#             文件夹改名/换机后重跑一次即修复所有绝对路径引用
set -e

# readlink -f: 经 /usr/local/bin/sc-install.sh 别名启动时 $0 是符号链接，
# 必须解析到真实文件位置，否则 APP_DIR 会变成 /usr/local/bin（2026-09-10 回归修复）
APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
SCENE_SCRIPT="$APP_DIR/scripts/场景管理.sh"
M3_SCRIPT="$APP_DIR/backend/m3_gui.sh"
ACDC_SCRIPT="$APP_DIR/backend/acdc-profile.sh"
THERMAL_GUARD_SCRIPT="$APP_DIR/backend/thermal_guard.sh"
SUDOERS="/etc/sudoers.d/system-console"
RAPL_SVC="/etc/systemd/system/console-rapl-perm.service"
ACDC_SVC="/etc/systemd/system/acdc-profile.service"
THERMAL_SVC="/etc/systemd/system/thermal-guard.service"
CPUPL_SVC="/etc/systemd/system/cpu-power-limit.service"
# 真实调用用户（sudo bash 时 whoami=root，必须用 SUDO_USER）
REAL_USER="${SUDO_USER:-$(whoami)}"
REAL_HOME="$(getent passwd "$REAL_USER" | cut -d: -f6)"

echo "=== 系统控制台安装（APP_DIR=$APP_DIR）==="

# H1: 生成默认 config.yaml
if [ -w "$REAL_HOME/.config/system-console" ] || mkdir -p "$REAL_HOME/.config/system-console" 2>/dev/null; then
    su - "$REAL_USER" -c "python3 '$APP_DIR/src/core/config.py' 2>/dev/null || true" 2>/dev/null || true
    # config 的 base_dir 默认值是数据目录，但 controller 用 BASE 定位 backend/scripts 代码
    # （跨机适配/场景管理等全部失效）→ 安装时统一指向代码目录（数据目录随之在其下，幂等）
    CFG="$REAL_HOME/.config/system-console/config.yaml"
    [ -f "$CFG" ] && sed -i "s|^base_dir: .*|base_dir: $APP_DIR|; s|^data_dir: .*|data_dir: $APP_DIR/data|; s|^perf_log_dir: .*|perf_log_dir: $APP_DIR/data/perf|; s|^snapshot_dir: .*|snapshot_dir: $APP_DIR/data/snapshots|" "$CFG"
    echo "  ✓ config.yaml 已生成/验证"
fi

# H2: 冲突检测（仅警告，不阻塞）
echo "[0/7] 互斥工具冲突检测..."
if [ -f "$APP_DIR/scripts/check_conflicts.py" ]; then
    su - "$REAL_USER" -c "python3 '$APP_DIR/scripts/check_conflicts.py' 2>&1" || true
fi

# A-S1: Python AST double-sudo 检测
if [ -f "$APP_DIR/scripts/check_double_sudo.py" ]; then
    echo "  [A-S1] double-sudo 检测..."
    su - "$REAL_USER" -c "python3 '$APP_DIR/scripts/check_double_sudo.py' '$APP_DIR' 2>&1 | head -20" || true
fi

# Phase 2 G1: 生成默认 profile 目录
if [ ! -d "$REAL_HOME/.config/system-console/profiles" ]; then
    mkdir -p "$REAL_HOME/.config/system-console/profiles"
    chown -R "$REAL_USER" "$REAL_HOME/.config/system-console/profiles" 2>/dev/null || true
    echo "  ✓ 创建用户 profile 目录"
fi
# Phase 2 G2: 生成默认 plugin 目录
if [ ! -d "$REAL_HOME/.config/system-console/plugins" ]; then
    mkdir -p "$REAL_HOME/.config/system-console/plugins"
    chown -R "$REAL_USER" "$REAL_HOME/.config/system-console/plugins" 2>/dev/null || true
    echo "  ✓ 创建用户 plugin 目录"
fi

# A-S3: MSR deadman switch 安装
echo "[A-S3] 安装 MSR deadman switch..."
if [ -f "$APP_DIR/backend/msr_deadman.sh" ]; then
    cp "$APP_DIR/backend/msr_deadman.sh" /usr/local/bin/msr_deadman.sh
    chmod +x /usr/local/bin/msr_deadman.sh
    if [ -f "$APP_DIR/backend/msr_deadman.service" ]; then
        cp "$APP_DIR/backend/msr_deadman.service" /etc/systemd/system/
    fi
    if [ -f "$APP_DIR/backend/msr_deadman.timer" ]; then
        cp "$APP_DIR/backend/msr_deadman.timer" /etc/systemd/system/
    fi
    systemctl daemon-reload
    systemctl enable --now msr_deadman.timer 2>/dev/null || echo "  ⚠ msr_deadman.timer enable 失败（需 root）"
    echo "  ✓ MSR deadman switch 已部署"
fi

# P1-1 (2026-09-04): 降压安全网 + 每日自检部署段（此前手工 cp，重装会丢）
# 同步部署 verdict 单一来源机制（uv_safeguard 写 / uv_daily_check 读）
echo "[P1-1] 安装 uv-safeguard + uv-daily-check..."
if [ -f "$APP_DIR/backend/uv_safeguard.sh" ]; then
    cp "$APP_DIR/backend/uv_safeguard.sh" /usr/local/bin/uv_safeguard.sh
    chmod +x /usr/local/bin/uv_safeguard.sh
    if [ -f "$APP_DIR/backend/uv-safeguard.service" ]; then
        cp "$APP_DIR/backend/uv-safeguard.service" /etc/systemd/system/
    fi
    systemctl daemon-reload
    systemctl enable uv-safeguard.service 2>/dev/null || echo "  ⚠ uv-safeguard enable 失败（需 root）"
    echo "  ✓ uv-safeguard 已部署（三级判定: CLEAN/CRASH_REVERT/WATCH）"
fi
if [ -f "$APP_DIR/backend/uv_daily_check.sh" ]; then
    cp "$APP_DIR/backend/uv_daily_check.sh" /usr/local/bin/uv_daily_check.sh
    chmod +x /usr/local/bin/uv_daily_check.sh
    if [ -f "$APP_DIR/backend/uv-daily-check.service" ]; then
        cp "$APP_DIR/backend/uv-daily-check.service" /etc/systemd/system/
    fi
    if [ -f "$APP_DIR/backend/uv-daily-check.timer" ]; then
        cp "$APP_DIR/backend/uv-daily-check.timer" /etc/systemd/system/
    fi
    systemctl daemon-reload
    systemctl enable uv-daily-check.timer 2>/dev/null || echo "  ⚠ uv-daily-check.timer enable 失败（需 root）"
    echo "  ✓ uv-daily-check 已部署（MCE 误报修复 P0-1 + verdict 单一来源 P1-1）"
fi

# R11: 服务单元显式依赖已移到 install.sh 末尾（避免被后续 cat > 覆盖）
# 原位置（行 60）逻辑被移到 "=== 安装完成 ===" 之后

# =============================================================================
# [0/7] 系统依赖自动安装（2026-09-11 审计：重装后这些包全丢, 手工补过一次 → 纳入自动）
# 限流时间轴/MCE 监控/降压工具的运行时依赖, 缺了功能静默退化
# =============================================================================
echo "[0/7] 系统依赖检查与安装..."

# 0a. apt 包: 缺则装（apt-get download + dpkg -i 在多数环境可用; 失败仅警告不中断）
APT_PKGS=""   # 待补列表
for p in msr-tools rasdaemon libdbi-perl libdbd-sqlite3-perl; do
    dpkg -s "$p" >/dev/null 2>&1 || APT_PKGS="$APT_PKGS $p"
done
if [ -n "$APT_PKGS" ]; then
    echo "  缺包:$APT_PKGS — 尝试自动安装..."
    TMPD=$(mktemp -d)
    if (cd "$TMPD" && apt-get download $APT_PKGS >/dev/null 2>&1 && dpkg -i "$TMPD"/*.deb >/dev/null 2>&1); then
        echo "  ✓ 已安装:$APT_PKGS"
    else
        echo "  ⚠ 自动安装失败(离线/无源?), 手工: sudo apt install$APT_PKGS"
    fi
    rm -rf "$TMPD"
else
    echo "  ✓ 系统包齐全(msr-tools/rasdaemon/perl-DBI/perl-DBD-SQLite)"
fi
# 0b. rasdaemon 环境文件（包不带, 缺了服务起不来 — 2026-09-11 实测）
if dpkg -s rasdaemon >/dev/null 2>&1 && [ ! -f /etc/default/rasdaemon ]; then
    printf 'OPTIONS="-e"\n' > /etc/default/rasdaemon
    echo "  ✓ 已建 /etc/default/rasdaemon"
fi
systemctl enable --now rasdaemon >/dev/null 2>&1 || true

# 0c. undervolt 工具（pip 包 undervolt==0.4.0 → 项目 venv, 二进制链到 /usr/local/bin）
# 三重守护(uv_safeguard/uv_daily_check/msr_deadman)硬依赖 /usr/local/bin/undervolt
if [ ! -x "$APP_DIR/.venv-tools/bin/undervolt" ]; then
    echo "  undervolt 工具缺失 — pip 安装到项目 venv..."
    if python3 -m venv "$APP_DIR/.venv-tools" 2>/dev/null \
       && "$APP_DIR/.venv-tools/bin/pip" install --quiet undervolt >/dev/null 2>&1; then
        echo "  ✓ undervolt 已装入 .venv-tools"
    else
        echo "  ⚠ pip 安装失败(离线?), 手工: python3 -m venv '$APP_DIR/.venv-tools' && pip install undervolt"
    fi
fi
ln -sf "$APP_DIR/.venv-tools/bin/undervolt" /usr/local/bin/undervolt

# 0d. undervolt 主服务 + 挂起恢复服务（-100mV D7 验收值; 重装即丢 → 本段生成）
# 注意: 已存在时保留现值（uv_set.sh GUI 调节会改 ExecStart）, 只在缺失时生成
UV_CORE_MV=-100
if [ ! -f /etc/systemd/system/undervolt.service ]; then
    cat > /etc/systemd/system/undervolt.service <<EOF
[Unit]
Description=CPU/GPU undervolt (${UV_CORE_MV}mV, D7 accepted 2026-09-07)
After=multi-user.target
[Service]
Type=oneshot
ExecStart=/usr/local/bin/undervolt --core ${UV_CORE_MV} --cache ${UV_CORE_MV} --gpu ${UV_CORE_MV} --temp 98
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
EOF
    echo "  ✓ 已生成 undervolt.service (${UV_CORE_MV}mV)"
fi
if [ ! -f /etc/systemd/system/undervolt-resume.service ]; then
    # 挂起唤醒后 MSR 清零, 必须重打; 值与主服务一致（读取主服务 --core, 同步防漂移）
    RES_MV=$(grep -oE -- '--core +-[0-9]+' /etc/systemd/system/undervolt.service 2>/dev/null | head -1 | grep -oE -- '-[0-9]+$' || echo "$UV_CORE_MV")
    cat > /etc/systemd/system/undervolt-resume.service <<EOF
[Unit]
Description=Re-apply undervolt after suspend/resume
After=suspend.target
[Service]
Type=oneshot
ExecStart=/usr/local/bin/undervolt --core ${RES_MV} --cache ${RES_MV} --gpu ${RES_MV} --temp 98
[Install]
WantedBy=suspend.target
EOF
    echo "  ✓ 已生成 undervolt-resume.service (${RES_MV}mV)"
fi
systemctl daemon-reload
systemctl enable undervolt.service undervolt-resume.service >/dev/null 2>&1 || echo "  ⚠ undervolt 服务 enable 失败"
systemctl start undervolt.service >/dev/null 2>&1 || echo "  ⚠ undervolt 应用失败(工具/权限?)"

# 0e. acer-wmi-battery DKMS（源码备份在 WS 盘 → 复制回家目录注册; 电池温度依赖）
WS_SRC="/media/$REAL_USER/WS/acer 性能优化方案/03_Linux/性能优化方案_20260822/acer-wmi-battery_源码备份"
DKMS_HOME="$REAL_HOME/acer-wmi-battery"
if [ -f "$APP_DIR/backend/kernel_guard.sh" ] && [ -d "$WS_SRC" ]; then
    if [ ! -f "$DKMS_HOME/register_dkms.sh" ]; then
        mkdir -p "$DKMS_HOME"
        cp "$WS_SRC"/*.c "$WS_SRC"/*.conf "$WS_SRC"/Makefile "$WS_SRC"/*.sh "$WS_SRC"/LICENSE "$WS_SRC"/*.md "$DKMS_HOME"/ 2>/dev/null
    fi
    if [ ! -d "/var/lib/dkms/acer-wmi-battery" ]; then
        bash "$DKMS_HOME/register_dkms.sh" >/dev/null 2>&1 \
            && echo "  ✓ acer-wmi-battery DKMS 已注册" \
            || echo "  ⚠ DKMS 注册失败(需 linux-headers), 手工: bash $DKMS_HOME/register_dkms.sh"
    else
        echo "  ✓ acer-wmi-battery DKMS 已注册"
    fi
    printf 'acer_wmi_battery\n' > /etc/modules-load.d/acer-wmi-battery.conf
fi

# 1. sudo 免密白名单（严格限定路径，无通配符）
echo "[1/7] 配置 sudo 白名单..."
[ -f "$SCENE_SCRIPT" ] || { echo "❌ 场景管理.sh 不存在: $SCENE_SCRIPT"; exit 1; }
[ -f "$M3_SCRIPT" ] || { echo "❌ m3_gui.sh 不存在: $M3_SCRIPT"; exit 1; }
[ -f "$APP_DIR/backend/adapt_test.sh" ] || { echo "❌ adapt_test.sh 不存在"; exit 1; }
# sudoers 路径含空格无法匹配(sudoers 不支持引号/转义) → 建无空格别名符号链接
ln -sf "$APP_DIR/scripts/场景管理.sh" /usr/local/bin/sc-scene-switch.sh
ln -sf "$APP_DIR/backend/m3_gui.sh" /usr/local/bin/sc-m3-gui.sh
ln -sf "$APP_DIR/backend/adapt_test.sh" /usr/local/bin/sc-adapt-test.sh
ln -sf "$APP_DIR/install.sh" /usr/local/bin/sc-install.sh
ln -sf "$APP_DIR/00_保存会话与日志.sh" /usr/local/bin/sc-backup.sh
ln -sf "$APP_DIR/backend/uv_set.sh" /usr/local/bin/sc-uv-set.sh
ln -sf "$APP_DIR/backend/grub_timeout.sh" /usr/local/bin/sc-grub-timeout.sh
ln -sf "$APP_DIR/backend/kernel_guard.sh" /usr/local/bin/sc-kernel-guard.sh
cat > "$SUDOERS" <<EOF
# 系统控制台（System Console）免密白名单 — 严格限定以下命令
# sudoers 无法匹配含空格路径 → 控制台脚本一律走 /usr/local/bin 无空格别名(符号链接)
$REAL_USER ALL=(root) NOPASSWD: /usr/local/bin/sc-scene-switch.sh
$REAL_USER ALL=(root) NOPASSWD: /usr/local/bin/sc-m3-gui.sh
$REAL_USER ALL=(root) NOPASSWD: /usr/local/bin/sc-adapt-test.sh
$REAL_USER ALL=(root) NOPASSWD: /usr/local/bin/sc-install.sh
$REAL_USER ALL=(root) NOPASSWD: /usr/local/bin/sc-backup.sh
$REAL_USER ALL=(root) NOPASSWD: /usr/local/bin/sc-uv-set.sh
$REAL_USER ALL=(root) NOPASSWD: /usr/local/bin/sc-grub-timeout.sh
$REAL_USER ALL=(root) NOPASSWD: /usr/local/bin/sc-kernel-guard.sh
$REAL_USER ALL=(root) NOPASSWD: /usr/bin/prime-select
$REAL_USER ALL=(root) NOPASSWD: /usr/sbin/ras-mc-ctl
$REAL_USER ALL=(root) NOPASSWD: /usr/bin/timeshift
$REAL_USER ALL=(root) NOPASSWD: /usr/sbin/efibootmgr
$REAL_USER ALL=(root) NOPASSWD: /usr/sbin/modprobe
$REAL_USER ALL=(root) NOPASSWD: /usr/local/bin/undervolt
EOF
chmod 440 "$SUDOERS"
# MSR 只读工具(msr-tools)免密: GUI 限流时间轴依赖
# (2026-09-11 审计: heredoc 刚全量重写 $SUDOERS, 必不含 rdmsr → grep 判断恒假是死条件, 删)
if dpkg -s msr-tools >/dev/null 2>&1; then
    echo "$REAL_USER ALL=(root) NOPASSWD: /usr/sbin/rdmsr" >> "$SUDOERS"
    echo "$REAL_USER ALL=(root) NOPASSWD: /usr/sbin/wrmsr" >> "$SUDOERS"
    echo "  ✓ msr-tools 已装, rdmsr/wrmsr 免密已补充"
else
    echo "  ⚠ msr-tools 未装(GUI 限流时间轴会退化), 本脚本 [0/7] 段会自动安装"
fi

# A-S2: visudo -c 自动校验（防止 sudoers 配置错误）
if command -v visudo >/dev/null 2>&1; then
    if ! visudo -c -f "$SUDOERS" >/dev/null 2>&1; then
        echo "  ❌ visudo -c 校验失败，请检查 $SUDOERS"
        visudo -c -f "$SUDOERS"
        exit 1
    fi
    echo "  ✓ visudo -c 校验通过"
else
    echo "  ⚠ visudo 不可用，跳过语法校验"
fi

# 1b. 散热控制脚本白名单（fan_boost/tcc/pclamp/maxperf/usb/wifi，安装到系统工具位）
# 2026-09-11 审计修复: 原为前置检查"不存在即退出" — 重装后 /usr/local/bin 为空,
# install.sh 必死在这(今天实测踩过) → 改为从仓库 backend/ 自动部署(幂等)
install -m 0755 "$APP_DIR/backend/thermal_ctl.sh" /usr/local/bin/thermal_ctl.sh \
  || { echo "❌ thermal_ctl.sh 部署失败"; exit 1; }
install -m 0755 "$APP_DIR/backend/thermal_guard.sh" /usr/local/bin/thermal_guard.sh \
  || echo "  ⚠ thermal_guard.sh 部署失败"
cat > /etc/sudoers.d/system-console-thermal <<EOF
$REAL_USER ALL=(root) NOPASSWD: /usr/local/bin/thermal_ctl.sh
EOF
chmod 440 /etc/sudoers.d/system-console-thermal

# A-S2: visudo -c 自动校验
if command -v visudo >/dev/null 2>&1; then
    if ! visudo -c -f /etc/sudoers.d/system-console-thermal >/dev/null 2>&1; then
        echo "  ❌ thermal sudoers 校验失败"
        visudo -c -f /etc/sudoers.d/system-console-thermal
        exit 1
    fi
    echo "  ✓ thermal sudoers 校验通过"
fi

# 2. RAPL 读权限（所有用户可读功耗限制，供 GUI 显示）
# 2026-09-01 修复: RAPL 设备在启动早期(local-fs.target 后)尚未出现(intel_rapl 模块加载更晚)，
# chmod 会失败且无人重试 → 实时功耗一直读不到。加 Restart=on-failure 重试直到设备出现。
echo "[2/7] 配置 RAPL 读权限..."
cat > "$RAPL_SVC" <<EOF
[Unit]
Description=Console RAPL read permission
After=local-fs.target
StartLimitIntervalSec=0
[Service]
Type=oneshot
ExecStart=/bin/chmod -R a+r /sys/class/powercap/intel-rapl:0
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable console-rapl-perm.service >/dev/null 2>&1
systemctl start console-rapl-perm.service 2>/dev/null || true

# 3. AC/DC 自动场景切换服务（指向本程序文件夹，动态路径）
echo "[3/7] 配置 acdc-profile 服务..."
[ -f "$ACDC_SCRIPT" ] || { echo "❌ acdc-profile.sh 不存在: $ACDC_SCRIPT"; exit 1; }
cat > "$ACDC_SVC" <<EOF
[Unit]
Description=AC/DC auto scene switch (v4, 相对路径)
After=multi-user.target
# 2026-09-11: 程序在 NTFS 数据盘上, 开机比挂载早启动 → 203/EXEC。等盘挂好再起。
RequiresMountsFor=$APP_DIR
[Service]
Type=simple
ExecStart="$ACDC_SCRIPT"
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable acdc-profile.service >/dev/null 2>&1
systemctl restart acdc-profile.service

# 4. 温度守护服务（指向本程序文件夹，动态路径）
# 2026-09-01: 原服务文件为手工部署(绝对路径)，文件夹改名/换机即失效 → 纳入 install.sh 统一管理
echo "[4/7] 配置 thermal-guard 服务..."
[ -f "$THERMAL_GUARD_SCRIPT" ] || { echo "❌ thermal_guard.sh 不存在: $THERMAL_GUARD_SCRIPT"; exit 1; }
cat > "$THERMAL_SVC" <<EOF
[Unit]
Description=Thermal guard: temperature->PL1 auto throttle (safe fan alternative)
After=multi-user.target
# 2026-09-11: 程序在 NTFS 数据盘上, 开机比挂载早启动 → 203/EXEC。等盘挂好再起。
RequiresMountsFor=$APP_DIR
[Service]
Type=simple
ExecStart="$THERMAL_GUARD_SCRIPT"
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable thermal-guard.service >/dev/null 2>&1
systemctl restart thermal-guard.service

# 5. PL1/PL2 功耗限制（M3 感知，防 44W 突刺过热）
# 2026-09-01: M3 生效时跳过——否则启动后覆盖 M3 的 PL1=10W，
# 且使 turbo-guard 场景感知(powersave/power/PL1≤11W)误判为非省电场景而强制开 turbo
echo "[5/7] 配置 cpu-power-limit 服务..."
cat > "$CPUPL_SVC" <<EOF
[Unit]
Description=PL1/PL2 功耗限制 - 防 44W 突刺过热
After=multi-user.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c '[ "\$(systemctl is-enabled m3-power-saver 2>/dev/null)" = "enabled" ] && exit 0; echo 25000000 > /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw; echo 25000000 > /sys/class/powercap/intel-rapl:0/constraint_1_power_limit_uw'
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable cpu-power-limit.service >/dev/null 2>&1
systemctl start cpu-power-limit.service 2>/dev/null || true

# 6. 桌面启动器（三处：桌面 / 应用菜单 / 程序目录自引用，全部动态路径）
# 注意: sudo 下 $HOME=/root, 必须用真实用户解析桌面路径
echo "[6/7] 创建桌面启动器（桌面/应用菜单/程序目录）..."
DESKTOP_DIR="$(sudo -u "$REAL_USER" xdg-user-dir DESKTOP 2>/dev/null || echo "/home/$REAL_USER/Desktop")"
mk_desktop() { # $1=目标路径
  cat > "$1" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=系统控制台
GenericName=Power & Thermal Console
Comment=Acer A615-51G 电源与散热控制台（监控 + 场景切换 + 调优）
Exec="$APP_DIR/启动控制台.sh"
Path=$APP_DIR
Icon=utilities-system-monitor
Terminal=false
Categories=Utility;System;
Keywords=power;battery;thermal;undervolt;cpu;电源;电池;散热;降压
StartupNotify=true
StartupWMClass=console.py
EOF
  chmod +x "$1"
  echo "  ✓ $1"
}
mk_desktop "$DESKTOP_DIR/系统控制台.desktop"
mkdir -p "$REAL_HOME/.local/share/applications"
mk_desktop "$REAL_HOME/.local/share/applications/系统控制台.desktop"
mk_desktop "$APP_DIR/系统控制台.desktop"

# 7. 自启动（开机自动运行 GUI，存在则更新 Exec 指向当前路径）
echo "[7/7] 检查自启动..."
AUTOSTART="$REAL_HOME/.config/autostart/system-console.desktop"
if [ -f "$AUTOSTART" ]; then
  sed -i "s|^Exec=.*|Exec=\"$APP_DIR/启动控制台.sh\"|; s|^Path=.*|Path=$APP_DIR|" "$AUTOSTART"
  echo "  - 自启动已存在，已更新路径"
else
  mkdir -p "$REAL_HOME/.config/autostart"
  mk_desktop "$AUTOSTART"
  echo "  ✓ 已添加开机自启动 $AUTOSTART"
fi
# 2026-09-11 修复: 以 root 运行时生成的文件归 root → GUI 自启开关写不进去。
# 家目录配置文件归还真实用户（维护页开关功能依赖可写性）。
chown "$REAL_USER":"$(id -gn "$REAL_USER")" "$AUTOSTART" 2>/dev/null || true
# 同理: 用户目录下的另两份 .desktop 也归还（install 以 root 写入时同样会错归属）
for d in "$DESKTOP_DIR/系统控制台.desktop" "$REAL_HOME/.local/share/applications/系统控制台.desktop"; do
  [ -f "$d" ] && chown "$REAL_USER":"$(id -gn "$REAL_USER")" "$d" 2>/dev/null || true
done

echo ""
echo "=== 安装完成 ==="
echo "程序目录: $APP_DIR（整体复制到新电脑后重新运行本脚本即可）"
echo "启动: 双击桌面「系统控制台」 或 $APP_DIR/启动控制台.sh"
echo "验证: sudo visudo -c; systemctl status acdc-profile thermal-guard"

# R11: 服务单元显式依赖（在 cat > 全部完成之后注入，避免被覆盖）
echo ""
echo "[R11] 服务单元显式依赖注入..."
# acdc-profile 必须在 cpu-power-limit 之后启动（避免后者覆盖前者的 PL 设置）
if [ -f /etc/systemd/system/acdc-profile.service ]; then
    if ! grep -q "After=cpu-power-limit.service" /etc/systemd/system/acdc-profile.service; then
        sed -i '/^After=multi-user.target/a After=cpu-power-limit.service' /etc/systemd/system/acdc-profile.service
        echo "  ✓ acdc-profile.service 添加 After=cpu-power-limit.service"
    else
        echo "  - acdc-profile.service 依赖已存在"
    fi
fi
# thermal-guard 必须在 cpu-power-limit 之后启动
if [ -f /etc/systemd/system/thermal-guard.service ]; then
    if ! grep -q "After=cpu-power-limit.service" /etc/systemd/system/thermal-guard.service; then
        sed -i '/^After=multi-user.target/a After=cpu-power-limit.service' /etc/systemd/system/thermal-guard.service
        echo "  ✓ thermal-guard.service 添加 After=cpu-power-limit.service"
    else
        echo "  - thermal-guard.service 依赖已存在"
    fi
fi
systemctl daemon-reload 2>/dev/null || true

# Phase 1 健康检查（验证部署结果）
echo ""
echo "=== Phase 1 健康检查 ==="
if [ -x "$APP_DIR/scripts/phase1_health_check.sh" ]; then
    bash "$APP_DIR/scripts/phase1_health_check.sh" 2>&1 | tail -10
fi
