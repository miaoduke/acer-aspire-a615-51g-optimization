#!/bin/bash
# m3_gui.sh — M3 离电效能模式非交互切换（系统控制台专用后端）
# 用法: sudo m3_gui.sh on|off|status
# 与桌面 m3.sh 功能等价，但：无倒计时/无交互提问/无自动重启（GUI 内提示）
MODE="$1"
SVC=/etc/systemd/system/m3-power-saver.service

ac_online() {
  for d in /sys/class/power_supply/*; do
    [ "$(cat "$d/type" 2>/dev/null)" = "Mains" ] && [ "$(cat "$d/online" 2>/dev/null)" = "1" ] && { echo 1; return; }
  done
  echo 0
}

mode_on() {
  echo "=== 进入 M3 离电效能模式 ==="
  systemctl stop acdc-profile 2>/dev/null
  systemctl disable acdc-profile 2>/dev/null
  # 直写 EPP=power（不再依赖 PPD——已 mask，2026-08-20 修复）
  # 关键: 必须先切 governor=powersave（intel_pstate 在 performance governor 下 EPP 写入返回 EINVAL）
  echo powersave > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null
  # 路径为 per-CPU cpufreq; EBUSY(设备忙)是 intel_pstate 瞬时并发, 重试 5 次
  ok=0
  for i in 1 2 3 4 5; do
    if echo power > /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference 2>/dev/null; then ok=1; break; fi
    sleep 1
  done
  [ "$ok" = "1" ] || { echo "❌ EPP 写入失败(EBUSY 重试 5 次后仍失败)"; exit 1; }
  cat > "$SVC" <<'EOF'
[Unit]
Description=M3 low-power profile keep
[Service]
Type=oneshot
ExecStart=/bin/bash -c 'echo powersave > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor; for i in 1 2 3 4 5; do echo power > /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference 2>/dev/null && break; sleep 1; done; echo 10000000 > /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw; echo 1 > /sys/devices/system/cpu/intel_pstate/no_turbo'
[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable m3-power-saver.service >/dev/null 2>&1
  # M3 低功耗: 主动设 PL1=10W(覆盖 ac-perf 残留的 25W),
  # 使 turbo-guard 场景感知判定成立 -> 自动保持涡轮关闭(2026-08-20)
  echo 10000000 > /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw 2>/dev/null
  echo 1 > /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null
  echo "✅ M3 已生效（EPP=power，acdc-profile 已停，PL1=10W，Turbo 关，重启后保持）"
  echo "GPU 建议: 集显可再省 ~7.7W，但需重启（请在控制台 GPU 模式切换）"
}

mode_off() {
  echo "=== 退出 M3，恢复自动模式 ==="
  systemctl enable acdc-profile 2>/dev/null
  systemctl start acdc-profile 2>/dev/null
  systemctl disable m3-power-saver.service 2>/dev/null
  rm -f "$SVC"
  systemctl daemon-reload
  # 2026-08-20 修复: 只设 PPD 档位不恢复场景参数 -> 参数残留无法匹配场景, UI 显示占位
  # 改为按当前供电恢复默认场景(与 acdc 联动逻辑一致)
  DEFAULT_SCENE=/home/<USER>/.config/system-console/default_scene
  LAST_AC=ac-bal
  LAST_DC=bat-bal
  [ -f "$DEFAULT_SCENE" ] && . "$DEFAULT_SCENE"
  # 相对路径: 脚本在 backend/, 场景管理.sh 在上级 scripts/
  DIR="$(cd "$(dirname "$0")" && pwd)"
  SCENE_MGR="$DIR/../scripts/场景管理.sh"
  if [ "$(ac_online)" = "1" ]; then
    "$SCENE_MGR" "$LAST_AC" >/dev/null 2>&1
    echo "✅ 已退出 M3，恢复插电默认场景：$LAST_AC（自动切换已恢复）"
  else
    "$SCENE_MGR" "$LAST_DC" >/dev/null 2>&1
    echo "✅ 已退出 M3，恢复离电默认场景：$LAST_DC（自动切换已恢复）"
  fi
}

status() {
  echo "EPP=$(cat /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference 2>/dev/null) acdc=$(systemctl is-active acdc-profile) gpu=$(prime-select query) AC=$(ac_online) turbo=$(cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null)"
}

case "$MODE" in
  on) mode_on ;;
  off) mode_off ;;
  status) status ;;
  *) echo "用法: $0 on|off|status"; exit 1 ;;
esac