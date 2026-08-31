#!/bin/bash
# m3.sh v2.0 — M3 离电效能模式一键切换（进入/退出/状态 + GPU 切换引导 + 自动重启）
# 用法:
#   ./m3.sh          无参数 → 交互菜单
#   ./m3.sh on       进入 M3 离电效能（DC + power-saver，可选切集显）
#   ./m3.sh off      退出 M3，恢复自动模式（可选切回独显）
#   ./m3.sh status   查看当前状态
# 关联: 三电源模式方案_20260818.md 第五节
# v2.0 新增: GPU 切换选择与建议 / 事前提醒+反悔倒计时 / 自动重启 / M3 持久化(重启后保持)

MODE="$1"
M3_SERVICE="/etc/systemd/system/m3-power-saver.service"

# Ctrl+C = 友好取消
trap 'echo ""; echo "⏹  已取消，操作中止"; exit 1' INT

# 倒计时: $1=秒数 $2=提示文字。交互终端中按 空格/Enter/s 跳过等待, Ctrl+C 取消
countdown() {
  local SECS=$1
  echo -n "$2"
  if [ -t 0 ]; then  # 交互终端: 监听按键
    for i in $(seq $SECS -1 1); do
      echo -n " $i"
      if read -t 1 -n 1 -s KEY 2>/dev/null; then
        if [ "$KEY" = " " ] || [ "$KEY" = "s" ] || [ "$KEY" = "S" ] || [ -z "$KEY" ]; then
          echo ""
          echo "  ⏩ 跳过等待，继续执行"
          return 0
        fi
      fi
    done
  else  # 非交互(管道/脚本): 正常倒计时
    for i in $(seq $SECS -1 1); do
      echo -n " $i"
      sleep 1
    done
  fi
  echo ""
}

show_status() {
  AC=$(cat /sys/class/power_supply/ACAD/online)
  echo "--- 当前状态 ---"
  echo "供电          : $([ "$AC" = "1" ] && echo "AC(插电)" || echo "DC(电池)")"
  echo "PPD 档位     : $(powerprofilesctl get)"
  echo "EPP          : $(cat /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference 2>/dev/null)"
  echo "acdc-profile : $(systemctl is-active acdc-profile)"
  echo "GPU          : $(prime-select query)"
}

# GPU 切换引导: $1=目标(intel/nvidia)。提醒 + 反悔倒计时 + prime-select + 自动重启
gpu_switch() {
  local TARGET=$1
  echo ""
  echo "⚠️  重要提醒（请仔细阅读）:"
  echo "  · 切换 GPU 到 $TARGET 需要【重启系统】（1 次重启生效）"
  echo "  · 重启会中断所有会话和未保存工作 —— 请先保存重要文件！"
  echo "  · 切换后如需恢复: 运行 ./m3.sh off（会自动引导切回独显）"
  echo ""
  countdown 10 "  ⏳ 10 秒反悔窗口: 按 空格 跳过等待, Ctrl+C 取消本次切换..."
  sudo prime-select "$TARGET" || { echo "❌ GPU 切换失败"; return 1; }
  echo "✅ GPU 已切换为 $TARGET（重启后生效）"
  sync
  echo ""
  echo "  ⏳ 即将自动重启（取消则不会重启，GPU 配置已切换、下次手动重启时生效）"
  countdown 5 "     按 空格 跳过等待, Ctrl+C 取消重启..."
  sudo reboot
}

