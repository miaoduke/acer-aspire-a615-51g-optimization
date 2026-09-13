#!/bin/bash
# =============================================================================
# phase1_health_check.sh — Phase 1 7 天观察期每日健康检查
# =============================================================================
# 用途: 每日运行一次，验证 Phase 1 各项部署正常工作
# 频率: 每日 1 次（用户手动或 cron）
# 退出码: 0=全部正常 / 1=有异常需关注
# =============================================================================

set -e

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
WARN=0
FAIL=0

check_pass() { echo -e "  ${GREEN}✓${NC} $1"; PASS=$((PASS+1)); }
check_warn() { echo -e "  ${YELLOW}⚠${NC} $1"; WARN=$((WARN+1)); }
check_fail() { echo -e "  ${RED}✗${NC} $1"; FAIL=$((FAIL+1)); }

echo "============================================================"
echo "Phase 1 健康检查 - $(date '+%F %T')"
echo "============================================================"
echo ""

# 1. systemd 服务状态
echo "[1] systemd 服务状态"
for s in undervolt acdc-profile cpu-power-limit thermal-guard msr_deadman.timer; do
    state=$(systemctl is-active "$s" 2>/dev/null || true)
    if [ "$state" = "active" ]; then
        check_pass "$s: $state"
    else
        check_warn "$s: $state"
    fi
done
echo ""

# 2. R11 服务依赖（需 daemon-reload 生效）
echo "[2] R11 服务依赖"
if grep -q "After=cpu-power-limit.service" /etc/systemd/system/acdc-profile.service 2>/dev/null; then
    check_pass "acdc-profile.service 含 After=cpu-power-limit"
else
    check_fail "acdc-profile.service 缺 After=cpu-power-limit"
fi
if grep -q "After=cpu-power-limit.service" /etc/systemd/system/thermal-guard.service 2>/dev/null; then
    check_pass "thermal-guard.service 含 After=cpu-power-limit"
else
    check_fail "thermal-guard.service 缺 After=cpu-power-limit"
fi
echo ""

# 3. 降压值（应保持 -100mV）
echo "[3] MSR 降压值"
if [ -x /usr/local/bin/undervolt ]; then
    CURRENT_MV=$(sudo -n /usr/local/bin/undervolt --read 2>/dev/null | grep -oE -- '-?[0-9]+\.[0-9]+ mV' | head -1)
    if [ -n "$CURRENT_MV" ]; then
        check_pass "undervolt 当前值: $CURRENT_MV"
    else
        check_warn "undervolt --read 失败（sudo 缓存过期？）"
    fi
else
    check_warn "undervolt 工具未安装"
fi
echo ""

# 4. deadman 日志（应为空或无异常）
echo "[4] MSR deadman 日志"
if [ -f /var/log/msr_deadman.log ]; then
    LAST=$(tail -1 /var/log/msr_deadman.log 2>/dev/null)
    if echo "$LAST" | grep -q "🔴"; then
        check_warn "发现 deadman 触发记录: $LAST"
    else
        check_pass "deadman 未触发（最新: $LAST）"
    fi
    # 检查标记文件
    if [ -f /var/log/msr_deadman.triggered ]; then
        check_warn "/var/log/msr_deadman.triggered 存在（需手动恢复原降压）"
    else
        check_pass "deadman triggered 文件不存在"
    fi
else
    check_warn "msr_deadman.log 不存在（deadman 尚未运行）"
fi
echo ""

# 5. config.yaml 完整性
echo "[5] config.yaml"
# P1-1 修复: sudo 环境下 $HOME=/root，需探测实际用户
REAL_USER="${SUDO_USER:-$(logname 2>/dev/null || echo "")}"
if [ -z "$REAL_USER" ] || [ "$REAL_USER" = "root" ]; then
    REAL_USER="$(id -un 2>/dev/null || echo "")"
fi
if [ -n "$REAL_USER" ] && [ "$REAL_USER" != "root" ]; then
    CFG="/home/$REAL_USER/.config/system-console/config.yaml"
else
    CFG="$HOME/.config/system-console/config.yaml"
fi
if [ -f "$CFG" ]; then
    for key in base_dir data_dir perf_log_dir config_dir; do
        if grep -q "^$key:" "$CFG"; then
            check_pass "$key 已配置"
        else
            check_warn "$key 缺失"
        fi
    done
else
    check_fail "config.yaml 不存在"
fi
echo ""

# 6. sudoers 校验

echo "[6] sudoers 完整性"
if sudo -n visudo -c -f /etc/sudoers.d/system-console >/dev/null 2>&1; then
    check_pass "system-console sudoers 语法 OK"
else
    check_warn "system-console sudoers 需 root 校验（sudo 缓存过期）"
fi
if sudo -n visudo -c -f /etc/sudoers.d/system-console-thermal >/dev/null 2>&1; then
    check_pass "thermal sudoers 语法 OK"
else
    check_warn "thermal sudoers 需 root 校验（sudo 缓存过期）"
fi
echo ""

# 7. 部署物漂移检测（2026-09-07 审计新增：/usr/local/bin vs 仓库）
echo "[7] 部署物一致性"
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
for s in thermal_ctl.sh uv_daily_check.sh uv_safeguard.sh msr_deadman.sh; do
    if [ -f "/usr/local/bin/$s" ] && [ -f "$APP_DIR/backend/$s" ]; then
        if diff -q "/usr/local/bin/$s" "$APP_DIR/backend/$s" >/dev/null 2>&1; then
            check_pass "$s: /usr/local/bin 与仓库一致"
        else
            check_warn "$s: /usr/local/bin 与仓库有差异（漂移）"
        fi
    fi
done
echo ""

# 8. perf 采样活跃度（2026-09-07 审计新增：防 P0-A 零采样复发）
echo "[8] perf 采样活跃度"
PERF_TSV="$APP_DIR/data/perf/perf_$(date +%Y%m%d).tsv"
if [ -f "$PERF_TSV" ]; then
    LINES=$(wc -l < "$PERF_TSV")
    if [ "$LINES" -le 1 ]; then
        # 当日只有表头 → 检查最近修改时间（超过 1 小时未采样即告警）
        AGE=$(( $(date +%s) - $(stat -c %Y "$PERF_TSV") ))
        if [ "$AGE" -gt 3600 ]; then
            check_fail "perf TSV 当日零采样且 $(( AGE / 60 )) 分钟未更新（P0-A 复发特征！）"
        else
            check_warn "perf TSV 当日暂无采样（控制台可能未启动或窗口隐藏）"
        fi
    else
        check_pass "perf TSV 当日采样 ${LINES} 行"
    fi
else
    check_warn "perf TSV 当日文件不存在（控制台未启动？）"
fi
echo ""

# 总结
echo "============================================================"
echo -e "通过: ${GREEN}$PASS${NC}  警告: ${YELLOW}$WARN${NC}  失败: ${RED}$FAIL${NC}"
echo "============================================================"

if [ $FAIL -gt 0 ]; then
    echo -e "${RED}❌ 有失败项需立即处理${NC}"
    exit 1
elif [ $WARN -gt 0 ]; then
    echo -e "${YELLOW}⚠ 有警告项建议关注${NC}"
    exit 0
else
    echo -e "${GREEN}✅ Phase 1 全部健康${NC}"
    exit 0
fi
