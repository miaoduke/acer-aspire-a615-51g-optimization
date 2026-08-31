#!/bin/bash
# =============================================================================
# register_dkms.sh — 将 acer-wmi-battery 注册进 DKMS（彻底解决内核升级失效）
# =============================================================================
# 为什么需要它（2026-08-29 审计发现）：
#   · 该模块目前是【手动 make install】安装的，装到
#     /usr/lib/modules/7.0.0-28-generic/extra/acer-wmi-battery.ko，vermagic 锁定 28。
#   · dkms.conf 早已写好（AUTOINSTALL=yes）但【从未注册】：/var/lib/dkms/ 下只有 nvidia。
#   · 内核未锁定（apt-mark showhold 为空）→ apt 一升级内核，模块必然失效，
#     这正是 2026-08-21 发生过的故障（"升级 29 后模块加载失败"）。
#   · 更糟的是：0821 为 29 编译的版本随 29 内核被移除而丢失，
#     现在能用纯属侥幸（28 的旧 .ko 一直在）。
#   · 当前内核是【无意】回退到 28 的（用户确认），无任何记录 → 随时可能被再次改变。
#
#   🔴 **故障已在审计当天真实发生（2026-08-29 12:30）**：
#      系统重启到 7.0.0-30-generic，模块因未随新内核重建而失效：
#        modprobe: FATAL: Module acer_wmi_battery not found in directory /lib/modules/7.0.0-30-generic
#      → 电池温度功能当前处于失效状态（/sys/bus/wmi/drivers/acer-wmi-battery/ 不存在）。
#      本脚本正是为此编写：注册后不仅修复当下，且今后内核升级自动重建。
#
# 注册 DKMS 后：内核升级时自动为新内核重建模块，一劳永逸。
#
# 用法: sudo bash register_dkms.sh
# 前置: 按项目铁律 L1（系统级修改前必须快照），建议先执行：
#       sudo bash 系统控制台/backend/snapshot.sh create "DKMS注册前"
#
# 环境已确认就绪（2026-08-29 核验）：
#   · /usr/src/linux-headers-7.0.0-30-generic 存在
#   · dkms / make / gcc 13.3.0 均已安装
#   · 源码完好：/home/<USER>/acer-wmi-battery/{acer-wmi-battery.c,Makefile,dkms.conf}
#   · 仅缺 root 权限执行
# =============================================================================
set -e

SRC=/home/<USER>/acer-wmi-battery
NAME=acer-wmi-battery
VER=1.0
CUR_KV=$(uname -r)
MANUAL_KO="/usr/lib/modules/${CUR_KV}/extra/${NAME}.ko"
BACKUP_DIR="/root/acer-wmi-battery_backup_$(date +%Y%m%d_%H%M%S)"

# ---------- 0. 环境检查 ----------
[ "$(id -u)" = "0" ] || { echo "❌ 需要 root: sudo bash $0" >&2; exit 1; }
[ -d "$SRC" ] || { echo "❌ 源码目录不存在: $SRC" >&2; exit 1; }
for f in acer-wmi-battery.c Makefile dkms.conf; do
    [ -f "$SRC/$f" ] || { echo "❌ 缺少源文件: $SRC/$f" >&2; exit 1; }
done
command -v dkms >/dev/null || { echo "❌ 未安装 dkms: apt install dkms" >&2; exit 1; }
command -v make >/dev/null || { echo "❌ 未安装 make" >&2; exit 1; }
[ -d "/usr/src/linux-headers-${CUR_KV}" ] || \
    { echo "❌ 缺少内核头文件: apt install linux-headers-${CUR_KV}" >&2; exit 1; }

# 关键前置校验: Makefile 必须支持 KDIR 传入, 否则 DKMS 自动重建会编译错内核版本。
# (原 Makefile 硬编码 $(shell uname -r), 忽略 dkms.conf 的 KDIR → 内核升级未重启时
#  会按旧内核编译却装进新内核目录 → vermagic 不匹配 → 故障重演)
echo "检查 Makefile 是否支持 KDIR 传入..."
if ! grep -q 'KDIR *?*=' "$SRC/Makefile"; then
    echo "❌ Makefile 不支持 KDIR 传入，DKMS 自动重建会失败。" >&2
    echo "   已于 2026-08-29 修复此问题，请用修复版覆盖：" >&2
    echo "   cp 性能优化方案_20260822/acer-wmi-battery_源码备份/Makefile $SRC/Makefile" >&2
    exit 1
