#!/bin/bash
# =============================================================================
# 00_保存会话与日志.sh — 会话内容 + 系统实时日志 一键备份
# =============================================================================
# 原则(必读):
#   【每次执行下一个新任务前, 必须先运行本脚本】
#   将所有 AI 会话内容 + 实时相关日志(系统/内核/电源/传感器/配置)
#   保存到 性能优化方案/会话备份/<时间戳>/ 独立文件夹,
#   保证重装系统后能快速查验问题、继续研究与优化。
#
# 用法:
#   ./00_保存会话与日志.sh            # 正常备份
#   ./00_保存会话与日志.sh "任务说明"  # 备份并在 MANIFEST 标注任务内容
# 回退/说明: 本脚本只读系统信息并复制文件, 不修改任何系统配置。
# =============================================================================

set -u

# 自动定位 BASE(脚本所在目录), 支持用户名变化
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"  # readlink: 经 sc-backup.sh 别名调用时解析真实位置
BASE="$SCRIPT_DIR"
STAMP=$(date +%Y%m%d_%H%M%S)
DIR="$BASE/$STAMP"
TASK_DESC="${1:-}"

mkdir -p "$DIR/system_logs" "$DIR/session" "$DIR/configs" "$DIR/opencode_data"

echo "=== 会话备份开始: $STAMP ==="
echo "保存位置: $DIR"

# ---------- 1. 系统日志 ----------
echo "[1/8] 系统日志..."
journalctl --no-pager -b > "$DIR/system_logs/journalctl_current_boot.log" 2>/dev/null
journalctl --no-pager -b -1 > "$DIR/system_logs/journalctl_prev_boot.log" 2>/dev/null
journalctl --no-pager -k > "$DIR/system_logs/journalctl_kernel.log" 2>/dev/null
journalctl --no-pager -p err --since "7 days ago" > "$DIR/system_logs/journalctl_errors_7d.log" 2>/dev/null
dmesg > "$DIR/system_logs/dmesg.log" 2>/dev/null || dmesg 2>/dev/null | sudo tee "$DIR/system_logs/dmesg.log" >/dev/null
dmesg 2>/dev/null | grep -iE "mce|machine check|thermal|throttl" > "$DIR/system_logs/dmesg_mce_thermal.log" 2>/dev/null || true
last -x reboot shutdown 2>/dev/null > "$DIR/system_logs/reboot_history.log"