mode_on() {
  echo "=== 进入 M3 离电效能模式 ==="
  AC=$(cat /sys/class/power_supply/ACAD/online)
  if [ "$AC" = "1" ]; then
    echo "⚠️  当前插电(AC)。M3 为离电效能模式，AC 下省电意义有限。"
    echo "    5 秒后继续（安静场景可用），Ctrl+C 可取消..."
    sleep 5
  fi
  echo "[1/4] 停用并禁用 acdc-profile 自动切换..."
  sudo systemctl stop acdc-profile || { echo "❌ 失败"; exit 1; }
  sudo systemctl disable acdc-profile 2>/dev/null
  echo "[2/4] 切换 power-saver 档 + 创建开机保持服务..."
  powerprofilesctl set power-saver || { echo "❌ 失败，回滚..."; sudo systemctl enable acdc-profile 2>/dev/null; sudo systemctl start acdc-profile; exit 1; }
  # M3 持久化: 重启后 PPD 恢复默认档时, 由本服务自动设回 power-saver
  sudo tee "$M3_SERVICE" >/dev/null <<'EOF'
[Unit]
Description=M3 power-saver profile keep
After=power-profiles-daemon.service

[Service]
Type=oneshot
ExecStart=/usr/bin/powerprofilesctl set power-saver

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable m3-power-saver.service >/dev/null 2>&1
  sleep 1
  echo "[3/4] 验证:"
  show_status
  if [ "$(powerprofilesctl get)" = "power-saver" ]; then
    echo ""
    echo "✅ M3 离电效能模式已生效（已持久化: 重启后自动保持）"
  else
    echo "❌ 切换失败，请检查"
    return 1
  fi
  echo "[4/4] GPU 选择:"
  GPU=$(prime-select query)
  if [ "$GPU" = "nvidia" ]; then
    echo ""
    echo "  M3 推荐【集显】: 空闲可省 ~7.7W（23.7W→16W），续航提升 ~30%"
    echo "  但切换需要重启系统。当前 GPU: $GPU（独显）"
    echo ""
    echo "  1) 保持独显 nvidia（性能优先，无需重启）"
    echo "  2) 切换集显 intel（省电最优，需重启，M3 将保持）"
    echo "  3) 跳过"
    read -rp "  输入数字 [1/2/3]: " G
    case "$G" in
      2) gpu_switch intel ;;
      1|3|*) echo "  ✅ 保持独显。M3 已生效。" ;;
    esac
  else
    echo "  ✅ 已在集显 $GPU 模式（M3 省电最优），无需切换。"
  fi
}

mode_off() {
  echo "=== 退出 M3，恢复自动模式 ==="
  AC=$(cat /sys/class/power_supply/ACAD/online)
  if [ "$AC" = "1" ]; then
    echo "[1/3] 当前插电(AC) → 立即切回 performance (M1)..."
    powerprofilesctl set performance
  else
    echo "[1/3] 当前拔电(DC) → 立即切回 balanced (M2)..."
    powerprofilesctl set balanced
  fi
  echo "[2/3] 恢复 acdc-profile 自动切换 + 移除 M3 持久化服务..."
  sudo systemctl enable acdc-profile 2>/dev/null
  sudo systemctl start acdc-profile || { echo "❌ 失败"; exit 1; }
  sudo systemctl disable m3-power-saver.service 2>/dev/null
  sudo rm -f "$M3_SERVICE"
  sudo systemctl daemon-reload
  sleep 3
  echo "[3/3] 验证:"
  show_status
  echo ""
  echo "✅ 已恢复自动模式（插电=M1 带电极致 / 拔电=M2 离电均衡）"
  GPU=$(prime-select query)
  if [ "$GPU" != "nvidia" ]; then
    echo ""
    echo "GPU 状态: 当前为 $GPU（集显），与带电默认独显不同。"
    echo "是否切回独显 nvidia？（带电默认独显）"
    echo "  1) 切回独显 nvidia（需重启）"
    echo "  2) 保持集显"
    read -rp "  输入数字 [1/2]: " G
    if [ "$G" = "1" ]; then
      gpu_switch nvidia
    else
      echo "  ✅ 保持集显。如需切回: sudo prime-select nvidia && sudo reboot"
    fi
  else
    echo "GPU 状态: 当前为 nvidia（独显，默认）✅"
  fi
}

case "$MODE" in
  on)     mode_on ;;
  off)    mode_off ;;
  status) show_status ;;
  "")
    echo "=== M3 离电效能模式切换 ==="
    echo "当前: PPD=$(powerprofilesctl get) | acdc-profile=$(systemctl is-active acdc-profile) | GPU=$(prime-select query)"
    echo ""
    echo "  1) 进入 M3 离电效能（DC + power-saver，可选切集显）"
    echo "  2) 退出 M3，恢复自动模式（插电=M1 / 拔电=M2）"
    echo "  3) 查看详细状态"
    echo "  0) 退出"
    read -rp "  输入数字: " CHOICE
    case "$CHOICE" in
      1) mode_on ;;
      2) mode_off ;;
      3) show_status ;;
      *) echo "已取消" ;;
    esac
    ;;
  *) echo "用法: ./m3.sh [on|off|status]（无参数显示菜单）"; exit 1 ;;
esac