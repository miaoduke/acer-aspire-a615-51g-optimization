#!/bin/bash
# 01_提升PL1功耗墙.sh — 提升 PL1(实测有效!)
# 需要 root 权限
# 重要实测结论(2026-08-12): 本机 constraint_0_max_power_uw 报告 15W,
#   但写入 25W 真实生效(冷启动实测功率可达 22-24W,吞吐+20%)!
#   真正的瓶颈是散热(满载98°C热墙)→ 高温下会被热节流压制功耗。

RAPL="/sys/class/powercap/intel-rapl:0"
PL1_MAX=$(cat $RAPL/constraint_0_max_power_uw 2>/dev/null)
PL1_CUR=$(cat $RAPL/constraint_0_power_limit_uw 2>/dev/null)
PL2_CUR=$(cat $RAPL/constraint_1_power_limit_uw 2>/dev/null)
PL2_MAX=$(cat $RAPL/constraint_1_max_power_uw 2>/dev/null)
TARGET=${1:-25000000}

echo "=== 当前 RAPL 功耗限制 ==="
echo -n "PL1 (长时): $((PL1_CUR/1000000))W ($PL1_CUR µW)"
echo "  | 固件报告上限: $((PL1_MAX/1000000))W"
echo -n "PL2 (短时): $((PL2_CUR/1000000))W ($PL2_CUR µW)"
echo "  | 固件报告上限: $([ -n "${PL2_MAX:-0}" ] && [ "$PL2_MAX" -gt 0 ] && echo "$((PL2_MAX/1000000))W" || echo '未报告')"

echo ""
echo "⚠️ 已知事实: 固件报告上限${PL1_MAX}µW,但实测写入${TARGET}µW有效。"
echo "   ⚠️ 风险提示: 本机散热瓶颈(满载98°C/临界100°C),提升PL1会显著升温,"
echo "      务必在低温(<60°C)下使用,必要时配合降压(02脚本)或清灰换硅脂。"

echo ""
echo "=== 尝试提升 PL1 至 $((TARGET/1000000))W ==="
echo $TARGET | sudo tee $RAPL/constraint_0_power_limit_uw

echo ""
echo "=== 验证(写入后立即回读) ==="
NEW=$(cat $RAPL/constraint_0_power_limit_uw)
echo -n "PL1 新值: $((NEW/1000000))W ($NEW µW)"
if [ "$NEW" -ge "$TARGET" ]; then
    echo "  ← 写入成功 ✓"
else
    echo "  ← 被固件/EC钳制为 $((NEW/1000000))W"
fi
echo ""
echo "注意: EC 可能在数秒后重置此值。如需持久化:"
echo "  - 配合 throttled (github.com/erpalma/throttled)"
echo "  - 或写入 /etc/tmpfiles.d/pl1.conf:"
echo "    w /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw - - - - 25000000"