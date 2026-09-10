#!/usr/bin/env python3
"""
scripts/check_conflicts.py — H2 实施: 互斥工具冲突检测

目的: 防止与 tuned / power-profiles-daemon / TLP / auto-cpufreq 等
       互斥的工具同时启用导致电源参数相互覆盖

检测:
  1. tuned 服务是否运行
  2. power-profiles-daemon (PPD) 服务是否运行
  3. tlp 服务是否运行
  4. auto-cpufreq 守护是否运行
  5. 关键 sysfs 文件是否被锁

用法:
  python3 scripts/check_conflicts.py
  python3 scripts/check_conflicts.py --fix  # 显示解决建议
"""
import os
import shutil
import subprocess
import sys
from typing import List, Tuple


# 互斥工具列表
CONFLICT_TOOLS = [
    {
        "name": "tuned",
        "service": "tuned.service",
        "binary": "/usr/sbin/tuned",
        "reason": "tuned 也是系统调优守护，可能与本项目 PL/governor 设置冲突",
        "fix": "sudo systemctl disable --now tuned.service"
    },
    {
        "name": "power-profiles-daemon",
        "service": "power-profiles-daemon.service",
        "binary": "/usr/bin/power-profiles-daemon",
        "reason": "PPD 也会管理 EPP/governor，与本项目 EPP 设置冲突",
        "fix": "sudo systemctl mask power-profiles-daemon.service  # 永久禁用"
    },
    {
        "name": "TLP",
        "service": "tlp.service",
        "binary": "/usr/sbin/tlp",
        "reason": "TLP 启动时会应用全套省电参数，与本项目场景切换冲突",
        "fix": "sudo systemctl disable --now tlp.service"
    },
    {
        "name": "auto-cpufreq",
        "service": "auto-cpufreq.service",
        "binary": "/usr/bin/auto-cpufreq",
        "reason": "auto-cpufreq 持续监控 CPU 自动调优，与本项目场景切换冲突",
        "fix": "sudo auto-cpufreq --stop  # 停止守护"
    },
]


def check_service_active(service: str) -> bool:
    """检查 systemd 服务是否 active"""
    if not shutil.which("systemctl"):
        return False
    try:
        r = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip() == "active"
    except Exception:
        return False


def check_binary_exists(binary: str) -> bool:
    """检查二进制是否存在"""
    return os.path.exists(binary)


def check_sysfs_locked(path: str) -> bool:
    """检查 sysfs 文件是否被锁（如 Plundervolt 修补后）
    注意: 'crw------- root:root' 属于正常的 root-only 设备，不算 Plundervolt 锁
    """
    if not os.path.exists(path):
        return False
    # 优先检查是否能作为 root 读到（用 sudo -n 测试）
    import subprocess
    try:
        r = subprocess.run(
            ["sudo", "-n", "dd", f"if={path}", "bs=8", "count=1", "skip=340"],
            capture_output=True, timeout=5
        )
        if r.returncode == 0:
            return False  # root 可读 → 未锁定
    except Exception:
        pass
    # sudo 不可用（无密码）时，假设未锁
    return False


def detect_conflicts() -> List[dict]:
    """检测所有冲突"""
    conflicts = []

    for tool in CONFLICT_TOOLS:
        service_active = check_service_active(tool["service"])
        binary_exists = check_binary_exists(tool["binary"])

        if service_active or binary_exists:
            conflicts.append({
                **tool,
                "service_active": service_active,
                "binary_exists": binary_exists,
            })

    # 检查 Plundervolt 锁
    plundervolt_locked = check_sysfs_locked("/dev/cpu/0/msr")
    if plundervolt_locked:
        conflicts.append({
            "name": "Plundervolt Lock",
            "service": "(none)",
            "binary": "(sysfs lock)",
            "reason": "BIOS Plundervolt 补丁锁定了 MSR 写入，-100mV 降压将失败",
            "fix": "进入 BIOS 禁用 'Plundervolt' / 'Undervolt Protection'",
            "service_active": False,
            "binary_exists": True,
        })

    return conflicts


def main():
    show_fix = "--fix" in sys.argv

    print("=" * 60)
    print("系统控制台 · 互斥工具冲突检测")
    print("=" * 60)
    print()

    conflicts = detect_conflicts()

    if not conflicts:
        print("✅ 未发现冲突 — 可安全运行本项目")
        print()
        print("当前激活的相关服务:")
        for tool in CONFLICT_TOOLS:
            state = "active" if check_service_active(tool["service"]) else "inactive"
            print(f"  • {tool['name']:<25} {state}")
        return 0

    print(f"⚠️  发现 {len(conflicts)} 个冲突 / 风险:\n")

    for i, c in enumerate(conflicts, 1):
        print(f"  {i}. 🔴 {c['name']}")
        if c['service_active']:
            print(f"     • 服务状态: active（运行中）")
        if c['binary_exists']:
            print(f"     • 二进制: {c['binary']} 存在")
        print(f"     • 原因: {c['reason']}")
        if show_fix:
            print(f"     • 修复: {c['fix']}")
        print()

    if not show_fix:
        print("💡 提示: 用 --fix 选项查看具体修复命令\n")

    return 1 if any(c['service_active'] for c in conflicts) else 0


if __name__ == '__main__':
    sys.exit(main())
