#!/bin/bash
# =============================================================================
# collect_ground_truth.sh — 本机 Linux 调优栈「真值」采集
# =============================================================================
# 为什么需要它:
#   项目内多份"权威文档"对同一参数给出互相矛盾的值, 且都以断言式语气书写:
#     · 降压: 根 README(0825) 说 -100mV, 09B(0825) 说 -50mV, 服务快照(0821) 是 -100mV
#     · C-state: 交接手册(0818) 停在"撤销实验进行中", 实际 0821 已定为 6
#     · 硬件信息.csv 仍写 kernel 6.14 / PL1=15W / 建议装 TLP, 全部已过时
#   静态审计无法定案 —— 唯一办法是回真机实测。本脚本把这件事一键化。
#
# 用法:
#   bash backend/collect_ground_truth.sh                 # 输出到屏幕
#   bash backend/collect_ground_truth.sh > 真值报告.md    # 存档
#   sudo bash backend/collect_ground_truth.sh            # 含需 root 项(MSR/降压回读), 推荐
#
# 采集后请把输出贴回对话, 用于重写 00_交接手册 定稿表与根 README。
# 全程只读, 不修改任何系统状态。
# =============================================================================

echo "# 本机 Linux 调优栈真值报告"
echo ""
echo "> 采集时间: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "> 主机名: $(hostname 2>/dev/null)"
echo "> 执行用户: $(whoami) $([ "$(id -u)" = "0" ] && echo '(root — 完整采集)' || echo '(非 root — MSR/降压回读会跳过)')"
echo ""

sec() { echo ""; echo "## $1"; echo ""; }
kv()  { printf '| %-28s | %s |\n' "$1" "${2:-—}"; }
# 安全读取: 文件不存在或不可读时输出 —
rd()  { [ -r "$1" ] && cat "$1" 2>/dev/null | tr -d '\n' || echo "—"; }

# ---------------------------------------------------------------- 1. 环境
sec "1. 环境基线"
echo "| 项 | 值 |"
echo "|---|---|"
kv "内核"        "$(uname -r)"
kv "发行版"      "$(. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME")"
kv "GRUB 命令行" "$(rd /proc/cmdline)"
kv "微码"        "$(grep -m1 'microcode' /proc/cpuinfo 2>/dev/null | cut -d: -f2 | tr -d ' ' || echo —)"
kv "CPU"         "$(grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2 | sed 's/^ *//')"
kv "内存"        "$(free -h 2>/dev/null | awk '/^Mem:/{print $2}')"

# ---------------------------------------------------------------- 2. 功耗墙
sec "2. 功耗墙 PL1/PL2（RAPL 实测回读）"
RAPL=/sys/class/powercap/intel-rapl:0
echo "| 项 | 实测值 |"
echo "|---|---|"
if [ -d "$RAPL" ]; then
    kv "PL1 (constraint_0)" "$(rd $RAPL/constraint_0_power_limit_uw) µW = $(( $(rd $RAPL/constraint_0_power_limit_uw) / 1000000 )) W"
    kv "PL2 (constraint_1)" "$(rd $RAPL/constraint_1_power_limit_uw) µW = $(( $(rd $RAPL/constraint_1_power_limit_uw) / 1000000 )) W"
else
    echo "❌ 无 intel-rapl 接口（$RAPL 不存在）"
fi

# ---------------------------------------------------------------- 3. 降压真值 ★核心争议
sec "3. 降压真值 ★（文档矛盾点：README 说 -100mV / 09B 说 -50mV）"
echo "| 来源 | 值 |"
echo "|---|---|"
if [ -f /etc/systemd/system/intel-undervolt.service ]; then
    kv "服务单元配置" "$(grep -m1 'ExecStart' /etc/systemd/system/intel-undervolt.service | sed 's/^ *ExecStart=//')"
else
    kv "服务单元配置" "文件不存在"
fi
if command -v undervolt >/dev/null 2>&1; then
    echo ""
    echo "**undervolt --read 实测输出（权威）:**"
    echo '```'
    undervolt --read 2>&1 | sed 's/^/  /'
    echo '```'
else
    kv "undervolt" "未安装 —— 若服务显示 active 则实际未生效，这是重要发现"
fi

# ---------------------------------------------------------------- 4. C-state
sec "4. C-state ★（文档矛盾点：手册停在“撤销实验进行中”）"
echo "| 项 | 值 |"
echo "|---|---|"
kv "intel_idle.max_cstate" "$(rd /sys/module/intel_idle/parameters/max_cstate)"
echo ""
echo "**实际启用的 cpuidle 状态 (cpu0):**"
for st in /sys/devices/system/cpu/cpu0/cpuidle/state*; do
    [ -d "$st" ] && printf '  - %-6s disable=%s\n' "$(rd $st/name)" "$(rd $st/disable)"
done

# ---------------------------------------------------------------- 5. Turbo
sec "5. Turbo 双开关"
echo "| 项 | 值 |"
echo "|---|---|"
kv "intel_pstate/no_turbo" "$(rd /sys/devices/system/cpu/intel_pstate/no_turbo) (0=Turbo 开)"
kv "cpufreq boost"         "$(rd /sys/devices/system/cpu/cpufreq/boost)"
if [ "$(id -u)" = "0" ] && command -v rdmsr >/dev/null 2>&1; then
    kv "MSR 0x1A0 (bit38=Turbo禁用)" "$(rdmsr 0x1a0 2>/dev/null || echo '读取失败')"
