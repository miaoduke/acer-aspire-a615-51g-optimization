#!/bin/bash
# kernel_guard.sh — 内核变动检测 + 一键修复
# 功能: 检测内核升级是否导致优化功能失效(模块/服务/参数/驱动), 一键修复可自动修复的项。
# 用法: kernel_guard.sh check|repair
# check  只检测并输出状态 (每项 ✓/✗)
# repair 检测并修复可自动修复的项 (root)
#
# ⚠️ 2026-08-29 重要说明（本脚本的局限与根治方案）：
#   本脚本对 acer-wmi-battery 采取的是【事后重编译】策略（第 25-35 行检测 + repair 时 make 重编），
#   即内核升级后必须【有人手动跑一次 repair】才能恢复，升级完成到修复之前功能一直是断的。
#   这正是 0818/0821/0829 三次同类故障的共同模式。
#
#   ✅ 根治方案 = 把模块注册进 DKMS（升级时由系统自动重建，无需人工介入）：
#        sudo bash 性能优化方案_20260822/acer-wmi-battery_源码备份/register_dkms.sh
#      注册后本脚本第 1 项检查将持续为 ✓，且不再需要 repair。
#
#   参考：2026-08-29 12:30 内核 28→30 升级，该模块失效（modprobe: not found in
#        /lib/modules/7.0.0-30-generic），电池温度功能中断，即本局限的实况。
# 配置路径
KERN=$(uname -r)
MOD_SRC=/home/<USER>/acer-wmi-battery      # 自定义模块源码
MOD_NAME=acer_wmi_battery                   # 模块名(下划线, modprobe 用)
MOD_FILE=acer-wmi-battery                   # 内核模块文件(连字符, 路径用)
WMI_TEMP=/sys/bus/wmi/drivers/acer-wmi-battery/temperature
RAPL=/sys/class/powercap/intel-rapl:0
LOG=/var/log/kernel_guard.log
declare -a FAILS=()   # 失败项 (可修复)

log() { echo "$(date '+%F %T') $*" >> "$LOG"; }
mark() { # $1=状态  $2=项描述
  local s=$1; shift
  echo "  $s $*"
}

echo "=== 内核变动检测 (内核 $KERN) ==="

# ---- 1. acer-wmi-battery 模块 ----
if [ -f "/lib/modules/$KERN/extra/$MOD_FILE.ko" ]; then
  mark "✓" "模块 $MOD_FILE 已针对当前内核编译"
else
  mark "✗" "模块 $MOD_FILE 缺失 (内核升级后未重新编译)"
  FAILS+=("module")
fi
if lsmod | grep -q "$MOD_NAME"; then
  mark "✓" "模块已加载"
else
  mark "✗" "模块未加载"
  FAILS+=("module_load")
fi
if [ -f "$WMI_TEMP" ]; then
  mark "✓" "WMI 温度接口可读 ($(cat $WMI_TEMP 2>/dev/null | awk '{print $1/1000"°C"}'))"
else
  mark "✗" "WMI 温度接口不存在"
  FAILS+=("module_load")
fi

# ---- 2. nvidia DKMS 模块 ----
if dkms status 2>/dev/null | grep -q "$KERN"; then
  mark "✓" "nvidia DKMS 适配当前内核"
else
  mark "✗" "nvidia DKMS 未适配当前内核"
  FAILS+=("dkms")
fi

# ---- 3. 优化服务 ----
for s in acdc-profile undervolt thermal-guard; do
  if systemctl is-active "$s" >/dev/null 2>&1; then
    mark "✓" "服务 $s 运行中"
  else
    mark "✗" "服务 $s 未运行"
    FAILS+=("service:$s")
  fi
done

# ---- 4. GRUB 内核参数 ----
for p in "intel_idle.max_cstate=4" "zswap.enabled=1" "zswap.shrinker_enabled=1"; do
  if grep -q "$p" /proc/cmdline; then
    mark "✓" "内核参数 $p"
  else
    mark "✗" "内核参数 $p 缺失 (需 update-grub + 重启)"
    FAILS+=("param:$p")
  fi
