#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""controller.py — 控制操作封装
权限：sudo 免密白名单（install.sh 配置），严格限定以下路径。
"""
import os
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
SCENE_SCRIPT = os.path.join(BASE, "scripts", "场景管理.sh")
M3_SCRIPT = os.path.join(BASE, "backend", "m3_gui.sh")

# 场景定义：key -> (名称, 说明)
SCENES = {
    "ac-perf":  ("插电高性能", "编译/渲染/跑分 · PL=25W · performance"),
    "ac-bal":   ("插电平衡",   "日常办公/开发 · PL=15W"),
    "ac-quiet": ("插电静音",   "夜间/安静环境 · PL=10W"),
    "bat-save": ("离电省电",   "最大续航 · Turbo 关 · 深度省电"),
    "bat-bal":  ("离电均衡",   "离电日常 · PL=12W"),
    "bat-perf": ("离电性能",   "急需性能 · 受固件限制约 8W"),
}
# AC 场景 / DC 场景（用于推荐高亮）
AC_SCENES = ("ac-perf", "ac-bal", "ac-quiet")
DC_SCENES = ("bat-save", "bat-bal", "bat-perf")

# 场景定义参数（与场景管理.sh 一致）：(governor, epp, PL1_W, turbo_ON)
SCENE_PARAMS = {
    "ac-perf": ("performance", "performance", 25, True),
    "ac-bal": ("powersave", "balance_performance", 15, True),
    "ac-quiet": ("powersave", "balance_power", 10, True),
    "bat-save": ("powersave", "power", 10, False),
    "bat-bal": ("powersave", "balance_power", 12, True),
    "bat-perf": ("performance", "performance", 15, True),
}


def get_active_scene(params):
    """按当前系统参数匹配实际生效的场景（无匹配返回 None）"""
    gov = params.get("governor")
    epp = params.get("epp")
    pl1 = round(params["pl1_w"]) if params.get("pl1_w") is not None else None
    turbo = params.get("turbo")
    for key, (g, e, plw, tb) in SCENE_PARAMS.items():
        if gov == g and epp == e and pl1 == plw and turbo is tb:
            return key
    return None


DEFAULT_SCENE_FILE = os.path.expanduser("~/.config/system-console/default_scene")


def get_default_scenes():
    """读取插电/离电默认场景（acdc 自动切换用，独立于手动切换记录）"""
    d = {"LAST_AC": "ac-bal", "LAST_DC": "bat-bal"}
    try:
        with open(DEFAULT_SCENE_FILE) as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    if k in d and v in SCENES:
                        d[k] = v
    except Exception:
        pass
    return d


def set_default_scenes(ac_scene, dc_scene):
    """设置插电/离电默认场景（写 default_scene 文件，用户目录免 sudo；
    手动切换场景不会再覆盖它——默认档位只由用户显式设置）"""
    try:
        os.makedirs(os.path.dirname(DEFAULT_SCENE_FILE), exist_ok=True)
        with open(DEFAULT_SCENE_FILE, "w") as f:
            f.write("LAST_AC=%s\nLAST_DC=%s\n" % (ac_scene, dc_scene))
        return True
    except Exception:
        return False

SERVICES = [
    # 2026-08-31 修正: intel-undervolt 服务不存在(真机名 undervolt)、描述 -100mV 过时(现 -80mV)、
    # 补真机在跑的 undervolt-resume/thermal-guard/uv-safeguard/uv-daily-check
    ("cpu-power-limit", "PL1/PL2 功耗限制"),
    ("turbo-enable", "Turbo 开启守护"),
    ("undervolt", "CPU/GPU 降压 (-80mV)"),
    ("undervolt-resume", "挂起后恢复降压"),
    ("acdc-profile", "AC/DC 自动切换"),
    ("thermal-guard", "温度守护(自动限流)"),
    ("uv-safeguard", "降压安全网(异常关机回退)"),
    ("rasdaemon", "MCE 硬件错误记录"),
    ("thermald", "热管理守护"),
    ("power-profiles-daemon", "电源档位守护"),
]


def _is_password_prompt(stderr: str) -> bool:
    """判断 sudo stderr 是否为密码提示（兼容中英文系统）
    中文: 「sudo: 需要密码」/ 英文: 「sudo: a password is required」/「sudo: password for」"""
    if not stderr:
        return False
    s = stderr.lower()
    return ("password" in s or "需要密码" in stderr or "密码" in s)


def _ensure_auth():
    """确保 sudo 凭据可用：凭据过期时弹 zenity 密码框提权。
    返回 True=可用 / False=用户取消或失败。"""
    try:
        r = subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=5)
        if r.returncode == 0:
            return True
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["zenity", "--password", "--title=控制台授权",
             "--text=此功能需要 root 权限\n输入密码授权（15 分钟内有效）"],
            capture_output=True, text=True, timeout=90)
        if r.returncode != 0 or not r.stdout.strip():
            return False
        r2 = subprocess.run(["sudo", "-S", "-v"], input=r.stdout,
                            capture_output=True, timeout=10)
        return r2.returncode == 0
    except Exception:
        return False


def _run(args, timeout=90):
    """sudo -n 执行；凭据不足时弹窗授权后重试一次。返回 (rc, out, err)
    匹配中英文 sudo 密码提示（中文系统 stderr 为「sudo: 需要密码」）"""
    try:
        r = subprocess.run(["sudo", "-n"] + args, capture_output=True,
                           text=True, timeout=timeout)
        if r.returncode != 0 and _is_password_prompt(r.stderr):
            if _ensure_auth():
                r = subprocess.run(["sudo", "-n"] + args, capture_output=True,
                                   text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "执行超时"
    except Exception as e:
        return -1, "", str(e)


def set_scene(name):
    """应用电源场景"""
    if name not in SCENES:
        return -1, "", "未知场景: %s" % name
    return _run([SCENE_SCRIPT, name])


def m3_mode(on):
    """进入/退出 M3 离电效能模式（非交互后端）"""
    return _run([M3_SCRIPT, "on" if on else "off"])


def gpu_switch(target):
    """切换 GPU 模式（需重启生效）"""
    if target not in ("intel", "nvidia"):
        return -1, "", "未知 GPU 模式"
    return _run(["prime-select", target])


def reboot_system():
    """一键重启（sudoers 白名单 /usr/sbin/reboot，见 system-console-reboot）
    2026-08-31 修复: 原写 _run(["sudo", "/usr/sbin/reboot"])，_run 内部再加 sudo
    → 实际执行 `sudo -n sudo /usr/sbin/reboot`，而白名单只放行 reboot 本身 → 必失败。
    正确: _run(["/usr/sbin/reboot"])（_run 会补 sudo -n）"""
    return _run(["/usr/sbin/reboot"])


def ras_errors():
    """MCE/RAS 事件查询（sudoers 白名单 /usr/sbin/ras-mc-ctl）"""
    try:
        r = subprocess.run(["sudo", "-n", "/usr/sbin/ras-mc-ctl", "--errors"],
                           capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            return 0, r.stdout, ""
        # 无权限或 db 未建：回退 journalctl（rasdaemon 同时写 journal）
        r2 = subprocess.run(["journalctl", "-u", "rasdaemon", "--since", "30 days ago",
                             "--no-pager", "-n", "40"],
                            capture_output=True, text=True, timeout=10)
        return r2.returncode, r2.stdout, r2.stderr
    except Exception as e:
        return 1, "", str(e)


def is_ac():
    """当前是否插电（ACAD online）"""
    try:
        return open("/sys/class/power_supply/ACAD/online").read().strip() == "1"
    except Exception:
        return False


def bench_once():
    """单次基准测试（场景管理.sh bench 白名单已有；单次 ~20s 满载）
    输出兼容两种格式: total=xxx（bench 原始）/ 迭代次数: xxx（场景脚本中文输出）"""
    import re
    # 2026-08-31 修复: 原写 _run(["sudo", "-n", SCENE_SCRIPT, "bench"])，
    # _run 内部已加 sudo → 实际执行 `sudo -n sudo -n <场景管理.sh> bench`，
    # 而 sudoers 只放行 场景管理.sh 本身 → 报"sudo: 需要密码"直接失败。
    # （与 reboot_system() 同类问题，那处已于同日修复，此处遗漏）
    rc, out, err = _run([SCENE_SCRIPT, "bench"], timeout=120)
    if rc != 0:
        return rc, 0, out or err
    m = re.search(r"total=(\d+)", out) or re.search(r"迭代次数[:：]\s*(\d+)", out)
    return rc, int(m.group(1)) if m else 0, out


def bench_protocol():
    """科学基准协议（EMP）：热身 1 次丢弃 + 正式 5 次 + ±2σ 剔离群 + 中位数
    返回 (rc, dict 或 None, err)"""
    import statistics
    if not is_ac():
        return 1, None, "基准测试需在插电下进行（电池供电受功耗墙限制，结果不可比）"
    # 热身（丢弃）
    rc, _, err = bench_once()
    if rc != 0:
        return rc, None, "热身失败: " + (err or "未知错误（可能 sudo 凭据过期，重试一次）")
    samples = []
    for i in range(5):
        rc, iters, err = bench_once()
        if rc != 0:
            # 单次偶发失败重试一次
            rc, iters, err = bench_once()
            if rc != 0:
                return rc, None, "第 %d 次失败: %s" % (i + 1, err or "未知错误")
        if iters <= 0:
            return 1, None, "第 %d 次结果异常（迭代数=0，输出解析失败）" % (i + 1)
        samples.append(iters)
    # ±2σ 剔离群
    mean = statistics.mean(samples)
    sd = statistics.stdev(samples) if len(samples) > 1 else 0
    kept = [x for x in samples if abs(x - mean) <= 2 * sd]
    med = statistics.median(kept)
    kps = med / 20 / 10000  # 20 秒负载, 万/s
    return 0, {"samples": samples, "kept": kept, "median": med, "kps": kps}, ""


def service_states():
    """返回 [(name, desc, active|inactive|failed|None)]（状态已中文化显示）"""
    CN = {"active": "运行中", "inactive": "已停止", "failed": "失败", "activating": "启动中", "deactivating": "停止中"}
    out = []
    for name, desc in SERVICES:
        try:
            r = subprocess.run(["systemctl", "is-active", name],
                               capture_output=True, text=True, timeout=5)
            st = r.stdout.strip() or "unknown"
            out.append((name, desc, CN.get(st, st)))
        except Exception:
            out.append((name, desc, "未知"))
    return out


def mce_count():
    """ras-mc-ctl --summary 的事件计数（无则 0）"""
    try:
        rc, out, _ = _run(["ras-mc-ctl", "--summary"], timeout=15)
        if rc == 0:
            n = 0
            for line in out.splitlines():
                line = line.strip()
                if line and (line[0].isdigit() or line.startswith("No ") or "records" in line):
                    try:
                        n = int(line.split()[0])
                    except Exception:
                        pass
            return n
    except Exception:
        pass
    return None


def temp_module(load):
    """加载/卸载 acer-wmi-battery 模块（SMI 排查期手动控制）。
    加载后 sysfs 温度节点出现；卸载后消失。"""
    try:
        if load:
            r = subprocess.run(["sudo", "-n", "modprobe", "acer_wmi_battery"],
                               capture_output=True, text=True, timeout=10)
        else:
            r = subprocess.run(["sudo", "-n", "modprobe", "-r", "acer_wmi_battery"],
                               capture_output=True, text=True, timeout=10)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return 1, "", str(e)


# 风扇强制冷总开关 —— 默认 False（死机史铁律：fan_boost 即死机 #4 操作，永久禁用）
# 详见下方 fan_boost() 的说明；应急时可用 set_fan_boost_allowed(True) 临时打开。
FAN_BOOST_ALLOWED = False

# thermal_ctl.sh 命令映射（sudoers 白名单限定唯一入口，参数在脚本内校验）
THERMAL_CTL = "/usr/local/bin/thermal_ctl.sh"


def thermal(cmd, *args):
    """散热/功耗统一控制: fan_boost/tcc/pclamp/maxperf/usb/wifi/pl/camera。
    返回 (rc, out, err)。rc=2 表示写入但回读不一致（固件钳制）。
    注: 子命令清单必须与 backend/thermal_ctl.sh 的分支一一对应，
        改动任一侧后请运行 backend/check_ctl_consistency.sh 校验。"""
    try:
        argv = ["sudo", "-n", THERMAL_CTL, cmd] + [str(a) for a in args]
        r = subprocess.run(argv, capture_output=True, text=True, timeout=10)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return 1, "", str(e)


def fan_boost(on, force: bool = False):
    """风扇强制冷: on=True 全速 / on=False 恢复自动。

    ⛔ 2026-08-31 起默认拒绝（死机史铁律）：
    fan_boost 经 ACPI→VFN 共享内存→EC 写入，是【死机 #4 的直接操作】
    （见 未实现清单 第 17 行、第 77 行：永久禁用）。
    此前仅靠"UI 不显示按钮"来维持，任何误调用（脚本/其他代码）都会触发 EC 写入。
    现加硬拦截：默认拒绝，必须显式传 force=True 才会执行（仅应急/debug 用）。

    安全替代：TCC 温度墙偏移 / PL 功耗墙 —— 通过限制热源让 EC 自动调节风扇。
    """
    if not force and not FAN_BOOST_ALLOWED:
        return 1, "", ("已拒绝：fan_boost 为死机 #4 直接操作，项目铁律永久禁用。\n"
                       "安全替代：用 tcc_offset() 温度墙 或 set_pl() 功耗墙限制热源，"
                       "EC 会自动调节风扇。\n"
                       "确需强制执行请调用 fan_boost(on, force=True)（仅限应急/debug）。")
    return thermal("fan_boost", "on" if on else "off")


def set_fan_boost_allowed(v: bool):
    """应急开关：允许/禁止 fan_boost（默认 False）。仅调试用，勿在日常开启。"""
    global FAN_BOOST_ALLOWED
    FAN_BOOST_ALLOWED = bool(v)
    return FAN_BOOST_ALLOWED


def tcc_offset(v):
    """CPU 温度墙偏移（0-63）。"""
    return thermal("tcc", v)


def powerclamp(v):
    """intel_powerclamp 降载百分比（0=关闭, 100=最强降载）。"""
    return thermal("pclamp", v)


def cpu_max_perf(pct):
    """CPU 频率上限百分比（1-100）。"""
    return thermal("maxperf", pct)


def usb_autosuspend(on):
    """USB 自动挂起: on=True 省电 / on=False 常供电。"""
    return thermal("usb", "on" if on else "off")


def set_pl(pl1_w, pl2_w):
    """设置 PL1/PL2 功耗墙(W): 写 RAPL 后读回验证, 返回 (rc, out, err)。
    rc=2 表示写入但实测不一致(固件钳制/热管理覆盖)"""
    return thermal("pl", "%d" % int(pl1_w), "%d" % int(pl2_w))


def usb_verify():
    """验证 USB 自动挂起实际生效情况: 返回 (目标值生效数, 可写设备总数, 不支持数)"""
    import glob
    target = None
    total = ok = nop = 0
    for f in glob.glob("/sys/bus/usb/devices/[0-9]*/power/control"):
        try:
            total += 1
            v = open(f).read().strip()
            if target is None:
                target = v
            if v == "auto":
                ok += 1
            elif v == "on":
                nop += 1  # 常供电(未挂起)设备
        except Exception:
            pass
    return total, ok, nop


def wifi_power(on):
    """WiFi 电源管理: on=True 省电 / on=False 性能。"""
    return thermal("wifi", "on" if on else "off")


def wifi_verify():
    """验证 WiFi power_save 实际状态: 返回 [(接口, 状态)] 状态为 on/off/unknown
    2026-08-20 修复: 原用 iw 命令(不存在) -> FileNotFoundError 空列表; 改用 iwconfig 解析"""
    out = []
    try:
        import glob
        for w in glob.glob("/sys/class/net/wl*"):
            dev = os.path.basename(w)
            r = subprocess.run(["/usr/sbin/iwconfig", dev],
                               capture_output=True, text=True, timeout=5)
            state = "on" if "Power Management:on" in r.stdout else ("off" if "Power Management:off" in r.stdout else "unknown")
            out.append((dev, state))
    except Exception:
        pass
    return out


def camera(on):
    """摄像头开关: on=True 启用(加载 uvcvideo) / on=False 禁用(卸载驱动, 隐私保护)。"""
    return thermal("camera", "on" if on else "off")


def camera_status():
    """摄像头状态: True=已启用(驱动加载) False=已禁用"""
    try:
        import subprocess
        r = subprocess.run(["lsmod"], capture_output=True, text=True, timeout=5)
        return "uvcvideo" in r.stdout
    except Exception:
        return None


M3_SVC = "/etc/systemd/system/m3-power-saver.service"


def m3_active():
    """M3 生效判定：服务文件存在即生效（oneshot 服务 enable 后要重启才 active，
    is-active 会误判未启用——2026-08-20 修复）"""
    return os.path.exists(M3_SVC)


def sudo_ok():
    """检查 sudo 免密白名单是否已配置（静态检查白名单文件，无需 sudo）
    2026-08-31 修正: 与 install.sh 生成物对齐。
    install.sh 生成: system-console / system-console-thermal (+ 可选 reboot/kernel-guard)
    原检查的 99-thermal-ctl / 99-acer-battery-temp 是历史手动配置的文件，
    新机器只跑 install.sh 时不存在 → 启动误报"白名单未配置"。"""
    import os
    S = "/etc/sudoers.d/"
    # 核心必需: 场景/M3 白名单 + thermal_ctl 散热控制
    core = (os.path.exists(S + "system-console")
            and (os.path.exists(S + "system-console-thermal")
                 or os.path.exists(S + "99-thermal-ctl")))  # 两种历史命名都认
    # 可选: reboot / kernel-guard / 电池温度(modprobe) —— 有则提示不强求
    optional_any = any(os.path.exists(S + f) for f in (
        "system-console-reboot", "system-console-kernel-guard",
        "99-acer-battery-temp"))
    return core and optional_any


# ============================================================================
# 2026-08-31 新增: 运维工具集（快照/备份/降权/适配/切Win）
# 这些此前只能命令行执行，现接入 GUI。路径自动探测（项目归档位置可变）。
# ============================================================================

def _find_script(*rel):
    """自动定位脚本: 优先运行目录, 回退到项目归档"""
    cands = [
        os.path.join(BASE, *rel),
        os.path.expanduser("~/桌面/系统控制台/" + "/".join(rel)),
        "/media/<USER>/WS/acer 性能优化方案/03_Linux/性能优化方案_20260822/" + "/".join(rel),
    ]
    for c in cands:
        if os.path.isfile(c):
            return c
    return cands[0]


# ---------- 1. 系统快照（Timeshift，铁律 L1/L2）----------
def snapshot(action="list", desc="", target=""):
    """快照管理（2026-08-31 增强）:
    - list               列出快照
    - create <说明>      创建（可指定 --snapshot-device <target> 选备份盘）
    - delete <编号>      删除指定快照
    timeshift 均需 root，统一走 _run（sudo -n 免密，白名单放行 /usr/bin/timeshift）。"""
    if action == "list":
        return _run(["timeshift", "--list"], timeout=30)
    if action == "create":
        if target:
            # 指定备份盘（如 /dev/sdb1、/dev/sda8 等）
            return _run(["timeshift", "--create", "--comments", desc,
                         "--snapshot-device", target], timeout=120)
        return _run(["timeshift", "--create", "--comments", desc], timeout=120)
    if action == "delete":
        return _run(["timeshift", "--delete", "--snapshot", desc], timeout=60)
    return _run(["timeshift"] + ([action, desc] if desc else [action]), timeout=60)


def snapshot_devices():
    """列出可作备份盘的块设备（排除系统盘/挂载盘），供 GUI 选择
    2026-08-31 修复: ①过滤 lsblk 树形前缀(├─/└─) ②排除 /boot/efi 等系统分区
    返回 [(设备名, 大小, 类型, 标签/挂载点), ...]"""
    out = []
    try:
        r = subprocess.run(["lsblk", "-o", "NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT", "-n"],
                           capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines():
            parts = line.split()
            if not parts:
                continue
            # 去掉树形前缀（├─ └─ ╰─ 等）
            name = parts[0].lstrip("│├└─ ")
            size = parts[1]
            fstype = parts[2] if len(parts) > 2 else ""
            label = parts[3] if len(parts) > 3 else ""
            mount = parts[4] if len(parts) > 4 else ""
            # 跳过: 系统根分区 / 已挂载的 EFI / loop/sr/zram 虚拟设备
            if name.startswith(("loop", "sr", "zram")):
                continue
            # btrfs subvol 挂载点(/, /home, /opt)通过子卷, 物理分区本身挂载点显示为标签或空
            # 但 sdb2 挂载显示 /home 是 btrfs 整盘挂载 → 需排除
            if mount in ("/", "/home", "/boot/efi", "/opt"):
                continue
            # 排除当前系统所在磁盘的分区（btrfs 根挂载的盘）
            if fstype == "btrfs" and mount in ("", "/home", "/opt"):
                continue
            out.append(("/dev/" + name, size, fstype, label, mount))
    except Exception:
        pass
    return out


# ---------- 2. 会话备份（铁律 5）----------
BACKUP_SCRIPT = _find_script("会话备份", "00_保存会话与日志.sh")


def session_backup(desc=""):
    """一键会话备份: bash 00_保存会话与日志.sh <说明>"""
    if not os.path.isfile(BACKUP_SCRIPT):
        return 1, "", "备份脚本不存在: %s" % BACKUP_SCRIPT
    try:
        r = subprocess.run(["bash", BACKUP_SCRIPT, desc], capture_output=True,
                           text=True, timeout=300)
        return r.returncode, r.stdout[-2000:], r.stderr[-1000:]
    except Exception as e:
        return 1, "", str(e)


# ---------- 3. 后台降权（基准测试前置）----------
QUIET_SCRIPT = _find_script("测量脚本", "quiet.sh")
UNQUIET_SCRIPT = _find_script("测量脚本", "unquiet.sh")


def quiet_background(quiet=True):
    """后台进程降权: quiet=True renice+15 / quiet=False 恢复"""
    s = QUIET_SCRIPT if quiet else UNQUIET_SCRIPT
    if not os.path.isfile(s):
        return 1, "", "脚本不存在: %s" % s
    try:
        r = subprocess.run(["bash", s], capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


# ---------- 4. 跨机适配向导（重装/换机）----------
ADAPT_SCRIPT = _find_script("backend", "adapt_test.sh")


def adapt_test(apply=False):
    """跨机适配: apply=False 仅检测报告 / apply=True 检测+应用"""
    if not os.path.isfile(ADAPT_SCRIPT):
        return 1, "", "适配脚本不存在: %s" % ADAPT_SCRIPT
    args = [ADAPT_SCRIPT, "apply"] if apply else [ADAPT_SCRIPT]
    return _run(args, timeout=120)


# ---------- 5. 一键临时启动 Windows（UEFI BootNext）----------
WIN_SCRIPT = _find_script("临时启动Windows.sh")


def boot_windows():
    """临时切换到 Windows（efibootmgr -n BootNext，重启生效，不影响默认启动顺序）
    脚本内部会自我提权 + 交互确认，用 timeout 包住避免 GUI 卡死。
    返回 rc=0 且 out 含 '重启' 提示 = 已排程。"""
    if not os.path.isfile(WIN_SCRIPT):
        return 1, "", "脚本不存在: %s" % WIN_SCRIPT
    try:
        # 脚本含 read 等待确认，GUI 场景下喂 'y' 并限时
        r = subprocess.run(["bash", WIN_SCRIPT], capture_output=True, text=True,
                           input="y\n", timeout=60)
        return r.returncode, r.stdout.strip()[-1500:], r.stderr.strip()[-500:]
    except subprocess.TimeoutExpired:
        return 1, "", "脚本执行超时（可能等待交互确认，已中止）"
    except Exception as e:
        return 1, "", str(e)