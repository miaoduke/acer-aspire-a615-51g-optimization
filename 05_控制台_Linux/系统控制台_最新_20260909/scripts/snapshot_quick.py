#!/usr/bin/env python3
"""
scripts/snapshot_quick.py — H2.5: tlp-stat 风格完整状态快照

基于 backend/collect_ground_truth.sh（174 行）的 Python 实现
提供更友好的输出 + 模块化
"""
import os
import subprocess
import sys
from pathlib import Path

# GUI 经 subprocess 调用本脚本时 cwd 任意 → 把项目根(脚本上级目录)插进 sys.path,
# 否则 "from src.core.msr_reader import ..." 报 No module named 'src'(2026-09-11 修复)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def read(path, default="—"):
    try:
        with open(path) as f:
            return f.read().strip()
    except (OSError, IOError):
        return default


def cmd(*args, timeout=10):
    try:
        r = subprocess.run(list(args), capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return -1, str(e)


def section(title):
    print(f"\n━━ {title} " + "━" * max(0, 60 - len(title) - 2))


def snapshot():
    print("=" * 60)
    print(f" 系统状态快照 - {os.uname().nodename} - {os.uname().release}")
    print("=" * 60)

    # 1. CPU
    section("CPU")
    rc, out = cmd("lscpu")
    if rc == 0:
        for line in out.split("\n"):
            if any(k in line for k in ["Model name", "Architecture", "CPU(s):", "Thread(s)",
                                        "CPU MHz", "CPU max MHz", "Vendor ID"]):
                print(f"  {line.strip()}")
    print(f"  Governor: {read('/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor')}")
    print(f"  EPP: {read('/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference')}")
    print(f"  Turbo: {read('/sys/devices/system/cpu/intel_pstate/no_turbo')}")
    print(f"  PL1: {read('/sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw', '0')[:8]} uW")
    print(f"  PL2: {read('/sys/class/powercap/intel-rapl:0/constraint_1_power_limit_uw', '0')[:8]} uW")

    # 2. 内存
    section("内存")
    rc, out = cmd("free", "-h")
    if rc == 0:
        for line in out.split("\n")[:3]:
            print(f"  {line}")

    # 3. 电池
    section("电池")
    for f in os.listdir("/sys/class/power_supply/"):
        path = f"/sys/class/power_supply/{f}"
        if os.path.exists(f"{path}/type") and "Battery" in read(f"{path}/type"):
            cap = read(f"{path}/capacity")
            stat = read(f"{path}/status")
            pwr = read(f"{path}/power_now", "0")
            cur = read(f"{path}/current_now", "0")
            vol = read(f"{path}/voltage_now", "0")
            print(f"  [{f}] {cap}% {stat}")
            if pwr != "0":
                print(f"    Power: {int(pwr)/1000000:.2f} W")
            if cur != "0":
                print(f"    Current: {int(cur)/1000:.0f} mA")
            if vol != "0":
                print(f"    Voltage: {int(vol)/1000:.0f} mV")
            full = read(f"{path}/charge_full", "0")
            des = read(f"{path}/charge_full_design", "0")
            if full != "0" and des != "0":
                health = int(full) / int(des) * 100
                print(f"    Health: {health:.1f}%")

    # 4. 温度
    section("温度")
    for tz in sorted(os.listdir("/sys/class/thermal/")):
        if not tz.startswith("thermal_zone"):
            continue
        path = f"/sys/class/thermal/{tz}"
        t = read(f"{path}/temp", "0")
        name = read(f"{path}/type", "?")
        if t != "0" and t != "—":
            print(f"  [{tz}] {name}: {int(t)/1000:.1f}°C")

    # 5. 磁盘
    section("磁盘")
    rc, out = cmd("lsblk", "-o", "NAME,SIZE,FSUSED,MOUNTPOINT", "-nr")
    if rc == 0:
        for line in out.split("\n")[:8]:
            print(f"  {line}")

    # 6. 网络
    section("网络")
    rc, out = cmd("ip", "-br", "addr")
    if rc == 0:
        for line in out.split("\n"):
            if line.strip():
                print(f"  {line}")

    # 7. 服务状态
    section("项目服务")
    # oneshot 型跑完即退, inactive 是正常态 → 用"·预期"标注, 不再误导成故障(2026-09-11)
    for s in ["undervolt", "acdc-profile", "cpu-power-limit", "thermal-guard",
              "msr_deadman.timer", "uv-daily-check.timer", "uv-safeguard", "rasdaemon"]:
        rc, out = cmd("systemctl", "is-active", s)
        # is-active 对 oneshot 退出态返回 rc!=0 且 stdout 为空, 但 stderr 才有 "inactive"
        # → rc!=0 时 stderr 即状态文本
        state = out if (rc == 0 or out) else "inactive"
        if state == "inactive" and s == "uv-safeguard":
            icon, state = "✅", "inactive·预期(oneshot: 开机检测异常关机后退出)"
        else:
            icon = "✅" if state == "active" else "⚠" if state == "inactive" else "❌"
        print(f"  {icon} {s}: {state}")

    # 8. 限流状态（R4 集成）
    section("CPU 限流状态")
    try:
        from src.core.msr_reader import get_throttle_status
        s = get_throttle_status()
        print(f"  {s.summary_text()}")
    except Exception as e:
        print(f"  ⚠ 无法读取: {e}")

    # 9. 降压值
    section("MSR 降压")
    import shutil
    if shutil.which("undervolt"):
        # 2026-09-11 修复: undervolt 读 MSR 需要 root。原裸调用(无 sudo)永远失败,
        # 误报"sudo 缓存过期"。改 sudo -n + 白名单(/usr/local/bin/undervolt), 失败时如实显示
        rc, out = cmd("sudo", "-n", shutil.which("undervolt"), "--read")
        if rc == 0:
            print(f"  {out[:200]}")
        else:
            print(f"  ⚠ undervolt --read 失败: {out[:120]}")
    else:
        print(f"  undervolt 工具未安装")

    # 10. Profile 系统
    section("Profile 配置")
    try:
        from src.core.profile import get_loader, validate_profile
        loader = get_loader()
        names = loader.list_profiles()
        # 检测是否从 profile 加载（vs fallback 硬编码）
        from src.core.profile import get_loader as _gl
        _l = _gl()
        if _l._hardcoded_fallback:
            _using_profile = any(_l.find_profile_path(n) for n in names)
            src_type = 'profile' if _using_profile else 'hardcoded'
        else:
            src_type = 'profile'
        print(f"  加载来源: {src_type}")
        for n in names:
            ok, errs = validate_profile(n)
            icon = "✅" if ok else f"❌({len(errs)})"
            print(f"  {icon} {n}")
    except Exception as e:
        print(f"  ⚠ 无法加载: {e}")

    print("\n" + "=" * 60)


if __name__ == '__main__':
    snapshot()
