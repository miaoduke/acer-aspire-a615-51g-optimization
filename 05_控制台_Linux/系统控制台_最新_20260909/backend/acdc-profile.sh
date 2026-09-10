#!/bin/bash
# AC/DC 自动场景切换 v9 (2026-08-21): 插电/离电自动切到用户设置的默认档位
# v4: 启动时无条件应用一次默认场景(冷启动归位)
# v8: 移除亮度联动(用户自主控制亮度) + hwp_dynamic_boost
# v9: 轮询 5s→3s(插拔电切换响应更跟手) + GPU GT 频率联动(AC=GPU_AC/DC=GPU_DC) + nvidia PowerMizer 联动
# 相对路径: 脚本在 backend/, 场景管理.sh 在上级 scripts/ -> 重装/换机可用
DIR="$(cd "$(dirname "$0")" && pwd)"
# 2026-09-01 修复: M3 生效时保持 M3 参数不覆盖。此前 acdc-profile 在 multi-user.target 后启动,
# 总比 M3 服务晚 → 冷启动归位会覆盖 M3 的 governor/EPP/PL1/turbo(重启后 M3 失效)。
# M3 退出(m3_gui.sh off)时会恢复 acdc-profile；此处 exit 0 → Restart=on-failure 不会重启。
if [ "$(systemctl is-enabled m3-power-saver 2>/dev/null)" = "enabled" ]; then
  exit 0
fi
# 真实用户家目录（脚本由 systemd 以 root 运行，$HOME=/root 需纠正为实际用户）
REAL_HOME="$(getent passwd "${SUDO_USER:-$(awk -F'[ :]' '/ALL=\(root\)/{print $1; exit}' /etc/sudoers.d/system-console 2>/dev/null)}" 2>/dev/null | cut -d: -f6)"
[ -n "$REAL_HOME" ] || REAL_HOME="$HOME"
DEFAULT_SCENE="$REAL_HOME/.config/system-console/default_scene"
SCENE_MGR="$DIR/../scripts/场景管理.sh"
LAST_AC=ac-bal
LAST_DC=bat-bal
GPU_AC=1100
GPU_DC=700
[ -f "$DEFAULT_SCENE" ] && . "$DEFAULT_SCENE"
sleep 10

# GPU GT 频率联动: 离电限制 iGPU 最高频(突发省电), 插电恢复全速(RP0=1100MHz)
# 2026-09-07 审计修复: 原版 head -1 恰好选中 card1(NVIDIA 卡), 而 gt_* 是 Intel i915
# 专属属性 → 写不存在的文件报“权限不够”, GT 联动自部署以来从未生效。
# 修正: 按 vendor 探测 Intel 卡(取 gt_max_freq_mhz 存在的那个), 不依赖 card 编号顺序。
set_gt_freq() {
  local mhz=$1 dev
  for dev in /sys/class/drm/card[0-9]; do
    [ -f "$dev/gt_max_freq_mhz" ] || continue
    # 只写 Intel 卡（device/vendor 含 0x8086）
    if grep -q 0x8086 "$dev/device/vendor" 2>/dev/null; then
      echo "$mhz" > "$dev/gt_max_freq_mhz" 2>/dev/null
      return $?
    fi
  done
  return 0
}
# nvidia PowerMizer 联动: 仅 prime=nvidia 时生效(X11), 1=Prefer Max(性能) / 0=Adaptive(省电)
# intel 模式: nvidia-settings 失败自动跳过(MX150 已 D3cold 断电, 本函数无操作)
set_nvidia_pm() {
  local mode=$1
  command -v nvidia-settings >/dev/null 2>&1 || return 0
  DISPLAY=:0 XAUTHORITY="$REAL_HOME/.Xauthority" \
    nvidia-settings -a "[gpu:0]/GPUPowerMizerMode=$mode" >/dev/null 2>&1
}
# IO 等待任务唤醒时动态提升最小 P-state(官方文档: 改善性能, gov=performance 时无效 -> ac-perf 无副作用)
echo 1 > /sys/devices/system/cpu/intel_pstate/hwp_dynamic_boost 2>/dev/null

# 冷启动归位: 无条件应用一次默认场景
AC0="$(cat /sys/class/power_supply/ACAD/online 2>/dev/null)"
if [ "$AC0" = "1" ]; then
  set_gt_freq "$GPU_AC"
  set_nvidia_pm 1
  "$SCENE_MGR" "$LAST_AC" >/dev/null 2>&1
  echo "$(date +%H:%M:%S) 启动: 插电 -> 默认 $LAST_AC (GT ${GPU_AC}MHz)" >> /var/log/acdc-profile.log
else
  set_gt_freq "$GPU_DC"
  set_nvidia_pm 0
  "$SCENE_MGR" "$LAST_DC" >/dev/null 2>&1
  echo "$(date +%H:%M:%S) 启动: 离电 -> 默认 $LAST_DC (GT ${GPU_DC}MHz)" >> /var/log/acdc-profile.log
fi
PREV_AC="$AC0"
while true; do
  AC=$(cat /sys/class/power_supply/ACAD/online 2>/dev/null)
  if [ "$AC" != "$PREV_AC" ]; then
    PREV_AC="$AC"
    [ -f "$DEFAULT_SCENE" ] && . "$DEFAULT_SCENE"
    if [ "$AC" = "1" ]; then
          set_gt_freq "$GPU_AC"
      set_nvidia_pm 1
      "$SCENE_MGR" "$LAST_AC" >/dev/null 2>&1
      echo "$(date +%H:%M:%S) 插电 -> 默认 $LAST_AC (GT ${GPU_AC}MHz)" >> /var/log/acdc-profile.log
    else
          set_gt_freq "$GPU_DC"
      set_nvidia_pm 0
      "$SCENE_MGR" "$LAST_DC" >/dev/null 2>&1
      echo "$(date +%H:%M:%S) 离电 -> 默认 $LAST_DC (GT ${GPU_DC}MHz)" >> /var/log/acdc-profile.log
    fi
  fi
  sleep 3
done