done

# ---- 5. sysfs 优化项 ----
chk() { # $1=路径 $2=期望值 $3=项名
  local v=$(cat "$1" 2>/dev/null)
  if [ "$v" = "$2" ]; then
    mark "✓" "$3 ($v)"
  else
    mark "✗" "$3 (当前 $v, 期望 $2)"
    FAILS+=("sysfs:$3")
  fi
}
chk /sys/module/zswap/parameters/enabled Y zswap
chk /sys/module/zswap/parameters/shrinker_enabled Y zswap-shrinker
chk /sys/devices/system/cpu/intel_pstate/hwp_dynamic_boost 1 hwp_dynamic_boost
chk /sys/bus/pci/devices/0000:01:00.0/power/runtime_status suspended MX150-D3cold
[ -n "$(grep swapfile /proc/swaps)" ] && mark "✓" "swap 文件挂载" || { mark "✗" "swap 未挂载"; FAILS+=("swap"); }
[ -f "$RAPL/constraint_0_power_limit_uw" ] && mark "✓" "RAPL PL 接口可写" || { mark "✗" "RAPL PL 接口缺失"; FAILS+=("rapl"); }

# ---- 修复 ----
if [ "${1:-}" = "repair" ]; then
  if [ ${#FAILS[@]} -eq 0 ]; then
    echo "全部功能正常，无需修复。"
  else
    echo "=== 一键修复 ${#FAILS[@]} 项 ==="
    for f in "${FAILS[@]}"; do
      case "$f" in
        module)
          echo "  重编译 $MOD_NAME 针对 $KERN ..."
          # 2026-08-29 修复: 原写法 KDIR="/usr/src/linux-headers-$KERN-generic" 多了 -generic
          # (KERN 已含 -generic), 路径实为 /usr/src/linux-headers-7.0.0-30-generic-generic → 不存在。
          # 此前因 Makefile 忽略 KDIR 而未被察觉; Makefile 修好支持 KDIR 后此错会导致重编译失败, 故同步修正。
          (cd "$MOD_SRC" && make KDIR="/usr/src/linux-headers-$KERN" >/dev/null 2>&1 \
            && mkdir -p "/lib/modules/$KERN/extra" \
            && cp "$MOD_SRC/$MOD_FILE.ko" "/lib/modules/$KERN/extra/" \
            && depmod -a && echo "    模块已重新编译安装" && log "repair: 重编译 $MOD_FILE for $KERN") \
            || echo "    模块重编译失败 (需手动: cd $MOD_SRC && make KDIR=...)"
          ;;
        module_load)
          echo "  加载 $MOD_NAME ..."
          modprobe "$MOD_NAME" 2>/dev/null && echo "    模块已加载" && log "repair: 加载 $MOD_NAME" \
            || echo "    加载失败 (检查 modules-load.d / 模块依赖)"
          ;;
        service:*)
          svc_name=${f#service:}
          echo "  重启服务 $svc_name ..."
          systemctl restart "$svc_name" && systemctl enable "$svc_name" >/dev/null 2>&1 \
            && echo "    服务 $svc_name 已重启并自启" && log "repair: 重启 $svc_name" \
            || echo "    服务 $svc_name 重启失败"
          ;;
        dkms)
          echo "  dkms autoinstall ..."
          dkms autoinstall >/dev/null 2>&1 && echo "    DKMS 已自动重装" && log "repair: dkms autoinstall" \
            || echo "    DKMS 重装失败 (需手动: sudo dkms autoinstall)"
          ;;
        param:*)
          echo "  ${f#param:} — 需编辑 /etc/default/grub + update-grub + 重启 (不自动改)"
          ;;
        sysfs:*)
          echo "  ${f#sysfs:} — 需检查场景/服务 (重启后系统脚本应已设置)"
          ;;
        swap|rapl)
          echo "  $f — 需检查 fstab/系统启动 (通常重启自动恢复)"
          ;;
      esac
    done
  fi
fi

echo "=== 完成 ==="