else
    kv "MSR 0x1A0" "跳过（需 root + msr-tools）"
fi

# ---------------------------------------------------------------- 6. 服务
sec "6. 调优服务状态"
echo '```'
for s in cpu-power-limit turbo-enable intel-undervolt acdc-profile \
         m3-power-saver thermal-guard console-rapl-perm rasdaemon \
         battery-care.timer power-profiles-daemon thermald; do
    printf '%-28s %s\n' "$s" "$(systemctl is-active "$s" 2>/dev/null) / $(systemctl is-enabled "$s" 2>/dev/null)"
done
echo '```'

# ---------------------------------------------------------------- 7. GPU
sec "7. GPU 模式"
echo "| 项 | 值 |"
echo "|---|---|"
kv "prime-select 当前" "$(prime-select query 2>/dev/null || echo '命令不可用')"
kv "nvidia 模块已加载" "$(lsmod 2>/dev/null | grep -c '^nvidia')"
kv "MX150 功耗" "$(nvidia-smi --query-gpu=power.draw,power.limit --format=csv,noheader 2>/dev/null || echo '未激活/无权限')"

# ---------------------------------------------------------------- 8. 后端能力 ★关闭审计盲区
sec "8. thermal_ctl 部署副本实际能力 ★（关闭“源码副本 vs 部署副本”审计盲区）"
CTL=/usr/local/bin/thermal_ctl.sh
if [ -f "$CTL" ]; then
    echo "路径: \`$CTL\` | 字节数: $(wc -c < "$CTL" | tr -d ' ')"
    echo ""
    echo "**实际支持的分支:**"
    grep -oE '^  [a-z_0-9]+\)' "$CTL" | tr -d ' )' | sed 's/^/  - /'
    echo ""
    DIR="$(cd "$(dirname "$0")" && pwd)"
    if [ -f "$DIR/check_ctl_consistency.sh" ]; then
        echo "**与 controller.py 的一致性自检:**"
        echo '```'
        bash "$DIR/check_ctl_consistency.sh" 2>&1 | sed 's/^/  /'
        echo '```'
    fi
else
    echo "❌ 部署副本不存在 —— UI 所有散热/功耗控件均会失败，需先运行 install.sh"
fi

# ---------------------------------------------------------------- 9. 电池
sec "9. 电池"
echo "| 项 | 值 |"
echo "|---|---|"
for b in /sys/class/power_supply/BAT*; do
    [ -d "$b" ] || continue
    kv "$(basename $b) 容量"     "$(rd $b/capacity)%"
    kv "$(basename $b) 状态"     "$(rd $b/status)"
    kv "$(basename $b) 满充"     "$(rd $b/energy_full) µWh"
    kv "$(basename $b) 设计满充" "$(rd $b/energy_full_design) µWh"
    ef=$(rd $b/energy_full); ed=$(rd $b/energy_full_design)
    if [ "$ef" != "—" ] && [ "$ed" != "—" ] && [ "$ed" -gt 0 ] 2>/dev/null; then
        kv "$(basename $b) 健康度" "$(awk "BEGIN{printf \"%.2f%%\", $ef*100/$ed}")（放电窗口采样更可信）"
    fi
done

# ---------------------------------------------------------------- 10. 死机证据
sec "10. 近期死机证据"
echo "| 项 | 值 |"
echo "|---|---|"
kv "本次启动时间" "$(uptime -s 2>/dev/null)"
kv "启动次数(本月)" "$(journalctl --list-boots 2>/dev/null | wc -l | tr -d ' ')"
kv "MCE 计数" "$(journalctl -b -k 2>/dev/null | grep -ci 'mce\|machine check')"
kv "上一次启动异常" "$(journalctl -b -1 -k --no-pager 2>/dev/null | grep -ci 'panic\|mce\|timeout' || echo 0)"

echo ""
echo "---"
echo ""
echo "## 请用以上真值核对这几处文档"
echo ""
echo "| 文档 | 矛盾点 | 处置 |"
echo "|---|---|---|"
echo "| \`00_交接手册_重装后启动.md\` 第三节定稿表 | 降压/C-state 停更 | 按上方第 3、4 节实测值重写 |"
echo "| 根 \`README.md\` 第 45-49 行 | 说 -100mV | 与 \`09B\` 的 -50mV 冲突，以实测为准 |"
echo "| \`09B_本机Linux生态_20260825.md\` 1.3 节 | 说 -50mV | 同上 |"
echo "| \`硬件信息.csv\` / \`系统状态.csv\` | kernel 6.14 / PL1=15W / 建议装 TLP | 已过时，加取代横幅或更新 |"
echo "| \`00_重建优化栈.sh\` 第 101 行 | 写死 -105mV | 若实测非 -105 则同步修正 |"
echo ""
echo "*本脚本为只读采集，未修改任何系统状态。*"
