#!/bin/bash
# adapt_test.sh — 电源模式适配测试向导
# 在新机器/重装系统后运行：检测硬件能力 → 输出兼容性报告 → 给出推荐配置
# 用法: sudo bash adapt_test.sh [apply]
#   无参数 = 仅测试输出报告
#   apply  = 测试 + 应用可安全自动化的配置

BASE="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0; FAIL=0; SKIP=0

ok()   { echo "  ✓ $1"; PASS=$((PASS+1)); }
bad()  { echo "  ✗ $1"; FAIL=$((FAIL+1)); }
skip() { echo  "  ○ $1 (跳过)"; SKIP=$((SKIP+1)); }

echo "========================================"
echo " 电源模式适配测试 ($(date '+%F %T'))"
echo "========================================"
echo "机型: $(cat /sys/class/dmi/id/product_name 2>/dev/null)"
echo "CPU:  $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs)"
echo "内核: $(uname -r)"
echo

echo "--- 1. 核心设备探测 ---"
DRM_CARD=""
for card in /sys/class/drm/card[0-9]; do
    drv=$(readlink -f "$card/device/driver" 2>/dev/null | xargs basename 2>/dev/null)
    if [ "$drv" = "i915" ] || [ "$drv" = "xe" ] || [ "$drv" = "amdgpu" ]; then
        DRM_CARD="$card"
        ok "iGPU DRM 设备: $card ($drv)"
        if [ -f "$card/gt_max_freq_mhz" ]; then
            ok "GPU GT 频率控制可用"
        else
            skip "GT 频率控制（驱动不支持）"
        fi
        break
    fi
done
[ -z "$DRM_CARD" ] && bad "未找到 iGPU DRM 设备"

BAT=""
for d in /sys/class/power_supply/*; do
    [ "$(cat $d/type 2>/dev/null)" = "Battery" ] && BAT="$d" && break
done
[ -n "$BAT" ] && ok "电池: $BAT" || bad "未找到电池"
[ -f "$BAT/charge_control_end_threshold" ] && ok "充电上限接口(原生)" || skip "充电上限接口（固件不支持属正常）"

ACD=""
for d in /sys/class/power_supply/*; do
    [ "$(cat $d/type 2>/dev/null)" = "Mains" ] && ACD="$d" && break
done
[ -n "$ACD" ] && ok "AC 适配器: $ACD" || bad "未找到 AC 适配器"

TEMPZ=""
for z in /sys/class/thermal/thermal_zone*; do
    typ=$(cat $z/type 2>/dev/null)
    case "$typ" in
        x86_pkg_temp|*cpu*|*CPU*|coretemp*) TEMPZ="$z"; break;;
    esac
done
[ -n "$TEMPZ" ] && ok "CPU 温度源: $TEMPZ ($(cat $TEMPZ/type))" || skip "专用 CPU 温度区（用 hwmon 回退）"

echo
echo "--- 2. RAPL 功耗控制 ---"
if ls /sys/class/powercap/intel-rapl:* >/dev/null 2>&1 || ls /sys/class/powercap/amdgpu* >/dev/null 2>&1; then
    PKG=$(ls -d /sys/class/powercap/intel-rapl:0 2>/dev/null || true)
    if [ -n "$PKG" ] && [ -f "$PKG/constraint_0_power_limit_uw" ]; then
        ok "RAPL PL 控制: $PKG"
        echo "      当前 PL1=$(($(cat $PKG/constraint_0_power_limit_uw)/1000000))W PL2=$(($(cat $PKG/constraint_1_power_limit_uw 2>/dev/null || echo 0)/1000000))W"
    else
        bad "RAPL PL 控制文件缺失"
    fi
else
    bad "无 RAPL 域（非 Intel 或太老）"
fi

echo
echo "--- 3. CPU 调频 ---"
if [ -d /sys/devices/system/cpu/intel_pstate ]; then
    ok "intel_pstate active 模式: $(cat /sys/devices/system/cpu/intel_pstate/status 2>/dev/null)"
    [ -f /sys/devices/system/cpu/intel_pstate/hwp_dynamic_boost ] \
        && ok "hwp_dynamic_boost 可用" || skip "hwp_dynamic_boost"
elif ls /sys/devices/system/cpu/cpufreq/policy0/scaling_available_governors >/dev/null 2>&1; then
    ok "通用 cpufreq（acpi-cpufreq/intel_pstate passive）"
else
    bad "无调频接口"
fi
EPP=$(ls /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference 2>/dev/null)
[ -n "$EPP" ] && ok "EPP 接口可用" || skip "EPP（CPU 不支持或 amd_pstate）"

echo
echo "--- 4. 温度守护依赖 ---"
if [ -d /sys/class/thermal ]; then
    N=$(ls -d /sys/class/thermal/cooling_device* 2>/dev/null | wc -l)
    ok "cooling devices: $N 个"
else
    bad "无 thermal 子系统"
fi
if [ -e /dev/cpu/0/msr ]; then
    ok "MSR 设备可用（限流状态读取）"
else
    skip "MSR 未加载（modprobe msr 后可用）"
fi

echo
echo "--- 5. Acer WMI（仅acer机型） ---"
VENDOR=$(cat /sys/class/dmi/id/sys_vendor 2>/dev/null)
if echo "$VENDOR" | grep -qi acer; then
    GUIDS=$(ls /sys/bus/wmi/devices/ 2>/dev/null | tr '\n' ' ')
    echo "$GUIDS" | grep -qi "79772EC5" && ok "WMI battery health GUID 存在" || skip "battery health GUID"
    if [ -d /sys/bus/wmi/drivers/acer-wmi-battery ]; then
        ok "acer-wmi-battery 驱动已加载"
        # 实测温度读取验证
        T=$(cat /sys/bus/wmi/drivers/acer-wmi-battery/temperature 2>/dev/null)
        [ -n "$T" ] && ok "WMI 温度读取正常 (${T})" || bad "WMI 温度读取失败"
    else
        skip "acer-wmi-battery 驱动未装（编译安装见项目文档）"
    fi
else
    skip "非 Acer 机型，跳过 WMI"
fi

echo
echo "--- 6. 系统工具链 ---"
for tool in rsync zenity curl; do
    command -v $tool >/dev/null && ok "$tool" || bad "$tool 缺失"
done
systemctl list-unit-files 2>/dev/null | grep -q smartd && ok "smartmontools" || skip "smartmontools 未装"

echo
echo "========================================"
echo " 结果: ✓$PASS 通过  ✗$FAIL 缺失  ○$SKIP 不适用"
echo "========================================"

# apply 模式：写探测结果供控制台使用
if [ "${1:-}" = "apply" ]; then
    OUT="$BASE/data/hardware_profile.json"
    mkdir -p "$(dirname "$OUT")"
    cat > "$OUT" <<EOF
{
  "probed_at": "$(date '+%F %T')",
  "product": "$(cat /sys/class/dmi/id/product_name 2>/dev/null)",
  "cpu": "$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs)",
  "kernel": "$(uname -r)",
  "drm_card": "$DRM_CARD",
  "battery": "$BAT",
  "ac_adapter": "$ACD",
  "cpu_temp_zone": "$TEMPZ",
  "rapl_pkg": "$PKG"
}
EOF
    echo "✓ 硬件档案已写入: $OUT"
fi

exit 0