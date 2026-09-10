#!/bin/bash
# =============================================================================
# 启动控制台.sh — 系统控制台一键启动（带环境预检）
# =============================================================================
# 相比原 start.sh 增加了预检：依赖、显示环境、单实例、sudoers 白名单。
# 预检失败时给出【可操作的修复指引】，而不是让用户面对裸 Python 回溯。
#
# 用法:
#   双击桌面「系统控制台.desktop」     ← 推荐
#   终端: bash 启动控制台.sh
#   终端: bash 启动控制台.sh --check    ← 只预检不启动
#   终端: bash 启动控制台.sh --force    ← 跳过单实例检查（已有实例时再开一个）
# =============================================================================
set -u

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1

MODE="${1:-}"

# ---------- 预检 ----------
ERRS=""
WARNS=""

# 1. Python3
if ! command -v python3 >/dev/null 2>&1; then
    ERRS="${ERRS}  ❌ 未找到 python3\n     修复: sudo apt install python3\n"
fi

# 2. GTK3 / PyGObject
if ! python3 -c "import gi; gi.require_version('Gtk','3.0')" >/dev/null 2>&1; then
    ERRS="${ERRS}  ❌ 缺少 GTK3 绑定 (PyGObject)\n     修复: sudo apt install python3-gi gir1.2-gtk-3.0\n"
fi

# 3. DISPLAY（GUI 必需）
if [ -z "${DISPLAY:-}" ]; then
    # 尝试 Wayland 会话
    if [ -n "${WAYLAND_DISPLAY:-}" ]; then
        WARNS="${WARNS}  ⚠️ 检测到 Wayland 会话；托盘图标可能需要 appindicator 扩展\n"
    else
        ERRS="${ERRS}  ❌ 无图形显示环境 (DISPLAY 未设置)\n     请在桌面会话中运行，或先执行: export DISPLAY=:0\n"
    fi
fi

# 4. 主程序存在
if [ ! -f "$DIR/console.py" ]; then
    ERRS="${ERRS}  ❌ 主程序缺失: $DIR/console.py\n"
fi

# 5. sudoers 白名单（控制功能；缺失则只能监控）
if [ ! -f /etc/sudoers.d/system-console ]; then
    WARNS="${WARNS}  ⚠️ sudo 免密白名单未配置 → 控制功能不可用（监控仍可用）\n     修复: sudo bash \"$DIR/install.sh\"\n"
fi

# 6. 单实例检查（锁文件 + /proc/cmdline 校验）
# 2026-08-31 修正: 原用 pgrep -fc 进程名匹配，两个问题:
#   ① pgrep -fc 输出多行 → "[: 需要整数表达式" 报错
#   ② 匹配模式过宽，易误判
# 改为: 锁文件存 PID + 读 /proc/<PID>/cmdline 校验该进程确实是本控制台；
# 陈旧锁（进程已退出）自动忽略并被覆盖。
LOCK_DIR="$DIR/data"
LOCK_FILE="$LOCK_DIR/.console.pid"

_console_running_pid() {
    [ -f "$LOCK_FILE" ] || return 0
    local pid
    pid=$(tr -dc '0-9' < "$LOCK_FILE" 2>/dev/null)
    [ -n "$pid" ] || return 0
    [ -r "/proc/$pid/cmdline" ] || return 0
    if tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q "console.py"; then
        echo "$pid"
    fi
}

if [ "$MODE" != "--force" ]; then
    OLD_PID=$(_console_running_pid)
    if [ -n "$OLD_PID" ]; then
        echo "=== 系统控制台已在运行（PID: $OLD_PID）==="
        echo "  若窗口被隐藏，请点击系统托盘图标（电池图标）选择「显示 / 隐藏」。"
        echo "  需要再开一个实例: bash 启动控制台.sh --force"
        echo "  结束现有实例:     kill $OLD_PID"
        exit 0
    fi
fi

# ---------- 输出结果 ----------
if [ -n "$WARNS" ]; then
    echo "=== 提示 ==="
    printf '%b' "$WARNS"
    echo
fi

if [ -n "$ERRS" ]; then
    echo "=== 无法启动，请先解决以下问题 ==="
    printf '%b' "$ERRS"
    echo
    # 有图形环境时弹窗提示（桌面双击场景下终端不可见）
    if command -v zenity >/dev/null 2>&1 && [ -n "${DISPLAY:-}" ]; then
        zenity --error --title="系统控制台无法启动" \
               --text="$(printf '%b' "$ERRS" | sed 's/\x1b\[[0-9;]*m//g')" 2>/dev/null
    fi
    exit 1
fi

if [ "$MODE" = "--check" ]; then
    echo "✅ 预检通过（未启动）"
    echo "   程序目录: $DIR"
    echo "   DISPLAY:  ${DISPLAY:-未设置}"
    exit 0
fi

# ---------- 启动 ----------
# 前台 exec: 进程被 python3 替换，PID 不变 → 锁文件记录的 PID 即控制台进程，
# 单实例判定精确。桌面 .desktop 以 Terminal=false 启动，无终端依赖。
# 日志: data/console.log（便于排查启动问题；同时输出到终端）
mkdir -p "$LOCK_DIR" 2>/dev/null

# --force 时清掉旧锁（允许再开一个实例）
[ "$MODE" = "--force" ] && rm -f "$LOCK_FILE" 2>/dev/null

# 记录本进程 PID（exec 后即 python 的 PID）
echo $$ > "$LOCK_FILE" 2>/dev/null

# 2026-08-31 修正: 原写 `exec python3 ... | tee -a log`
# → 管道使 bash 创建子 shell，exec 替换的是【子 shell】而非本进程，
#   导致 $$ 写入锁文件的 PID 与实际 python 进程不符，单实例判断失效。
# 改为: tee 在后台跑，前台 exec python（无管道）→ PID 保持不变，锁文件精确。
echo "✅ 正在启动系统控制台...（PID: $$）"
echo "   日志: $DIR/data/console.log"
echo "   提示: 关闭本终端即结束程序；或按 Ctrl+C"

# 后台 tee 负责落盘（日志另存，不影响前台 PID）
tee -a "$DIR/data/console.log" >/dev/null 2>&1 &
TEE_PID=$!

# 前台 exec：进程被 python3 替换，PID == $$（锁文件记录的 PID）
exec python3 "$DIR/console.py" 2>&1
