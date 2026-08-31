#!/bin/bash
# =============================================================================
# 00_重建优化栈.sh — 重装系统后一键重建优化栈(工具 + 4 服务 + GRUB + prime)
# =============================================================================
# 依据: AI自主科学优化SOP_Linux_v1_20260813.md + 00_交接手册_重装后启动.md(当前定稿)
# 定稿(2026-08-17): PL1=PL2=25W / Turbo 双守护(MSR bit38 + no_turbo) / 降压 -105mV
#                    / acdc-profile(AC=performance, DC=balanced) / GRUB C-state修复
#                    / prime=intel(禁用独显)
# 用法: sudo ./00_重建优化栈.sh
# 回退: systemctl disable --now cpu-power-limit turbo-enable undervolt undervolt-resume
#       并移除 /etc/default/grub 里的 intel_idle.max_cstate（当前为 4）后 update-grub
# =============================================================================

set -e

if [ "$(id -u)" != "0" ]; then
    echo "需要 root: sudo $0"
    exit 1
fi

echo "=== 重建优化栈开始 $(date '+%F %T') ==="

# ---------- 1. 安装工具 ----------
echo "[1/7] 安装工具..."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    linux-tools-common linux-tools-generic stress-ng msr-tools lm-sensors \
    power-profiles-daemon 2>&1 | tail -3 || echo "⚠️ 部分安装失败, 请手动检查"

modprobe msr 2>/dev/null || true

# ---------- 2. 安装 undervolt(Python版) ----------
echo "[2/7] 安装 undervolt (georgewhewell/undervolt)..."
if [ ! -x /usr/local/bin/undervolt ]; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y git python3-pip > /dev/null 2>&1
    cd /tmp && git clone --depth 1 https://github.com/georgewhewell/undervolt
    pip3 install --break-system-packages ./undervolt 2>&1 | tail -2
fi

# ---------- 3. 创建 cpu-power-limit.service (25W) ----------
echo "[3/7] 创建 cpu-power-limit.service (PL1=PL2=25W)..."
cat > /etc/systemd/system/cpu-power-limit.service << 'EOF'
[Unit]
Description=PL1/PL2 功耗限制 - 防 44W 突刺过热
After=multi-user.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'echo 25000000 > /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw; echo 25000000 > /sys/class/powercap/intel-rapl:0/constraint_1_power_limit_uw'
[Install]
WantedBy=multi-user.target
EOF

# ---------- 4. 创建 turbo-guard.sh 双守护 + turbo-enable.service ----------
echo "[4/7] 创建 Turbo 双守护 (MSR bit38 + no_turbo)..."
cat > /usr/local/bin/turbo-guard.sh << 'EOF'
#!/bin/bash
# Turbo 守护: 覆盖两个 Turbo 开关, 每30s检查修复
#  1. MSR 0x1A0 bit38 (EC 会重置为 1=关Turbo)
#  2. intel_pstate no_turbo sysfs (拔电源/PPD 会置 1=关Turbo, 2026-08-17 发现)
LOG=/var/log/turbo-guard.log
sleep 15
while true; do
  # 1. MSR 0x1A0 bit38
  if [ "$(/usr/sbin/rdmsr -f 38:38 0x1a0 2>/dev/null)" != "0" ]; then
    v=$(/usr/sbin/rdmsr 0x1a0 2>/dev/null || echo 0)
    /usr/sbin/wrmsr -a 0x1a0 $(( 0x$v & ~(1<<38) )) 2>/dev/null || true
    echo "$(date +%H:%M:%S) MSR Turbo 被重置, 已修复" >> $LOG
  fi
  # 2. intel_pstate no_turbo
  if [ "$(cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null)" = "1" ]; then
    echo 0 > /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null
    echo "$(date +%H:%M:%S) no_turbo 被置1, 已修复" >> $LOG
  fi
  sleep 30
done
EOF
chmod +x /usr/local/bin/turbo-guard.sh

cat > /etc/systemd/system/turbo-enable.service << 'EOF'
[Unit]
Description=Turbo Enable guard - MSR 0x1A0 bit38=0 持续守护
After=multi-user.target
[Service]
Type=simple
ExecStart=/usr/local/bin/turbo-guard.sh
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF

