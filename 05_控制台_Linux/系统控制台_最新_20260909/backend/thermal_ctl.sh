#!/bin/bash
# thermal_ctl.sh — 散热/功耗控制统一入口（sudoers 白名单限定）
# 用法: thermal_ctl.sh <fan_boost|tcc|pclamp|maxperf|usb|wifi> <参数>
# 全部参数严格校验，越界即拒绝。
set -u

CUR=/sys/class/thermal
CUR17=$CUR/cooling_device17
CUR16=$CUR/cooling_device16
PSTATE=/sys/devices/system/cpu/intel_pstate

die() { echo "参数无效: $1" >&2; exit 1; }

case "${1:-}" in
  # 风扇强制冷: on=全速(含5/6/7三个有效设备), off=恢复自动
  fan_boost)
    case "${2:-}" in
      on) v=1;;
      off) v=0;;
      *) die "fan_boost 需要 on/off";;
    esac
    for i in 5 6 7; do echo "$v" > $CUR/cooling_device$i/cur_state; done
    echo "fan_boost $2 → $v";;
  # CPU 温度墙偏移 TCC Offset: 0-63（63=降得最多，CPU 更早降频）
  tcc)
    v=${2:-}; [ "$v" -ge 0 ] 2>/dev/null && [ "$v" -le 63 ] || die "tcc 0-63"
    echo "$v" > $CUR17/cur_state
    sleep 1
    R=$(cat $CUR17/cur_state 2>/dev/null || echo -1)
    echo "TCC 目标 $v → 实测 $R"
    [ "$R" = "$v" ] || { echo "⚠ 实测与目标不一致(内核钳制)" >&2; exit 2; };;
  # intel_powerclamp 强制降载: 0-100（% 时间空闲）
  pclamp)
    v=${2:-}; [ "$v" -ge 0 ] 2>/dev/null && [ "$v" -le 100 ] || die "pclamp 0-100"
    echo "$v" > $CUR16/cur_state
    sleep 1
    R=$(cat $CUR16/cur_state 2>/dev/null || echo -1)
    echo "强制降载 目标 $v% → 实测 $R%"
    [ "$R" = "$v" ] || { echo "⚠ 实测与目标不一致(内核钳制)" >&2; exit 2; };;
  # CPU 频率上限百分比: 1-100（intel_pstate max_perf_pct）
  maxperf)
    v=${2:-}; [ "$v" -ge 1 ] 2>/dev/null && [ "$v" -le 100 ] || die "maxperf 1-100"
    echo "$v" > $PSTATE/max_perf_pct
    sleep 1
    R=$(cat $PSTATE/max_perf_pct 2>/dev/null || echo -1)
    echo "频率上限 目标 $v% → 实测 $R%"
    [ "$R" = "$v" ] || { echo "⚠ 实测与目标不一致(内核钳制)" >&2; exit 2; };;
  # PL1/PL2 功耗墙: pl <PL1_W> <PL2_W>（写 RAPL，读回验证生效/钳制）
  pl)
    pl1=${2:-}; pl2=${3:-}
    [ "$pl1" -ge 1 ] 2>/dev/null && [ "$pl1" -le 30 ] || die "PL1 需 1-30W"
    [ "$pl2" -ge 1 ] 2>/dev/null && [ "$pl2" -le 45 ] || die "PL2 需 1-45W"
    RAPL=/sys/class/powercap/intel-rapl:0
    echo $((pl1*1000000)) > $RAPL/constraint_0_power_limit_uw
    echo $((pl2*1000000)) > $RAPL/constraint_1_power_limit_uw
    sleep 1
    R1=$(cat $RAPL/constraint_0_power_limit_uw 2>/dev/null || echo 0)
    R2=$(cat $RAPL/constraint_1_power_limit_uw 2>/dev/null || echo 0)
    echo "PL1 目标 ${pl1}W → 实测 $((R1/1000000))W | PL2 目标 ${pl2}W → 实测 $((R2/1000000))W"
    if [ $((R1/1000000)) -ne "$pl1" ] || [ $((R2/1000000)) -ne "$pl2" ]; then
      echo "⚠ 注意: 实测与目标不一致(可能被固件钳制或热管理覆盖)" >&2
      exit 2
    fi;;
  # USB 自动挂起: on=auto(省电) off=on(常供电)
  usb)
    case "${2:-}" in
      on) v=auto;;
      off) v=on;;
      *) die "usb 需要 on/off";;
    esac
    for d in /sys/bus/usb/devices/[0-9]*/power/control; do echo "$v" > "$d" 2>/dev/null; done
    echo "usb autosuspend → $v";;
  # 摄像头: on=加载驱动(开) off=卸载驱动(关, 隐私保护), 均验证
  camera)
    case "${2:-}" in
      on)
        modprobe uvcvideo 2>/dev/null
        sleep 1
        if lsmod | grep -q "^uvcvideo"; then
          echo "camera on OK (uvcvideo 已加载, /dev/video0)"
        else
          echo "camera on FAIL 驱动加载失败" >&2
          exit 1
        fi;;
      off)
        modprobe -r uvcvideo 2>/dev/null
        sleep 1
        if lsmod | grep -q "^uvcvideo"; then
          echo "camera off FAIL 驱动仍加载" >&2
          exit 1
        else
          echo "camera off OK (uvcvideo 已卸载, 摄像头已禁用)"
        fi;;
      *) die "camera 需要 on/off";;
    esac;;
  # WiFi 电源管理: on=省电 off=性能（iwconfig, 2026-08-20 修复: 原用 iw 命令不存在静默失败）
  wifi)
    case "${2:-}" in
      on) v=on;;
      off) v=off;;
      *) die "wifi 需要 on/off";;
    esac
    for w in /sys/class/net/wl*/; do
      dev=$(basename "$w")
      /usr/sbin/iwconfig "$dev" power "$v" 2>/dev/null
    done
    echo "wifi power_save → $v";;
  *)
    die "未知命令 ${1:-}";;
esac