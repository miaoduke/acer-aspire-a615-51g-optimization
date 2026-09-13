#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""controller.py — 控制操作封装
权限：sudo 免密白名单（install.sh 配置），严格限定以下路径。

H1 改造: BASE 改为从 Config 读取，支持多机器部署
"""
import os
import subprocess
from pathlib import Path
from src.core.i18n import T

# H1: 路径配置化（优先用 Config，fallback 到原硬编码）
try:
    from src.core.config import Config
    _cfg = Config.get()
    BASE = str(_cfg.base_dir)
except ImportError:
    # 兼容旧启动方式（直接 python3 controller.py）
    BASE = os.path.dirname(os.path.abspath(__file__))

SCENE_SCRIPT = os.path.join(BASE, "scripts", "场景管理.sh")
M3_SCRIPT = os.path.join(BASE, "backend", "m3_gui.sh")


def _alias_script(real_path, alias_name):
    """sudoers 无法匹配含空格路径 → 特权脚本走 /usr/local/bin 无空格别名。
    别名存在且指向本文件才用；缺失/陈旧时回退原路径（提权弹窗兜底）。"""
    alias = "/usr/local/bin/" + alias_name
    try:
        if os.path.isfile(real_path) and os.path.samefile(alias, real_path):
            return alias
    except OSError:
        pass
    return real_path


# sudoers 免密别名(由 install.sh [1/7] 创建): 无空格路径, sudo -n 直接匹配
SCENE_SCRIPT = _alias_script(SCENE_SCRIPT, "sc-scene-switch.sh")
M3_SCRIPT = _alias_script(M3_SCRIPT, "sc-m3-gui.sh")

# 场景定义：key -> (名称, 说明)
SCENES = {
    "ac-perf":  ("插电高性能", "编译/渲染/跑分 · PL=25W · performance"),
    "ac-bal":   ("插电平衡",   "日常办公/开发 · PL=15W"),
    "ac-quiet": ("插电静音",   "夜间/安静环境 · PL=10W"),
    "bat-save": ("离电省电",   "最大续航 · Turbo 关 · 深度省电"),
    "bat-bal":  ("离电均衡",   "离电日常 · PL=12W"),
    "bat-perf": ("离电性能",   "急需性能 · 受固件限制约 8W"),
}

# Phase 2 G1: SCENES / SCENE_PARAMS 现在从 profile 加载
# （见下面的 _load_scenes_from_profiles 和 _load_scene_params_from_profiles）
# 上面是 fallback 硬编码，加载失败时使用
_LOADED_FROM_PROFILE = False


def _load_scenes_from_profiles():
    """从 profile 配置加载 SCENES（若可用）"""
    try:
        from src.core.profile import get_loader
        loader = get_loader()
        result = {}
        for name in loader.list_profiles():
            if name in ('balanced', 'user_custom'):
                continue
            try:
                p = loader.load(name)
                result[name] = (p.summary, _profile_to_desc(p))
            except Exception:
                pass
        return result if result else None
    except Exception:
        return None


def _profile_to_desc(profile):
    """从 profile 生成简短描述"""
    parts = []
    pl1 = profile.get("cpu", "pl1_watts")
    if pl1:
        parts.append(f"PL={pl1}W")
    gov = profile.get("cpu", "governor")
    if gov:
        parts.append(gov)
    turbo = profile.get("cpu", "turbo")
    if turbo == "0":
        parts.append("Turbo off")
    return " · ".join(parts) if parts else profile.summary


def _load_scene_params_from_profiles():
    """从 profile 配置加载 SCENE_PARAMS"""
    try:
        from src.core.profile import get_loader
        loader = get_loader()
        result = {}
        for name in ('ac-perf', 'ac-bal', 'ac-quiet', 'bat-save', 'bat-bal', 'bat-perf'):
            try:
                p = loader.load(name)
                gov = p.get("cpu", "governor")
                epp = p.get("cpu", "energy_performance_preference")
                pl1 = p.get("cpu", "pl1_watts")
                turbo = p.get("cpu", "turbo") == "1"
                if gov and epp and pl1:
                    result[name] = (gov, epp, int(pl1), turbo)
            except Exception:
                pass
        return result if len(result) == 6 else None
    except Exception:
        return None


# 实际加载：profile 优先，失败则用上面的硬编码
_PROFILE_SCENES = _load_scenes_from_profiles()
if _PROFILE_SCENES is not None:
    SCENES = _PROFILE_SCENES
    _LOADED_FROM_PROFILE = True

_PROFILE_SCENE_PARAMS = _load_scene_params_from_profiles()
if _PROFILE_SCENE_PARAMS is not None:
    SCENE_PARAMS = _PROFILE_SCENE_PARAMS
    _LOADED_FROM_PROFILE = True
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
    # 2026-08-31 修正: intel-undervolt 服务不存在(真机名 undervolt)、
    # 补真机在跑的 undervolt-resume/thermal-guard/uv-safeguard/uv-daily-check
    # 2026-09-01: 降压描述同步 -100mV 定稿
    # 2026-09-11 修正: 移除 turbo-enable(单元从未存在,幽灵条目永远 inactive 徒增困惑;
    # turbo 由场景管理直接管理) + rasdaemon 补录(2026-09-11 重装恢复)
    ("cpu-power-limit", T("PL1/PL2 功耗限制")),
    ("undervolt", T("CPU/GPU 降压 (-100mV)")),
    ("undervolt-resume", T("挂起后恢复降压")),
    ("acdc-profile", T("AC/DC 自动切换")),
    ("thermal-guard", T("温度守护(自动限流)")),
    ("uv-safeguard", T("降压安全网(异常关机回退)")),
    ("rasdaemon", T("MCE 硬件错误记录")),
    ("thermald", T("热管理守护")),
    ("power-profiles-daemon", T("电源档位守护")),
]

# 非预期常驻服务：inactive 属正常（oneshot 跑完即退 / 场景脚本主动停 / 未安装由脚本自管）
EXPECTED_IDLE = {
    "undervolt-resume": T("oneshot：仅在挂起恢复时运行"),
    "uv-safeguard": T("oneshot：仅在启动时检测异常关机"),
    "thermald": T("已由自研 thermal-guard 替代（85°C 降 PL1），避免双热守护打架"),
    "power-profiles-daemon": T("已 mask：与场景管理的 EPP/governor 冲突（2026-09-11）"),
}


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
    匹配中英文 sudo 密码提示（中文系统 stderr 为「sudo: 需要密码」）
    注: 所有需要 root 的操作都应走此函数（统一弹窗提权）"""
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