# ---------- 5. 创建 undervolt 服务 (降压 -80mV = 2026-08-30 定稿值) ----------
# ⚠️ 2026-08-29 修正(安全项): 原写死 -105mV, 该值曾导致死机 #6
#    (kernel panic "not all cpus entered broadcast exception handler", 见 三电源模式方案_20260818.md 第七节)。
#    且原服务名 intel-undervolt 与真机不符(真机为 undervolt)。
# ⚠️ 2026-08-30 更新: 降压 -50mV → -80mV(已完成全场景验证, 见
#    `降压实验记录_-80mV_20260830.md`; 并已部署 uv-safeguard 异常关机回退)。
#    如需保守值: UV_MV=-50 sudo ./00_重建优化栈.sh
UV_MV=${UV_MV:--80}   # 加深前必须用 测量脚本/uv_sweep_v2.sh 带防护扫描, 禁止手改服务值
echo "[5/7] 创建 undervolt 服务 (降压 ${UV_MV}mV)..."
cat > /etc/systemd/system/undervolt.service << EOF
[Unit]
Description=Intel CPU undervolt (MSR 0x150)
After=multi-user.target
[Service]
Type=oneshot
ExecStart=/usr/local/bin/undervolt --core ${UV_MV} --cache ${UV_MV} --gpu ${UV_MV} --temp 98
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
EOF

# 挂起/休眠后重新应用: MSR 掉电易失, 缺此服务会导致唤醒后降压静默失效
cat > /etc/systemd/system/undervolt-resume.service << EOF
[Unit]
Description=Re-apply undervolt after suspend/resume (MSR is volatile)
After=suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target
[Service]
Type=oneshot
ExecStart=/usr/local/bin/undervolt --core ${UV_MV} --cache ${UV_MV} --gpu ${UV_MV} --temp 98
[Install]
WantedBy=suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target
EOF

# ---------- 6. GRUB C-state + prime ----------
# ⚠️ 2026-08-29 修正: 原逻辑基于 2026-08-18「撤销 max_cstate=1」的决策, 而该实验已失败
#    (08-20 一天内 4 次死机, 见 观察期日志_撤销cstate_20260818.md), 不可再按原逻辑执行。
#    C-state 演进: 9(原始) → 1(0817 死机修复) → 9(0818 撤销, 失败) → 1(0820 回退)
#                  → 6(0821 折中) → 4(现状, 真机实测双向确认)
#    真机实测: /sys/module/intel_idle/parameters/max_cstate = 4, /etc/default/grub 一致。
CSTATE=${CSTATE:-4}   # 覆盖: CSTATE=6 sudo ./00_重建优化栈.sh
echo "[6/7] GRUB C-state=${CSTATE} + prime..."
if ! grep -q "intel_idle.max_cstate" /etc/default/grub; then
    cp /etc/default/grub "/etc/default/grub.bak_$(date +%Y%m%d_%H%M%S)"
    sed -i "s/^GRUB_CMDLINE_LINUX_DEFAULT=\"/GRUB_CMDLINE_LINUX_DEFAULT=\"intel_idle.max_cstate=${CSTATE} /" /etc/default/grub
    update-grub && echo "  ✓ 已写入 max_cstate=${CSTATE} 并 update-grub"
else
    echo "  - 已含 max_cstate 参数, 保持不动: $(grep -o 'intel_idle.max_cstate=[0-9]*' /etc/default/grub)"
fi
# zswap: 与真机保持一致(减少 swap 写盘, 延长 SSD 寿命)
if ! grep -q "zswap.enabled" /etc/default/grub; then
    sed -i "s/^GRUB_CMDLINE_LINUX_DEFAULT=\"/GRUB_CMDLINE_LINUX_DEFAULT=\"zswap.enabled=1 zswap.shrinker_enabled=1 /" /etc/default/grub
    update-grub && echo "  ✓ 已补 zswap 参数"
fi

# 注: acdc-profile 服务由 系统控制台/install.sh 创建(真机实测 active running),
#     本脚本不再重复创建, 也不再视其为废弃 —— 0820 的"已废弃"结论已被真机现状推翻。

# prime-discrete: off (intel 模式, 禁用独显; nvidia 模式=on)
if [ ! -f /etc/prime-discrete ]; then
    echo off > /etc/prime-discrete
fi

# ---------- 7. 启用 + 验证 ----------
echo "[7/7] 启用服务并验证..."
systemctl daemon-reload
# 服务名与真机一致: undervolt(非 intel-undervolt) + undervolt-resume(挂起恢复, 2026-08-29 修正)
systemctl enable --now cpu-power-limit turbo-enable undervolt
systemctl enable undervolt-resume 2>/dev/null   # oneshot 型, 由 suspend.target 触发, 不立即启动

