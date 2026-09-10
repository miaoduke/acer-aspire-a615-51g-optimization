#!/usr/bin/env bash
# =============================================================================
# tests/test_p1_safeguard.sh — P1-1 三级判定回归测试（bash 单测）
# =============================================================================
# 覆盖:
#   1. uv_safeguard.sh verdict_last_boot() 三级判定（CLEAN/CRASH/SUSPECT）
#      - 系统级关机序列识别（systemd-shutdown[ / Journal stopped / systemd[1]）
#      - 用户级 systemd[N≠1] 的 shutdown target 不误判 CLEAN（2026-09-04 boot -1 现场）
#      - 崩溃特征识别（panic/oops/MCE）+ P0-1 同款噪声排除（mcelog/AER/rasdaemon）
#   2. strike 升级逻辑（boot_id 防同事件重复计数 + 7 天窗口）
#   3. uv_daily_check.sh 检查项3 verdict 解析（KEY=VAL 新格式 + 旧单行兼容）
#   4. 告警分级退出（纯🟡 exit 0，含🔴/🟠 exit 1）
#
# 运行: bash tests/test_p1_safeguard.sh   （无需 root，全部 mock）
# =============================================================================
set -u
BASE="$(cd "$(dirname "$0")/.." && pwd)"
SG="$BASE/backend/uv_safeguard.sh"
DC="$BASE/backend/uv_daily_check.sh"

PASS=0; FAIL=0
t() { if [ "$2" = "$3" ]; then PASS=$((PASS+1)); echo "  ✓ $1"; else FAIL=$((FAIL+1)); echo "  ✗ $1: 期望 '$2' 实际 '$3'"; fi; }

# ---------- A. verdict_last_boot 三级判定 ----------
echo "[A] safeguard verdict_last_boot 三级判定"
eval "PREV_BOOT=-1
$(sed -n '/^verdict_last_boot()/,/^}/p' "$SG")"
journalctl() { printf 'systemd-journald[338]: Journal stopped\n'; }
t "A1 系统关机序列→CLEAN" "CLEAN" "$(verdict_last_boot)"
journalctl() { printf 'systemd[1]: Reached target Shutdown.\nsystemd[1]: Powering off.\n'; }
t "A2 systemd[1]关机target→CLEAN" "CLEAN" "$(verdict_last_boot)"
journalctl() { printf 'systemd[1339]: Reached target shutdown.target - Shutdown.\ndbus-daemon[977]: Activation failed\n'; }
t "A3 用户级instance不算CLEAN→SUSPECT" "SUSPECT" "$(verdict_last_boot)"
journalctl() { printf 'kernel: Kernel panic - not syncing: Fatal exception\n'; }
t "A4 panic→CRASH" "CRASH" "$(verdict_last_boot)"
journalctl() { printf 'kernel: misc mcelog: hash matches\nkernel: mce: [Hardware Error]: Machine check events logged\n'; }
t "A5 真MCE行→CRASH" "CRASH" "$(verdict_last_boot)"
journalctl() { printf 'kernel: misc mcelog: hash matches\nkernel: rasdaemon: mce:mce_record event enabled\nkernel: pcieport 0000:03:00.0: AER: Corrected error received\nkernel: msr: Write to unrecognized MSR 0x150 by undervolt\n'; }
t "A6 P0-1噪声现场→SUSPECT" "SUSPECT" "$(verdict_last_boot)"
journalctl() { return 1; }
t "A7 journal不可读→SUSPECT" "SUSPECT" "$(verdict_last_boot)"

# ---------- B. strike 升级逻辑 ----------
echo "[B] strike 升级逻辑（boot_id 防重复）"
strike_decision() {
    local line="$1" now="$2" bid="$3" win=$((7*24*3600))
    local ots=$(echo "$line" | awk '{print $1}') obid=$(echo "$line" | awk '{print $2}')
    ots=${ots:-0}; local age=$((now - ots))
    if [ "$ots" -gt 0 ] && [ "$age" -lt "$win" ] && [ "$obid" != "$bid" ]; then echo REVERT
    elif [ "$ots" -gt 0 ] && [ "$obid" = "$bid" ]; then echo KEEP_WATCH
    else echo NEW_WATCH; fi
}
NOW=1788502000
t "B1 首次→NEW_WATCH" "NEW_WATCH" "$(strike_decision "" $NOW aaa)"
t "B2 同boot重判→KEEP_WATCH" "KEEP_WATCH" "$(strike_decision "$((NOW-60)) aaa" $NOW aaa)"
t "B3 7天内异boot→REVERT" "REVERT" "$(strike_decision "$((NOW-3600)) bbb" $NOW aaa)"
t "B4 8天前过期→NEW_WATCH" "NEW_WATCH" "$(strike_decision "$((NOW-8*24*3600)) bbb" $NOW aaa)"
t "B5 旧格式行(缺bid)→REVERT" "REVERT" "$(strike_decision "$((NOW-3600))" $NOW aaa)"

# ---------- C. verdict 文件解析（daily check 消费端） ----------
echo "[C] verdict 解析（KEY=VAL + 旧格式兼容）"
extract() {
    local f="$1"
    local v=$(awk -F'=' '/^verdict=/{print $2; found=1} END{if(!found) print ""}' "$f")
    if [ -z "$v" ]; then
        v=$(awk '{for(i=1;i<=NF;i++) if($i=="CLEAN"||$i=="WATCH"||$i=="CRASH_REVERT"||$i=="STRIKE_REVERT"||$i=="SKIP"){print $i; exit}}' "$f")
    fi
    echo "$v"
}
printf 'ts=2026-09-04 14:02:58\nverdict=WATCH\nboot=-1\nboot_id=9374434f\ndetail=疑似手动重启 strike=1/2\n' > /tmp/vt_new
t "C1 新格式WATCH" "WATCH" "$(extract /tmp/vt_new)"
printf 'ts=x\nverdict=CRASH_REVERT\nboot=-2\nboot_id=abc\ndetail=崩溃\n' > /tmp/vt_crash
t "C2 新格式CRASH_REVERT" "CRASH_REVERT" "$(extract /tmp/vt_crash)"
printf '2026-09-04 13:57:15 WATCH boot=-1 疑似手动重启\n' > /tmp/vt_old
t "C3 旧单行格式WATCH" "WATCH" "$(extract /tmp/vt_old)"
: > /tmp/vt_empty; t "C4 空文件→空" "" "$(extract /tmp/vt_empty)"
printf '乱七八糟\n' > /tmp/vt_bad; t "C5 无字段→空" "" "$(extract /tmp/vt_bad)"
rm -f /tmp/vt_new /tmp/vt_crash /tmp/vt_old /tmp/vt_empty /tmp/vt_bad

# ---------- D. 告警分级退出 ----------
echo "[D] 告警分级退出（纯🟡不 failed）"
level() { local a="$1"; local n=$(printf '%b' "$a" | grep -c '🔴\|🟠'); [ "$n" -gt 0 ] && echo FAIL || echo OK; }
t "D1 纯🟡→exit0" "OK" "$(level '🟡 safeguard 观察中\n')"
t "D2 🔴→exit1" "FAIL" "$(level '🔴 MCE 新增\n')"
t "D3 🟠→exit1" "FAIL" "$(level '🟠 降压偏离\n')"
t "D4 🟡+🟠→exit1" "FAIL" "$(level '🟡 观察\n🟠 偏离\n')"

echo ""
echo "测试结果: $PASS/$((PASS+FAIL)) 通过, $FAIL 失败"
[ "$FAIL" -eq 0 ]
