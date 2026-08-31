#!/bin/bash
# =============================================================================
# acdc_uv_test.sh — AC/DC 切换下的降压保持性验证
# =============================================================================
# 背景（2026-08-30）：-80mV 扫描在 AC 下 5 轮全通过（MCE=0, 波动 1.96%），
#   但存在未验证盲区：
#   · 历史实证「拔电瞬间 EC 会重置 MSR」（0x1A0 Turbo 已由 turbo-enable 守护修复）
#   · 降压走 MSR 0x150，**没有对应的守护进程**
#   · undervolt-resume.service 仅覆盖 suspend/hibernate，**不含 AC/DC 切换**
#   · acdc-profile 是全自动的 → 持久化后每次拔电都会自动套用该降压值
#   → 必须验证：拔电/插电切换时降压是否保持、是否触发 MCE。
#
# 安全约束（严格遵守项目红线）：
#   ❌ 不做 DC 满载（历史 5 死机 4 在 DC，两次明确为 DC 满载）
#   ✅ 仅测：拔电切换（空闲） + 离电轻载（日常场景） + 插电恢复
#
# 用法（需用户配合拔插电源）：
#   PW_FILE=/tmp/.uvpw bash acdc_uv_test.sh 80
# 依赖: undervolt(Python版) / sensors / dmesg
# =============================================================================

set -u

UV_MV="${1:-80}"
SAFE_MV=50
TEMP_TARGET=98
PW_FILE="${PW_FILE:-/tmp/.uvpw}"
LOG="${LOG:-/tmp/acdc_uv_test.log}"
ACF=/sys/class/power_supply/ACAD/online
WAIT_SEC=180          # 等待用户拔/插电的最长时间

# ---------- 工具函数 ----------
srun() { sudo -S -p '' "$@" 2>/dev/null < "$PW_FILE"; }

uv_core() { srun undervolt --read 2>/dev/null | awk '/^core:/{print $2}'; }
mce_cnt() { dmesg 2>/dev/null | grep -ciE "mce|machine check"; }
pkg_temp() { sensors 2>/dev/null | awk '/^Package/{print $4}' | tr -d '+°C' | head -1; }
ac_state() { [ "$(cat "$ACF" 2>/dev/null)" = "1" ] && echo AC || echo DC; }
batt() { cat /sys/class/power_supply/BAT1/capacity 2>/dev/null; }
now() { date '+%H:%M:%S'; }

# 采样一行: 记录 时间/供电/降压/MCE/温度/电池
SNAP_LINES=""
snap() {
    local tag="$1"
    local line
    line="  [$(now)] ${tag}: 供电=$(ac_state) 降压=$(uv_core)mV MCE=$(mce_cnt) 温度=$(pkg_temp)°C 电池=$(batt)%"
    echo "$line" | tee -a "$LOG"
    SNAP_LINES="${SNAP_LINES}${line}"$'\n'
}

# ★ 安全网: 任何中断都恢复安全值
cleanup() {
    echo "" | tee -a "$LOG"
    echo ">>> 收尾: 恢复安全值 -${SAFE_MV}mV <<<" | tee -a "$LOG"
    srun undervolt --core "-$SAFE_MV" --cache "-$SAFE_MV" --gpu "-$SAFE_MV" --temp "$TEMP_TARGET"
    sleep 1
    echo "    恢复后实测: core=$(uv_core)mV" | tee -a "$LOG"
    rm -f "$PW_FILE" 2>/dev/null
    exit 0
}
trap cleanup INT TERM EXIT

# ---------- 0. 前置检查 ----------
[ -f "$PW_FILE" ] || { echo "❌ 缺少密码文件 $PW_FILE"; exit 1; }
command -v undervolt >/dev/null || { echo "❌ 缺少 undervolt"; exit 1; }
[ "$(ac_state)" = "AC" ] || { echo "❌ 必须在 AC 下启动本测试（DC 启动不符合流程）"; exit 1; }
[ "$(batt)" -ge 40 ] 2>/dev/null || echo "⚠️ 电池偏低，注意接回电源"