def auth_status():
    """sudo 凭据当前是否有效（15 分钟缓存期内），无需弹窗"""
    try:
        r = subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def elevate():
    """一键提权：凭据过期时弹 zenity 密码窗，成功后 15 分钟内所有功能免密。
    返回 (ok, msg)"""
    if auth_status():
        return True, "sudo 凭据已有效（15 分钟缓存期内）"
    if _ensure_auth():
        return True, "授权成功，15 分钟内所有控制功能可用"
    return False, "授权已取消或失败"


def set_scene(name):
    """应用电源场景"""
    if name not in SCENES:
        return -1, "", "未知场景: %s" % name
    rc, out, err = _run([SCENE_SCRIPT, name])

    # W5: 场景切换后调 plugin（插件扩展点）
    if rc == 0:
        try:
            from src.core.plugin import get_registry, PluginContext
            registry = get_registry()
            ctx = PluginContext(dry_run=False)
            # 调 thermal_ctl plugin（与 controller.thermal() 兼容）
            registry.apply_plugin("thermal_ctl", ctx)
            # 调 hwp_dynamic_boost plugin（按 scene 设置）
            ctx.results['scene_name'] = name
            registry.apply_plugin("hwp_dynamic_boost", ctx)
        except Exception:
            # plugin 失败不影响场景切换
            pass

    return rc, out, err


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
    """MCE/RAS 事件查询（sudoers 白名单 /usr/sbin/ras-mc-ctl；无白名单时弹窗提权）"""
    try:
        rc, out, err = _run(["/usr/sbin/ras-mc-ctl", "--errors"], timeout=15)
        if rc == 0 and out:
            return 0, out, ""
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
    from src.core.i18n import T
    CN = {"active": T("运行中"), "inactive": T("已停止"), "failed": T("失败"),
          "activating": T("启动中"), "deactivating": T("停止中")}
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
    """真实 CPU MCE 计数（ras-mc-ctl，2026-09-04 P0-1 重写）
    旧版把所有数字开头行取最后一个 —— PCIe AER 段（51 Corrected errors...）
    会覆盖/混入计数，造成误报。新版只解析 MCE 段落：
      - "No MCE errors." → 0
      - "MCE records summary:" 后制表符行 "<count> <msg> errors" 求和
    ras-mc-ctl 不可用返回 None（调用方按未知处理，不误报）"""
    try:
        rc, out, _ = _run(["ras-mc-ctl", "--summary"], timeout=15)
        if rc == 0 and out:
            if "No MCE errors" in out:
                return 0
            total, in_mce = 0, False
            for line in out.splitlines():
                s = line.strip()
                if s.startswith("MCE records summary:") or s.startswith("MCE events:"):
                    in_mce = True
                    continue
                if in_mce:
                    if s and not line.startswith(("\t", " ")):
                        in_mce = False  # 下一段落（如 Extlog/AER）边界，止步
                    else:
                        try:
                            total += int(s.split()[0])
                        except (ValueError, IndexError):
                            pass
            return total
    except Exception:
        pass
    return None


