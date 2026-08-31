#!/bin/bash
# 02_CPU降压脚本.sh — 安装 intel-undervolt 并应用降压
# 需要 root + 网络(apt)
# ⚠️ 降压过度会导致蓝屏/死机,请从 -50mV 起步逐步测试
# 来源: github.com/georgewhewell/undervolt

if [ "$(id -u)" != "0" ]; then
    echo "需要 root 权限,请用: sudo $0"
    exit 1
fi

echo "=== 1. 检查 intel-undervolt ==="
if ! command -v intel-undervolt >/dev/null 2>&1; then
    echo "未安装,尝试通过 apt 安装..."
    apt-get install -y intel-undervolt 2>&1 || {
        echo "apt 安装失败。请手动安装:"
        echo "  git clone https://github.com/georgewhewell/undervolt"
        echo "  cd undervolt && make && sudo make install"
        exit 1
    }
fi
intel-undervolt read > /dev/null 2>&1 && echo "intel-undervolt 可用" || echo "⚠️ 驱动/MSR 访问可能受限(需 modprobe msr)"

echo ""
echo "=== 2. 选择降压幅度 ==="
echo "推荐起始值(i5-8250U 参考):"
echo "  稳妥:  CPU -50mV / GPU -40mV / Cache -50mV"
echo "  进阶:  CPU -100mV / GPU -80mV / Cache -100mV"
echo ""
read -r -p "输入 CPU Core 偏移(mV,默认 -50): " CPU_MV
CPU_MV=${CPU_MV:--50}
read -r -p "输入 GPU 偏移(mV,默认 -40): " GPU_MV
GPU_MV=${GPU_MV:--40}
read -r -p "输入 CPU Cache 偏移(mV,默认 -50): " CACHE_MV
CACHE_MV=${CACHE_MV:--50}

if [ -f /etc/intel-undervolt.conf ]; then
    cp /etc/intel-undervolt.conf /etc/intel-undervolt.conf.bak
    echo "已备份原配置 → /etc/intel-undervolt.conf.bak"
fi

echo ""
echo "=== 3. 写入配置 /etc/intel-undervolt.conf ==="
cat > /etc/intel-undervolt.conf << EOF
# intel-undervolt 配置(由 02_CPU降压脚本.sh 生成)
undervolt 0 'CPU' $CPU_MV
undervolt 1 'GPU' $GPU_MV
undervolt 2 'CPU Cache' $CACHE_MV
undervolt 3 'System Agent' 0
undervolt 4 'Analog I/O' 0
EOF
echo "✓ 已写入"

echo ""
echo "=== 4. 应用并验证 ==="
intel-undervolt apply && intel-undervolt read

echo ""
echo "=== 5. 稳定性测试 ==="
echo "执行以下命令满载测试至少 5 分钟:"
echo "  sudo stress-ng --cpu 8 --timeout 300s"
echo "如果蓝屏/死机: 降低幅度后重新运行本脚本(-50mV → -30mV)"
echo ""
echo "⚠️ 提示: 降压不持久,重启后需 systemctl 服务或手动 apply:"
echo "  sudo systemctl enable intel-undervolt  # 开机自动应用"