# ---------- 2. 电源/CPU 实时状态(snapshot) ----------
echo "[2/8] CPU/电源状态快照..."
RAPL=/sys/class/powercap/intel-rapl:0
{
    echo "=== 采集时间 ==="
    date
    echo; echo "=== 内核/系统 ==="
    uname -a
    echo; echo "=== 运行时长/负载 ==="
    uptime
    echo; echo "=== PL1/PL2 ==="
    echo "PL1: $(cat $RAPL/constraint_0_power_limit_uw 2>/dev/null)"
    echo "PL2: $(cat $RAPL/constraint_1_power_limit_uw 2>/dev/null)"
    echo "PL1 max: $(cat $RAPL/constraint_0_max_power_uw 2>/dev/null)"
    echo "PL2 max: $(cat $RAPL/constraint_1_max_power_uw 2>/dev/null)"
    echo "PL1 time_window: $(cat $RAPL/constraint_0_time_window_us 2>/dev/null)"
    echo "PL2 time_window: $(cat $RAPL/constraint_1_time_window_us 2>/dev/null)"
    echo; echo "=== Governor / EPP (cpu0) ==="
    echo "governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)"
    echo "EPP: $(cat /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference 2>/dev/null)"
    echo "cur_freq: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null)"
    echo "max_freq: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq 2>/dev/null)"
    echo "no_turbo: $(cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null)"
    echo "turbo_pct: $(cat /sys/devices/system/cpu/intel_pstate/turbo_pct 2>/dev/null)"
    echo; echo "=== C-State 状态 (cpu0) ==="
    for st in /sys/devices/system/cpu/cpu0/cpuidle/state*; do
        [ -d "$st" ] || continue
        echo "$(cat $st/name 2>/dev/null): disable=$(cat $st/disable 2>/dev/null)"
    done
    echo; echo "=== 供电状态 ==="
    for d in /sys/class/power_supply/*; do
        [ -d "$d" ] || continue
        echo "$d: type=$(cat $d/type 2>/dev/null) online=$(cat $d/online 2>/dev/null) capacity=$(cat $d/capacity 2>/dev/null)% status=$(cat $d/status 2>/dev/null) energy_full=$(cat $d/energy_full 2>/dev/null) energy_full_design=$(cat $d/energy_full_design 2>/dev/null)"
    done
    echo; echo "=== 温度传感器 ==="
    sensors
    echo; echo "=== 热区 ==="
    for z in /sys/class/thermal/thermal_zone*; do
        [ -d "$z" ] || continue
        echo "$(basename $z): type=$(cat $z/type 2>/dev/null) temp=$(cat $z/temp 2>/dev/null)"
    done
} > "$DIR/system_logs/cpu_power_snapshot.txt"

# ---------- 3. 关键服务状态 ----------
echo "[3/8] 关键服务状态..."
{
    # 2026-08-29 修正: 服务名 intel-undervolt → undervolt(本机实际), 并补真机在用的服务
    for svc in cpu-power-limit turbo-enable undervolt undervolt-resume acdc-profile \
               thermal-guard console-rapl-perm rasdaemon power-profiles-daemon thermald; do
        echo "===== $svc ====="
        systemctl status "$svc" --no-pager 2>/dev/null | head -15
        echo
    done
    echo "===== turbo-guard 日志 ====="
    tail -30 /var/log/turbo-guard.log 2>/dev/null || echo "(无日志)"
} > "$DIR/system_logs/services_status.txt"

# ---------- 4. 降压/MSR 当前值(需 root, 失败则记录) ----------
echo "[4/8] 降压/MSR 状态..."
{
    # 2026-08-29 修正: 本机用 Python 版 undervolt(非 C 版 intel-undervolt),
    # 原逻辑恒输出"未安装", 导致每次备份都记录假失败。现按优先级探测两者。
    echo "=== undervolt read (降压实测) ==="
    if command -v undervolt >/dev/null 2>&1; then
        undervolt --read 2>&1 || sudo -n undervolt --read 2>&1 || \
            { echo "(需 root 且无免密; 改用服务单元配置值:)"; \
              grep -h 'ExecStart' /etc/systemd/system/undervolt.service 2>/dev/null; }
    elif command -v intel-undervolt >/dev/null 2>&1; then
        echo "(C 版 intel-undervolt)"
        intel-undervolt read 2>&1 || sudo intel-undervolt read 2>&1 || echo "(需 root, 跳过)"
    else
        echo "未安装"
    fi
    echo; echo "=== MSR 0x1A0 (bit38=Turbo) ==="
    if command -v rdmsr >/dev/null 2>&1; then
        rdmsr -f 38:38 0x1a0 2>&1 || sudo rdmsr -f 38:38 0x1a0 2>&1 || echo "(需 root, 跳过)"
        rdmsr 0x1a0 2>&1 || sudo rdmsr 0x1a0 2>&1 || true
    else
        echo "msr-tools 未安装"
    fi
    echo; echo "=== MCE 检查 ==="
    grep -ciE "mce|machine check" "$DIR/system_logs/dmesg_mce_thermal.log" 2>/dev/null || echo 0
} > "$DIR/system_logs/undervolt_msr_status.txt"

# ---------- 5. 配置文件(只读复制) ----------
echo "[5/8] 关键配置文件..."
# 2026-08-29: 删去不存在的 /etc/intel-undervolt.conf(本机用 Python 版, 配置在服务命令行)
for f in /etc/default/grub /etc/thermald/thermal-conf.xml; do
    [ -f "$f" ] && cp "$f" "$DIR/configs/$(echo $f | tr '/' '_')" 2>/dev/null
done
# 2026-08-29 修正: intel-undervolt → undervolt(+undervolt-resume)
for svc in cpu-power-limit turbo-enable undervolt undervolt-resume acdc-profile thermal-guard; do
    [ -f "/etc/systemd/system/$svc.service" ] && cp "/etc/systemd/system/$svc.service" "$DIR/configs/"
done
[ -f /usr/local/bin/turbo-guard.sh ] && cp /usr/local/bin/turbo-guard.sh "$DIR/configs/turbo-guard.sh" 2>/dev/null

# ---------- 6. opencode 会话数据 ----------
echo "[6/8] opencode 会话数据..."
if [ -d ~/.local/share/opencode ]; then
    # 硬链接去重：同一天多次备份共享同一数据库块（80MB→0 增量）
    ln ~/.local/share/opencode/opencode.db "$DIR/opencode_data/" 2>/dev/null         || cp ~/.local/share/opencode/opencode.db "$DIR/opencode_data/" 2>/dev/null && echo "  已复制 opencode.db（硬链接优先）"
    cp ~/.local/share/opencode/opencode.db-wal "$DIR/opencode_data/" 2>/dev/null || true
    cp ~/.local/share/opencode/opencode.db-shm "$DIR/opencode_data/" 2>/dev/null || true
    [ -d ~/.local/share/opencode/log ] && cp -r ~/.local/share/opencode/log "$DIR/opencode_data/" 2>/dev/null
    [ -d ~/.local/share/opencode/repos ] && cp -r ~/.local/share/opencode/repos "$DIR/opencode_data/" 2>/dev/null
    # 导出为可读 markdown(新对话/人工可直接阅读)
    python3 - "$DIR/session/opencode_会话导出.md" << 'PYEOF' 2>/dev/null && echo "  已导出会话为可读文本"
import sqlite3, json, sys, time
out = sys.argv[1]
db = sqlite3.connect('/home/' + __import__('os').getenv('USER') + '/.local/share/opencode/opencode.db')
cur = db.cursor()
rows = []
for sid, title, created in cur.execute("SELECT id,title,time_created FROM session ORDER BY time_created DESC LIMIT 5"):
    rows.append((sid, title, created))
lines = ["# opencode 会话导出", "", "> 由 00_保存会话与日志.sh 自动生成, 供重装后查验", ""]
for sid, title, created in rows:
    lines.append(f"## 会话: {title}  ({time.strftime('%Y-%m-%d %H:%M', time.localtime(created/1000))})")
    lines.append("")
    cur.execute("SELECT m.time_created, m.data, p.data FROM message m JOIN part p ON p.message_id=m.id WHERE m.session_id=? ORDER BY m.time_created, p.time_created", (sid,))
    for mt, md, pd in cur.fetchall():
        try: pj = json.loads(pd)
        except: continue
        t = pj.get('type')
        if t == 'text' and pj.get('text'):
            lines.append(f"### {time.strftime('%H:%M:%S', time.localtime(mt/1000))}")
            lines.append(pj['text'].strip())
            lines.append("")
        elif t == 'tool':
            try:
                tid = pj.get('tool')
                st = pj.get('state')
                inp = pj.get('input') or {}
                if isinstance(st, dict) and st.get('status') == 'completed':
                    desc = str(tid)
                    if isinstance(inp, dict):
                        cmd = inp.get('command') or inp.get('filePath') or inp.get('pattern') or ''
                        desc = f"{tid}: {cmd}" if cmd else tid
                    lines.append(f"- [tool] {desc}")
            except: pass
    lines.append("")
open(out, 'w', encoding='utf-8').write("\n".join(lines))
PYEOF
fi

# ---------- 6.5 生成当前状态单一事实源 current_state.md ----------
echo "[6.5/8] 生成 current_state.md(单一事实源)..."
{
    echo "# 当前系统状态快照 — $STAMP"
    echo
    echo "> 生成: $(date '+%F %T') | 用途: 重装后快速判断当时状态"
    echo
    echo "## 电源/CPU"
    echo "- PL1: $(cat /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw 2>/dev/null) ($(($(cat /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw 2>/dev/null)/1000000))W)"
    echo "- PL2: $(cat /sys/class/powercap/intel-rapl:0/constraint_1_power_limit_uw 2>/dev/null) ($(($(cat /sys/class/powercap/intel-rapl:0/constraint_1_power_limit_uw 2>/dev/null)/1000000))W)"
    echo "- governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)"
    echo "- EPP: $(cat /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference 2>/dev/null)"
    echo "- no_turbo: $(cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null) (0=开)"
    echo "- Turbo bit38: $(rdmsr -f 38:38 0x1a0 2>/dev/null || sudo rdmsr -f 38:38 0x1a0 2>/dev/null || echo '需root')"
    echo
    echo "## 服务"
    # 2026-08-29 修正: intel-undervolt → undervolt(+undervolt-resume), 补真机在用的服务
    for svc in cpu-power-limit turbo-enable undervolt undervolt-resume acdc-profile \
               thermal-guard console-rapl-perm rasdaemon power-profiles-daemon thermald; do
        ST=$(systemctl is-active "$svc" 2>/dev/null)
        if [ -z "$ST" ] || [ "$ST" = "unknown" ]; then
            echo "- $svc: 不存在(unit 未安装)"
        else
            echo "- $svc: $ST"
        fi
    done
    echo
    echo "## 降压"
    # 2026-08-29 修正: 本机用 Python 版 undervolt; 原逻辑恒输出"未安装"
    if command -v undervolt >/dev/null 2>&1; then
        UV=$(undervolt --read 2>/dev/null || sudo -n undervolt --read 2>/dev/null)
        if [ -n "$UV" ]; then
            echo "$UV" | grep -E "core|gpu|cache|temperature target|powerlimit|turbo" | sed 's/^/- /'
        else
            echo "- 需 root（免密不可用），服务单元配置值："
            grep -h 'ExecStart' /etc/systemd/system/undervolt.service 2>/dev/null | sed 's/^/  /'
        fi
    elif command -v intel-undervolt >/dev/null 2>&1; then
        echo "- (C 版) $(intel-undervolt read 2>/dev/null | head -1 || sudo intel-undervolt read 2>/dev/null | head -1 || echo '需root')"
    else
        echo "- undervolt 未安装"
    fi
    echo
    echo "## 温度/负载"
    echo "- 封装温度: $(sensors 2>/dev/null | awk '/^Package/{print $4}' | tr -d '+°C' | head -1)°C"
    echo "- 负载: $(uptime)"
    echo
    echo "## 判断(对照定稿)"
    echo "⚠ 2026-08-29 审计: 下行定稿值已过时(为换脂前 15W/-105mV 时代), 勿据此判断"
    echo "  历史定稿: PL1=PL2=15W / Turbo ON(bit38=0) / 降压 -105mV / 三服务 active"
    echo "  当前应为(2026-08-29 真机实测): PL1=PL2=25W / C-state=max_cstate=4 / 降压 -50mV"
    echo "  服务真名: undervolt(+undervolt-resume) / turbo-enable / cpu-power-limit / acdc-profile / thermal-guard"
    echo "  定案方法: sudo bash \"$SCRIPT_DIR/backend/collect_ground_truth.sh\""
    echo "  若与本快照不符 → 需按 00_交接手册_重装后启动.md(注意其第三节已加过时横幅) 恢复"
} > "$DIR/current_state.md"

# ---------- 7. 项目数据同步(sweep_data/CSV 等) ----------
echo "[7/8] 项目数据同步..."
# 自动定位「性能优化方案」目录: 其名称带时间戳且按项目规则会随内容更新而改名,
# 故用通配符匹配而非硬编码路径(原 20260817 硬编码已在 20260825 重组后失效, 导致本步静默空转)
LINUX_DIR="$(dirname "$SCRIPT_DIR")"
PROJ_DIR="$(find "$LINUX_DIR" -maxdepth 1 -type d -name '性能优化方案*' 2>/dev/null | head -1)"
if [ -z "$PROJ_DIR" ] || [ ! -d "$PROJ_DIR" ]; then
    echo "  ⚠ 未找到 性能优化方案* 目录(搜索于 $LINUX_DIR), 跳过项目数据同步" >&2
else
    echo "  源目录: $PROJ_DIR"
    if command -v rsync >/dev/null 2>&1; then
        rsync -a --exclude='会话备份' "$PROJ_DIR/" "$DIR/project_snapshot/" 2>/dev/null
    else
        cp -r "$PROJ_DIR"/优化脚本 "$DIR/project_snapshot/" 2>/dev/null
        cp -r "$PROJ_DIR"/sweep_data "$DIR/project_snapshot/" 2>/dev/null
        cp "$PROJ_DIR"/*.md "$DIR/project_snapshot/" 2>/dev/null
        cp "$PROJ_DIR"/*.csv "$DIR/project_snapshot/" 2>/dev/null
    fi
    echo "  已同步: $(find "$DIR/project_snapshot" -type f 2>/dev/null | wc -l | tr -d ' ') 个文件"
fi

# ---------- 8. MANIFEST ----------
echo "[8/8] 生成 MANIFEST..."
{
    echo "# 会话备份清单 — $STAMP"
    echo
    echo "- 备份时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "- 任务说明: ${TASK_DESC:-未填写}"
    echo "- 系统: $(uname -sr) / $(hostnamectl --static 2>/dev/null || hostname)"
    echo "- 目录结构:"
    echo "  - system_logs/   系统日志(journalctl/dmesg/重启记录/电源快照/服务状态/降压MSR状态)"
    echo "  - session/       会话内容(opencode_会话导出.md 可读文本 + AI 补充纪要)"
    echo "  - configs/       关键配置(GRUB/降压conf/服务文件/turbo-guard脚本)"
    echo "  - opencode_data/ opencode 会话数据库与日志"
    echo "  - project_snapshot/ 性能优化方案 当时全量快照"
    echo "  - current_state.md  当前状态单一事实源(重装后最先看这个)"
    echo
    echo "## 用法:"
    echo "  重装/换机后: 先看 current_state.md → system_logs/cpu_power_snapshot.txt"
    echo "  → services_status.txt → session/。会话细节看 session/opencode_会话导出.md。"
    echo
    echo "## 原则提醒:"
    echo "  每次执行下一个新任务前, 必须先运行本脚本再做任何修改。"
    echo "  重装后续接: 读 性能优化方案/00_交接手册_重装后启动.md"
} > "$DIR/MANIFEST.md"

sync
echo
echo "=== 备份完成 ==="
echo "位置: $DIR"
echo "大小: $(du -sh "$DIR" 2>/dev/null | cut -f1)"

# 铁律（2026-08-22）: 备份后同步到 WS1 带日期目录
if [ -x "$DIR/../sync_to_ws1.sh" ]; then
    bash "$DIR/../sync_to_ws1.sh"
fi
