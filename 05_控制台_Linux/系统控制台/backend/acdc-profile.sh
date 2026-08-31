#!/bin/bash
# AC/DC 自动场景切换 v9 (2026-08-21): 插电/离电自动切到用户设置的默认档位
# v4: 启动时无条件应用一次默认场景(冷启动归位)
# v8: 移除亮度联动(用户自主控制亮度) + hwp_dynamic_boost
# v9: 轮询 5s→3s(插拔电切换响应更跟手) + GPU GT 频率联动(AC=GPU_AC/DC=GPU_DC) + nvidia PowerMizer 联动
# 相对路径: 脚本在 backend/, 场景管理.sh 在上级 scripts/ -> 重装/换机可用
DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_SCENE=/home/<USER>/.config/system-console/default_scene
SCENE_MGR="$DIR/../scripts/场景管理.sh"
LAST_AC=ac-bal
LAST_DC=bat-bal
GPU_AC=1100
GPU_DC=700
[ -f "$DEFAULT_SCENE" ] && . "$DEFAULT_SCENE"
sleep 10

# GPU GT 频率联动: 离电限制 iGPU 最高频(突发省电), 插电恢复全速(RP0=1100MHz)
set_gt_freq() {
  local mhz=$1
  local dev=$(ls /sys/class/drm/ | grep -E "^card[0-9]+$" | head -1)
  [ -n "$dev" ] && echo "$mhz" > "/sys/class/drm/$dev/gt_max_freq_mhz" 2>/dev/null
}
# nvidia PowerMizer 联动: 仅 prime=nvidia 时生效(X11), 1=Prefer Max(性能) / 0=Adaptive(省电)
# intel 模式: nvidia-settings 失败自动跳过(MX150 已 D3cold 断电, 本函数无操作)
set_nvidia_pm() {
  local mode=$1
  command -v nvidia-settings >/dev/null 2>&1 || return 0
  DISPLAY=:0 XAUTHORITY=/home/<USER>/.Xauthority \
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