def temp_module(load):
    """加载/卸载 acer-wmi-battery 模块（SMI 排查期手动控制）。
    加载后 sysfs 温度节点出现；卸载后消失。"""
    if load:
        return _run(["/usr/sbin/modprobe", "acer_wmi_battery"], timeout=10)
    return _run(["/usr/sbin/modprobe", "-r", "acer_wmi_battery"], timeout=10)


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
    return _run([THERMAL_CTL, cmd] + [str(a) for a in args], timeout=10)


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
    # 2026-09-11 修复: optional_any(reboot/kernel-guard/电池温度)是历史手动配置件,
    # 重装后不存在 → 启动误报"白名单未配置"弹窗。注释本意"有则提示不强求"，
    # 却被写成了硬门槛。核心项齐即视为已配置, 可选项不再影响判定。
    return core


# ============================================================================
# 2026-08-31 新增: 运维工具集（快照/备份/降权/适配/切Win）
# 这些此前只能命令行执行，现接入 GUI。路径自动探测（项目归档位置可变）。
# ============================================================================

def _find_script(*rel):
    """自动定位脚本: 优先运行目录, 回退到项目归档"""
    cands = [
        os.path.join(BASE, *rel),
        os.path.expanduser("~/.local/share/系统控制台/" + "/".join(rel)),
        # 归档回退：自动探测数据盘挂载点（WS 盘历史归档; WS1 盘已不存在,2026-09-11 审计移除死路径）
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
ADAPT_SCRIPT = _alias_script(_find_script("backend", "adapt_test.sh"), "sc-adapt-test.sh")
# 降压调节(2026-09-11): core+cache 电气耦合必须同值, GPU 域独立; 落点 uv_set.sh
# 做范围硬校验/原子改 service/应用后回读校验, 三重守护基准随 service 文件自动同步
UV_SET_SCRIPT = _alias_script(_find_script("backend", "uv_set.sh"), "sc-uv-set.sh")
# GRUB 启动菜单时间(2026-09-11): 备份+RECORDFAIL 同步+update-grub+cfg 校验
GRUB_TIMEOUT_SCRIPT = _alias_script(_find_script("backend", "grub_timeout.sh"), "sc-grub-timeout.sh")


def grub_timeout(seconds, style="menu"):
    """设置 GRUB 启动菜单等待时间。seconds: 0=直接启动, 1-300; style: menu|hidden。
    自动同步 GRUB_RECORDFAIL_TIMEOUT(异常关机后不再回退 30 秒默认)。
    备份: /etc/default/grub.grubtime.bak。返回 (rc, out, err)。"""
    return _run([GRUB_TIMEOUT_SCRIPT, str(seconds), style], timeout=90)


def grub_timeout_current():
    """读当前 GRUB_TIMEOUT / STYLE(纯文本读取, 无需 root)。返回 (timeout, style) 或 None。"""
    try:
        timeout, style = None, "menu"
        with open("/etc/default/grub") as f:
            for line in f:
                if line.startswith("GRUB_TIMEOUT="):
                    timeout = line.split("=", 1)[1].strip()
                elif line.startswith("GRUB_TIMEOUT_STYLE="):
                    style = line.split("=", 1)[1].strip()
        return (timeout, style) if timeout is not None else None
    except OSError:
        return None


def uv_set(core_mv, gpu_mv, temp_c=None):
    """GUI 降压调节入口。返回 (rc, out, err)。
    core_mv: core+cache 联动值(0 ~ -130mV); gpu_mv: GPU 域独立(0 ~ -130mV);
    temp_c: 温度墙(60~105°C, None 不动)。
    uv_set.sh: 越界拒绝 → 原子改 undervolt.service → 写 MSR → 回读校验(容差 4.25mV)
    → 失败自动回滚。uv_safeguard/uv_daily_check/msr_deadman 从 service 文件 grep
    --core 值, 改文件即同步三重守护基准。"""
    args = [UV_SET_SCRIPT, str(core_mv), str(gpu_mv)]
    if temp_c is not None:
        args.append(str(temp_c))
    return _run(args, timeout=30)


def uv_read():
    """读当前各域降压实测值(免密白名单)。返回 dict 或 None。"""
    rc, out, _ = _run(["/usr/local/bin/undervolt", "--read"], timeout=10)
    if rc != 0:
        return None
    d = {}
    for line in out.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip()
            if k in ("core", "gpu", "cache", "uncore"):
                try:
                    d[k] = float(v.strip().rstrip("mV").strip())
                except ValueError:
                    pass
            elif k == "temperature target":
                # 输出形如 "-2 (98C)": 括号里的才是温度墙 °C
                import re
                m = re.search(r"\((\d+)C\)", v)
                if m:
                    d["temp_target"] = int(m.group(1))
    return d or None


def adapt_test(apply=False):
    """跨机适配: apply=False 仅检测报告 / apply=True 检测+应用"""
    if not os.path.isfile(ADAPT_SCRIPT):
        return 1, "", "适配脚本不存在: %s" % ADAPT_SCRIPT
    args = [ADAPT_SCRIPT, "apply"] if apply else [ADAPT_SCRIPT]
    return _run(args, timeout=120)


# ---------- 4b. 隐形功能 GUI 化（2026-09-07 审计 A 类/B 类收编）----------
SNAPSHOT_QUICK = _find_script("scripts", "snapshot_quick.py")
TRY_PROFILE_SCRIPT = _find_script("scripts", "try_user_profile.sh")


def system_snapshot():
    """完整系统状态快照（tlp-stat 风格全景诊断，无需 root）
    输出 CPU/Governor/PL/内存/电池健康/温度/磁盘/限流全景 —— 排障时一键导出"""
    if not os.path.isfile(SNAPSHOT_QUICK):
        return 1, "", "快照脚本不存在: %s" % SNAPSHOT_QUICK
    try:
        r = subprocess.run(["python3", SNAPSHOT_QUICK], capture_output=True,
                           text=True, timeout=60)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return 1, "", str(e)


def try_user_profile():
    """用户自定义 profile 试用向导（/tmp 沙箱，零破坏）
    引导用户创建自己的电源方案而不动生产配置"""
    if not os.path.isfile(TRY_PROFILE_SCRIPT):
        return 1, "", "试用脚本不存在: %s" % TRY_PROFILE_SCRIPT
    try:
        r = subprocess.run(["bash", TRY_PROFILE_SCRIPT], capture_output=True,
                           text=True, timeout=60)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return 1, "", str(e)


def profile_inheritance(name=None):
    """profile 继承链可视化（B5：显示每个场景从基类继承了哪些值）
    name=None 时输出全部 profile 的继承树"""
    try:
        from src.core.profile_debug import dump_inheritance_tree
        return 0, dump_inheritance_tree(name), ""
    except ImportError:
        return 1, "", "profile_debug 模块不可用"
    except Exception as e:
        return 1, "", str(e)


def safeguard_verdict():
    """2026-09-08 审计 A1: 降压安全网状态（此前仅终端可查 verdict 文件）
    返回 (verdict, detail) 或 None（无记录）"""
    try:
        vf = Path("/var/lib/uv-safeguard/verdict")
        if not vf.exists():
            # verdict 由 uv-safeguard 开机时写入；不存在=从未跑过（异常）
            return ("UNKNOWN", "verdict 文件不存在")
        state, detail = "", ""
        for line in vf.read_text(encoding="utf-8").splitlines():
            if line.startswith("verdict="):
                state = line.split("=", 1)[1].strip()
            elif line.startswith("detail="):
                detail = line.split("=", 1)[1].strip()
        if not state:
            return None
        return (state, detail or state)
    except Exception:
        return None


def conflict_recheck():
    """运行期冲突复查（B6：安装新电源工具后一键复查互斥冲突 + double-sudo）"""
    out_parts = []
    rc_all = 0
    conf = _find_script("scripts", "check_conflicts.py")
    if os.path.isfile(conf):
        try:
            r = subprocess.run(["python3", conf], capture_output=True, text=True, timeout=30)
            out_parts.append("━━ 互斥工具冲突检测 ━━")
            out_parts.append(r.stdout.strip() or "（无输出）")
            rc_all = rc_all or r.returncode
        except Exception as e:
            out_parts.append(f"互斥检测失败: {e}")
            rc_all = 1
    ds = _find_script("scripts", "check_double_sudo.py")
    if os.path.isfile(ds):
        try:
            app_dir = os.path.dirname(os.path.abspath(__file__))
            r = subprocess.run(["python3", ds, app_dir], capture_output=True, text=True, timeout=30)
            out_parts.append("\n━━ double-sudo 静态检测 ━━")
            out_parts.append(r.stdout.strip() or "（无输出）")
            rc_all = rc_all or r.returncode
        except Exception as e:
            out_parts.append(f"double-sudo 检测失败: {e}")
            rc_all = 1
    if not out_parts:
        return 1, "", "检测脚本不存在"
    return rc_all, "\n".join(out_parts), ""


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


# ---------- 6. 一键安装/修复（重装、换机后 GUI 内直接完成）----------
INSTALL_SCRIPT = _alias_script(os.path.join(BASE, "install.sh"), "sc-install.sh")


def install_system():
    """一键安装/修复系统配置（等价 sudo bash install.sh，弹窗提权）。
    配置: sudo 免密白名单 + RAPL 读权限 + acdc/cpu-power-limit 服务 + 桌面启动器 + 自启动。
    返回 (rc, out, err)。"""
    if not os.path.isfile(INSTALL_SCRIPT):
        return 1, "", "install.sh 不存在: %s" % INSTALL_SCRIPT
    # 直接执行脚本本体: _run 内部 sudo -n 匹配的是别名路径(sudoers 白名单)，
    # 不能再套 bash —— 否则 sudo 记录的是 /usr/bin/bash，白名单永远不匹配
    return _run([INSTALL_SCRIPT], timeout=180)