# 降压安全网(2026-08-30 新增): 异常关机(硬死机/掉电)后自动回退保守值,
# 避免"死机→重启→又应用深降压→再死机"的循环。默认保守值 -50mV。
SAFEGUARD_SRC="$(cd "$(dirname "$0")" && pwd)/测量脚本/uv_safeguard.sh"
SAFEGUARD_SVC="$(cd "$(dirname "$0")" && pwd)/测量脚本/uv-safeguard.service"
if [ -f "$SAFEGUARD_SRC" ] && [ -f "$SAFEGUARD_SVC" ]; then
    install -m 0755 "$SAFEGUARD_SRC" /usr/local/bin/uv_safeguard.sh
    install -m 0644 "$SAFEGUARD_SVC" /etc/systemd/system/uv-safeguard.service
    systemctl daemon-reload
    systemctl enable uv-safeguard.service 2>/dev/null
    echo "  ✓ 降压安全网 uv-safeguard 已部署(异常关机回退 -50mV)"
else
    echo "  ⚠️ 未找到 uv_safeguard 文件, 跳过(深降压将缺少自动回退保护)"
fi

# 降压稳定性每日自检(2026-08-30 新增): 观察期核心工具。
# 每日 10:00 + 开机 3 分钟后运行, 检查 MCE 增量/降压值/异常关机/服务状态,
# 正常时静默, 异常时桌面通知 + 写 /var/log/uv_daily_check.alert
DC_SRC="$(cd "$(dirname "$0")" && pwd)/测量脚本/uv_daily_check.sh"
DC_SVC="$(cd "$(dirname "$0")" && pwd)/测量脚本/uv-daily-check.service"
DC_TMR="$(cd "$(dirname "$0")" && pwd)/测量脚本/uv-daily-check.timer"
if [ -f "$DC_SRC" ] && [ -f "$DC_SVC" ] && [ -f "$DC_TMR" ]; then
    install -m 0755 "$DC_SRC" /usr/local/bin/uv_daily_check.sh
    install -m 0644 "$DC_SVC" /etc/systemd/system/uv-daily-check.service
    install -m 0644 "$DC_TMR" /etc/systemd/system/uv-daily-check.timer
    # 期望值与本次重建保持一致
    sed -i "s/^Environment=EXPECT_MV=.*/Environment=EXPECT_MV=${UV_MV#-}/" /etc/systemd/system/uv-daily-check.service
    systemctl daemon-reload
    systemctl enable --now uv-daily-check.timer 2>/dev/null
    echo "  ✓ 每日自检 uv-daily-check.timer 已启用(期望 -${UV_MV#-}mV)"
else
    echo "  ⚠️ 未找到 uv_daily_check 文件, 跳过(观察期将缺少自动巡检)"
fi

sleep 20  # 等 turbo-guard 首次检查

echo ""
echo "=== 验证矩阵 ==="
echo -n "PL1: "; cat /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw
echo -n "PL2: "; cat /sys/class/powercap/intel-rapl:0/constraint_1_power_limit_uw
echo -n "Turbo bit38: "; rdmsr -f 38:38 0x1a0 2>/dev/null || echo "(需 msr)"
echo -n "no_turbo: "; cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null
echo -n "降压: "; undervolt --read 2>/dev/null | sed -n '2,4p' | tr '\n' ' ' || echo "(需手动验证)"
echo ""
echo -n "max_cstate: "; cat /sys/module/intel_idle/parameters/max_cstate 2>/dev/null || echo "(需重启生效)"
echo -n "prime-discrete: "; cat /etc/prime-discrete
for svc in cpu-power-limit turbo-enable undervolt uv-safeguard; do
    # uv-safeguard 是 oneshot 型, is-active 对已执行完的 oneshot 返回 inactive, 故改查 enabled
    if [ "$svc" = "uv-safeguard" ]; then
        systemctl is-enabled "$svc" >/dev/null 2>&1 && echo "$svc: enabled ✓" || echo "$svc: ✗ 未启用"
    else
        systemctl is-active "$svc" >/dev/null 2>&1 && echo "$svc: active ✓" || echo "$svc: ✗ 未激活"
    fi
done
echo ""
echo "=== 完成 ==="
echo "注意: GRUB C-state 参数(intel_idle.max_cstate=${CSTATE})需重启后生效"
echo "      降压/PL/Turbo 无需重启, 立即生效"
echo "本次重建降压值: ${UV_MV}mV (安全上限参考: -105mV 曾致死机 #6, 勿越)"
echo "回退: systemctl disable --now cpu-power-limit turbo-enable undervolt undervolt-resume"
echo "      并移除 /etc/default/grub 中的 intel_idle.max_cstate=${CSTATE} 后 update-grub"
