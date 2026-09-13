#!/bin/bash
# =============================================================================
# uv_set.sh — GUI 降压调节的白名单落点（2026-09-11 新增）
# =============================================================================
# 用法: sudo uv_set.sh <core_mv> <gpu_mv> [temp]
#   core_mv: 负值或 0，core 与 cache 域同值写入（电气耦合，必须一致）
#   gpu_mv : 负值或 0，GPU 域独立
#   temp   : 温度墙 °C（可选，默认不动）
# 安全设计:
#   · 范围硬校验: -130 ≤ mv ≤ 0（超出拒绝；-130 是本机型 D7 验收的物理上限余量）
#   · 原子更新: 写 .tmp → visudo 式校验行 → mv，失败自动回滚，service 永不半写
#   · 应用即校验: 写 MSR 后立即 --read 回读，实测值与目标差 >4.25mV(量化步长2.5档)判失败
#   · 守护链自动感知: uv_safeguard / uv_daily_check / msr_deadman 均 grep 本
#     service 文件的 --core 值 → 改文件即改三重守护的基准，无需另行同步
#   · 全程留痕: 日志追加 /var/log/uv_set.log（谁在何时改成了什么）
# 退出码: 0=成功 / 1=参数或范围拒绝 / 2=应用或回读校验失败
# =============================================================================
set -eu
SVC=/etc/systemd/system/undervolt.service
UV=/usr/local/bin/undervolt
LOG=/var/log/uv_set.log
CUR_MV_FILE="$SVC"   # 与 msr_deadman.sh 同源: 三个守护都从 service 文件 grep --core

log() { echo "$(date '+%F %T') $1" >> "$LOG"; }

# ---------- 1. 参数与范围校验 ----------
[ $# -ge 2 ] || { echo "用法: uv_set.sh <core_mv> <gpu_mv> [temp]"; exit 1; }
CORE=$1; GPU=$2; TEMP=${3:-}
valid() { case "$1" in ''|*[!0-9-]*) return 1;; esac
        [ "$1" -le 0 ] && [ "$1" -ge -130 ]; }
valid "$CORE" || { echo "❌ core 越界(0 ~ -130): $CORE"; exit 1; }
valid "$GPU"  || { echo "❌ gpu 越界(0 ~ -130): $GPU";  exit 1; }
[ -n "$TEMP" ] && { case "$TEMP" in ''|*[!0-9]*) echo "❌ temp 非法: $TEMP"; exit 1;; esac
                   [ "$TEMP" -ge 60 ] && [ "$TEMP" -le 105 ] || { echo "❌ temp 越界(60~105°C): $TEMP"; exit 1; }; }
[ -x "$UV" ] || { echo "❌ undervolt 工具不可用"; exit 2; }

# ---------- 2. 备份 + 原子改 service ----------
cp "$SVC" "${SVC}.bak" 2>/dev/null || true
TEMPF=$(mktemp)
sed -E "s/--core +-[0-9]+/--core $CORE/; s/--cache +-[0-9]+/--cache $CORE/; s/--gpu +-[0-9]+/--gpu $GPU/; s/--temp +[0-9]+/--temp $TEMP/" "$SVC" > "$TEMPF" || { echo "❌ 生成失败"; exit 2; }
grep -q -- "--core $CORE" "$TEMPF" && grep -q -- "--cache $CORE" "$TEMPF" && grep -q -- "--gpu $GPU" "$TEMPF" \
  || { echo "❌ 行校验失败，未落盘"; exit 2; }
install -m 644 "$TEMPF" "$SVC" && rm -f "$TEMPF"

# ---------- 3. 立即应用 + 回读校验 ----------
ARGS=(--core "$CORE" --cache "$CORE" --gpu "$GPU")
[ -n "$TEMP" ] && ARGS+=(--temp "$TEMP")
if ! "$UV" "${ARGS[@]}" 2>&1; then
  cp "${SVC}.bak" "$SVC" 2>/dev/null || true
  log "FAIL apply core=$CORE gpu=$GPU — 已回滚 service 文件"
  echo "❌ 应用失败，service 已回滚"; exit 2
fi
READ_CORE=$("$UV" --read 2>/dev/null | grep '^core:' | grep -oE -- '-?[0-9.]+' | head -1 || echo 0)
# 量化步长 2.5mV，容差 4.25mV 内视为一致（|实测 - 目标| 判定）
ACT=$(awk -v r="$READ_CORE" -v t="$CORE" 'BEGIN{ d = r - t; if (d < 0) d = -d; print (d < 4.25) ? 1 : 0 }')
[ "$ACT" = "1" ] || { cp "${SVC}.bak" "$SVC" 2>/dev/null || true; "$UV" --core "$(grep -oE -- '--core -?[0-9]+' "${SVC}.bak" | awk '{print $2}')" --cache "$(grep -oE -- '--cache -?[0-9]+' "${SVC}.bak" | awk '{print $2}')" --gpu "$(grep -oE -- '--gpu -?[0-9]+' "${SVC}.bak" | awk '{print $2}')" >/dev/null 2>&1 || true
  log "FAIL verify read=$READ_CORE target=$CORE — 已回滚"
  echo "❌ 回读校验失败(实测 ${READ_CORE}mV)，已回滚"; exit 2; }

# ---------- 4. 同步挂起恢复服务(2026-09-11: 否则 suspend 唤醒后 MSR 清零会被
# resume 服务按旧值重打, GUI 改的 -100 在睡眠唤醒后悄悄变回旧档) ----------
RESUME_SVC=/etc/systemd/system/undervolt-resume.service
if [ -f "$RESUME_SVC" ]; then
    sed -E -i "s/--core +-[0-9]+/--core $CORE/; s/--cache +-[0-9]+/--cache $CORE/; s/--gpu +-[0-9]+/--gpu $GPU/; s/--temp +[0-9]+/--temp ${TEMP:-98}/" "$RESUME_SVC" 2>/dev/null || true
    grep -q -- "--core $CORE" "$RESUME_SVC" && echo "✓ undervolt-resume.service 已同步 (唤醒后重打 $CORE mV)" \
        || echo "⚠ resume 服务同步失败(下次唤醒值可能漂移, 手工核对 grep core $RESUME_SVC)"
fi

# ---------- 5. 下次开机生效确认 ----------
systemctl daemon-reload 2>/dev/null || true
log "OK core=$CORE gpu=$GPU temp=${TEMP:-unchanged} (read: $READ_CORE)"
echo "✓ 已应用 core/cache=$CORE mV, gpu=$GPU mV${TEMP:+, 温度墙 ${TEMP}°C}（实测 ${READ_CORE}mV）"
echo "✓ 三重守护(uv_safeguard/uv_daily_check/msr_deadman)基准已同步为 $CORE mV"
