#!/bin/bash
# 04_电源管理全套.sh — 安装配置 TLP + 禁用 thermald + NVIDIA 持久模式
# 需要 root 权限
# 来源: linrunner.de/tlp + NVIDIA 文档
# 修正: NVIDIA -ac 参数(MX150 无此参考值), 提示TLP不管理PL1

echo "=== 1. 安装 TLP ==="
echo "sudo apt install tlp tlp-rdw"

echo ""
echo "=== 2. 禁用 power-profiles-daemon(与TLP冲突) ==="
echo "sudo systemctl stop power-profiles-daemon"
echo "sudo systemctl disable power-profiles-daemon"

echo ""
echo "=== 3. 启用 TLP ==="
echo "sudo systemctl enable tlp"
echo "sudo systemctl start tlp"

echo ""
echo "=== 4. TLP 推荐配置(/etc/tlp.conf) ==="
cat << 'EOF'
# 性能模式(插电)
CPU_SCALING_GOVERNOR_ON_AC=performance
CPU_ENERGY_PERF_POLICY_ON_AC=performance
CPU_BOOST_ON_AC=1
CPU_HWP_DYN_BOOST_ON_AC=1
SCHED_POWERSAVE_ON_AC=0

# 省电模式(电池)
CPU_SCALING_GOVERNOR_ON_BAT=powersave
CPU_ENERGY_PERF_POLICY_ON_BAT=balance_performance
CPU_BOOST_ON_BAT=0
SCHED_POWERSAVE_ON_BAT=1

# 设备管理
DEVICES_TO_DISABLE_ON_STARTUP="bluetooth wwan"
RUNTIME_PM_ON_AC=auto
RUNTIME_PM_ON_BAT=auto
EOF

echo ""
echo "⚠️ 说明: TLP 不管理 PL1/PL2(RAPL)。本机 PL1 固件上限仅 15W,"
echo "   要真正提升需 erpalma/throttled(MSR直写)或BIOS mod,TLP无法解决。"

echo ""
echo "=== 5. 禁用 thermald(允许手动温控) ==="
echo "sudo systemctl stop thermald"
echo "sudo systemctl disable thermald"

echo ""
echo "=== 6. NVIDIA 持久模式 ==="
echo "sudo nvidia-smi -pm 1"
echo ""
echo "⚠️ 上版本建议的 'nvidia-smi -ac 3004,1683' 已移除: MX150 显存 3004MHz 有效值"
echo "   但核心 1683MHz 超出规格,无效参数会被驱动拒绝。日常无需锁频率。"
echo "   如需确认当前时钟: nvidia-smi -q -d CLOCK"