: > "$LOG"
echo "=== AC/DC 切换降压保持性验证 (目标 -${UV_MV}mV) ===" | tee -a "$LOG"
echo "安全值 -${SAFE_MV}mV | 红线: 不做 DC 满载 | 开始 $(now)" | tee -a "$LOG"
echo "" | tee -a "$LOG"

# ---------- 1. 基线（AC, 安全值）----------
echo "--- [1/6] 基线采集（AC, -${SAFE_MV}mV 安全值）---" | tee -a "$LOG"
BASE_MCE=$(mce_cnt)
snap "基线"

# ---------- 2. 应用目标值 ----------
echo "" | tee -a "$LOG"
echo "--- [2/6] 应用 -${UV_MV}mV ---" | tee -a "$LOG"
if ! srun undervolt --core "-$UV_MV" --cache "-$UV_MV" --gpu "-$UV_MV" --temp "$TEMP_TARGET"; then
    echo "❌ apply 失败，未改动系统" | tee -a "$LOG"; exit 1
fi
sleep 1
snap "应用后"
APPLIED=$(uv_core)
echo "  → 实测 ${APPLIED}mV" | tee -a "$LOG"

# ---------- 3. 等待拔电 ----------
echo "" | tee -a "$LOG"
echo "--- [3/6] 请【拔掉电源】，等待中（最多 ${WAIT_SEC}s）---" | tee -a "$LOG"
T0=$(date +%s)
while [ "$(ac_state)" = "AC" ]; do
    [ $(( $(date +%s) - T0 )) -gt "$WAIT_SEC" ] && { echo "⏱ 超时未拔电，退出" | tee -a "$LOG"; exit 0; }
    sleep 1
done
echo "  ✓ 检测到拔电 ($(now))" | tee -a "$LOG"
snap "DC+0s(切换瞬间)"
sleep 10;  snap "DC+10s"
sleep 20;  snap "DC+30s"
sleep 15;  snap "DC+45s"

# ---------- 4. 离电轻载（日常场景，非满载）----------
echo "" | tee -a "$LOG"
echo "--- [4/6] 离电轻载测试（单线程 15s，模拟日常使用，非满载）---" | tee -a "$LOG"
# 单线程轻负载: 不做 8 线程满载（红线）。用 dc_idle_sample 思路的轻量计算。
( for i in 1 2; do timeout 6 awk 'BEGIN{s=0; for(i=0;i<3000000;i++) s+=i%7; print s}' >/dev/null 2>&1; done ) &
LPID=$!
sleep 3;  snap "轻载中+3s"
sleep 8;  snap "轻载中+11s"
wait $LPID 2>/dev/null
snap "轻载结束"

# ---------- 5. 等待插电 ----------
echo "" | tee -a "$LOG"
echo "--- [5/6] 请【插回电源】，等待中（最多 ${WAIT_SEC}s）---" | tee -a "$LOG"
T0=$(date +%s)
while [ "$(ac_state)" = "DC" ]; do
    [ $(( $(date +%s) - T0 )) -gt "$WAIT_SEC" ] && { echo "⏱ 超时未插电，退出（将恢复安全值）" | tee -a "$LOG"; exit 0; }
    sleep 1
done
echo "  ✓ 检测到插电 ($(now))" | tee -a "$LOG"
snap "AC+0s(回复瞬间)"
sleep 10;  snap "AC+10s"
sleep 20;  snap "AC+30s"

# ---------- 6. 汇总 ----------
echo "" | tee -a "$LOG"
echo "--- [6/6] 汇总 ---" | tee -a "$LOG"
END_MCE=$(mce_cnt)
echo "  MCE: 基线 ${BASE_MCE} → 结束 ${END_MCE} (增量 $((END_MCE-BASE_MCE)))" | tee -a "$LOG"
echo "  全程系统存活: $(uptime | sed 's/^.*up //; s/,.*user.*//')" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "=== 采样汇总 ===" | tee -a "$LOG"
echo "$SNAP_LINES" | tee -a "$LOG"
echo "=== 测试结束 $(now)（随后自动恢复安全值）===" | tee -a "$LOG"