fi
# 实测传入生效性（干跑，不编译）
if ! make -C "$SRC" -n KDIR="/usr/src/linux-headers-${CUR_KV}" 2>/dev/null | \
     grep -q "linux-headers-${CUR_KV}"; then
    echo "❌ Makefile 未采用传入的 KDIR（可能仍硬编码 uname -r）" >&2
    exit 1
fi
echo "  ✓ Makefile 支持 KDIR 且传入生效"

echo "=== acer-wmi-battery DKMS 注册 ==="
echo "源码: $SRC / 当前内核: $CUR_KV"
echo ""

# ---------- 1. 备份手动安装的模块（防同名冲突） ----------
echo "[1/5] 备份现有手动安装模块..."
mkdir -p "$BACKUP_DIR"
if [ -f "$MANUAL_KO" ]; then
    cp -v "$MANUAL_KO" "$BACKUP_DIR/"
    rm -f "$MANUAL_KO"
    echo "  ✓ 已备份并移除手动安装副本（避免与 DKMS 版本同名冲突）"
else
    echo "  - 未找到手动安装副本（$MANUAL_KO），跳过"
fi

# ---------- 2. 清理旧注册 ----------
echo "[2/5] 清理可能存在的旧 DKMS 注册..."
dkms remove ${NAME}/${VER} --all 2>/dev/null || echo "  - 无旧注册"

# ---------- 3. 注册 + 构建 + 安装 ----------
echo "[3/5] DKMS add / build / install..."
dkms add "$SRC"
dkms build ${NAME}/${VER}
dkms install ${NAME}/${VER}

# ---------- 4. depmod ----------
echo "[4/5] depmod..."
depmod -a "$CUR_KV"

# ---------- 5. 验证 ----------
echo "[5/5] 验证..."
echo ""
echo "--- DKMS 状态 ---"
dkms status
echo ""
echo "--- 模块信息（vermagic 应为 $CUR_KV）---"
modinfo ${NAME} 2>&1 | grep -E "^(filename|vermagic)"
echo ""
echo "--- 重新加载并读温度 ---"
modprobe -r acer_wmi_battery 2>/dev/null || true
modprobe acer_wmi_battery
sleep 2
if [ -f /sys/bus/wmi/drivers/acer-wmi-battery/temperature ]; then
    echo "✅ 电池温度: $(awk '{printf "%.1f°C", $1/1000}' /sys/bus/wmi/drivers/acer-wmi-battery/temperature)"
else
    echo "⚠️ 温度接口未出现，检查: dmesg | grep -i acer_wmi_battery"
fi

echo ""
echo "================================================"
echo "完成。今后内核升级会自动重建本模块（AUTOINSTALL=yes）。"
echo ""
# 仅在确实备份过手动安装副本时才给出 cp 回滚（否则 $BACKUP_DIR 为空目录，命令会失败）
if [ -f "$BACKUP_DIR/${NAME}.ko" ]; then
    echo "【回滚方法】若出现问题："
    echo "  dkms remove ${NAME}/${VER} --all"
    echo "  cp $BACKUP_DIR/${NAME}.ko $MANUAL_KO"
    echo "  depmod -a && modprobe acer_wmi_battery"
else
    echo "【回滚方法】若出现问题（本次无手动安装副本可回退，卸载即可）："
    echo "  dkms remove ${NAME}/${VER} --all"
    echo "  depmod -a"
    echo "  注: 回滚后电池温度功能将失效（回到修复前状态），可重新运行本脚本恢复。"
fi
echo ""
echo "【验证自动重建是否真生效】下次内核升级后执行："
echo "  dkms status          # 应显示新内核版本 installed"
echo "================================================"
