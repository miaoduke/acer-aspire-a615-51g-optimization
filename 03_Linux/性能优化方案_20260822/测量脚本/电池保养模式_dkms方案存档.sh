#!/bin/bash
# ============================================================
# 电池保养模式.sh — Acer 电池健康模式(80% 充电上限) 一键部署
# 依据: 性能优化方案/电池保养模式调研_20260818.md (2026-08-18)
# 功能: 构建 acer-wmi-battery 模块 + DKMS 持久化 + 启用 80% 上限
# 用法: sudo bash 电池保养模式.sh   (或 电池保养模式.sh on/off/status)
# 注意: 需 root 执行安装部分
# ============================================================

set -e
SRC=/home/<USER>/acer-wmi-battery
MOD=acer_wmi_battery          # modprobe 名(连字符转下划线)
SYSFS=/sys/bus/wmi/drivers/acer-wmi-battery

# ---------- 状态查询 ----------
status() {
    echo "=== 电池保养模式状态 ==="
    echo "模块: $(lsmod | grep -c acer_wmi_battery) (1=已加载)"
    if [ -d "$SYSFS" ]; then
        echo -n "health_mode: "; cat $SYSFS/health_mode 2>/dev/null || echo "(不可读)"
        echo -n "电池温度: "; [ -f $SYSFS/temperature ] && awk "{printf \"%.1f°C\\n\", \$1/1000}" $SYSFS/temperature 2>/dev/null || echo "(不可读)"
    else
        echo "驱动接口不存在(模块未加载或硬件不支持)"
    fi
    echo -n "电池: "; cat /sys/class/power_supply/BAT1/capacity 2>/dev/null; echo -n "% 状态: "; cat /sys/class/power_supply/BAT1/status 2>/dev/null
}

# ---------- 关闭健康模式(临时 100%) ----------
off() {
    [ -d "$SYSFS" ] && echo 0 > $SYSFS/health_mode && echo "已关闭健康模式(可充满 100%)"
    echo "如需持久关闭请: sudo systemctl disable 电池保养模式 并移除 modules-load 配置"
}

# ---------- 开启健康模式 ----------
on() {
    [ -d "$SYSFS" ] && echo 1 > $SYSFS/health_mode && echo "已开启健康模式(限充 80%)"
}

# ---------- 安装 ----------
install_all() {
    echo "==== 电池保养模式部署 ===="
    echo
    # [1/6] 构建
    echo "[1/6] 构建内核模块 ..."
    cd "$SRC" && make 2>&1 | tail -3
    ls -la "$SRC/acer-wmi-battery.ko"

    # [2/6] DKMS 注册(内核更新自动重建)
    echo "[2/6] 注册 DKMS ..."
    DKMS_CONF="$SRC/dkms.conf"
    if [ ! -f "$DKMS_CONF" ]; then
        cat > "$DKMS_CONF" << 'EOF'
PACKAGE_NAME="acer-wmi-battery"
PACKAGE_VERSION="1.0"
BUILT_MODULE_NAME[0]="acer-wmi-battery"
DEST_MODULE_LOCATION[0]="/kernel/drivers/platform/x86"
MAKE[0]="make KDIR=${kernel_source_dir}"
CLEAN="make clean"
AUTOINSTALL="yes"
EOF
    fi
    dkms remove acer-wmi-battery/1.0 --all 2>/dev/null || true
    dkms add "$SRC" && dkms build acer-wmi-battery/1.0 && dkms install acer-wmi-battery/1.0

    # [3/6] 开机自动加载 + 参数(健康模式开机即启, 防重置)
    echo "[3/6] 开机自动加载配置 ..."
    echo "acer_wmi_battery" > /etc/modules-load.d/acer-wmi-battery.conf
    echo "options acer_wmi_battery enable_health_mode=1" > /etc/modprobe.d/acer-wmi-battery.conf

    # [4/6] 加载模块
    echo "[4/6] 加载模块 ..."
    modprobe -r acer_wmi_battery 2>/dev/null || true
    modprobe acer_wmi_battery
    sleep 1

    # [5/6] 启用健康模式
    echo "[5/6] 启用健康模式(限充 80%) ..."
    if [ -d "$SYSFS" ]; then
        echo 1 > $SYSFS/health_mode
        echo "  已启用"
    else
        echo "  ⚠️ 驱动接口未出现! 硬件可能不支持(WMI GUID 应存在: 79772EC5-04B1-4BFD-843C-61E7F77B6CC9)"
        echo "  检查 dmesg: sudo dmesg | grep -i acer_wmi_battery"
    fi

    # [6/6] 验证
    echo "[6/6] 验证 ..."
    sleep 2
    status

    echo
    echo "================================================"
    echo "完成。80% 充电上限已启用(EC 固件级, 关机也生效)。"
    echo "当前电量高于 80% 时将立即停充, 低于 80% 恢复充电到 80% 停。"
    echo "临时需要 100%: sudo bash $0 off → 充满后: sudo bash $0 on"
    echo "================================================"
}

# ---------- 入口 ----------
case "$1" in
    on)   on ;;
    off)  off ;;
    status|"") status ;;
    *)    install_all ;;
esac
