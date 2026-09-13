#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""collector.py — 系统控制台数据采集器
原则：直读 /proc 与 /sysfs（无子进程），GPU/PPD 低频子进程，全部 try/except 绝不崩溃。
"""
import os
import time
import subprocess

# ---- 路径常量（本机实测）----
BAT_DIR = "/sys/class/power_supply/BAT1"
AC_FILE = "/sys/class/power_supply/ACAD/online"
RAPL_E = "/sys/class/powercap/intel-rapl:0/energy_uj"
PL1 = "/sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw"
PL2 = "/sys/class/powercap/intel-rapl:0/constraint_1_power_limit_uw"
NO_TURBO = "/sys/devices/system/cpu/intel_pstate/no_turbo"
# 2026-08-31 修复: 原指向 thermal_zone0(ACPI 机壳温度, 实测 27.8°C),
# 而 CPU 封装温度在 thermal_zone2(x86_pkg_temp, 实测 59°C)。
# 后果: ①总览页温度卡显示环境温度而非 CPU 温度
#       ②console.py 的 78°C 高温告警永远不触发(CPU 78°C 时采集值才约 47°C)
# 改为优先取 CPU 封装温度, 回退到 thermal_zone0。
THERMAL_PKG = "/sys/class/thermal/thermal_zone2/temp"   # x86_pkg_temp (CPU 封装)
THERMAL_FALLBACK = "/sys/class/thermal/thermal_zone0/temp"  # acpitz (机壳/环境)
CHARGE_HIST_MAX = 1800  # 充电历史点数（每 2s 采样 ≈ 1 小时）
FLOAT_KEEP = 60        # 满电浮充保留点数（2026-08-31: 防 100% 浮充点无限堆积污染真实曲线）
CHARGE_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return None


def _read_int(path):
    v = _read(path)
    try:
        return int(v)
    except Exception:
        return None


class Collector:
    """采集器：sample() 返回完整快照 dict。差分计算（CPU%/功耗/电池功率）依赖上次采样。"""

    def __init__(self):
        self._prev_stat = None      # {cpuN: total_jiffies}
        self._prev_rapl = None
        self._prev_bat = None       # (monotonic, charge_now, voltage_now)
        self._prev_charge = None    # (monotonic, charge_now) 充电阶段识别
        self._prev_float = False    # 上一采样是否处于满电浮充（2026-08-31 新增）
        self._charge_samples = []   # 电流平滑窗口
        self.charge_hist = []       # 充电曲线 (容量%, 电流mA, 电压V)
        self._charge_file = None
        self._charge_file_day = None
        self._charge_last_flush = 0.0
        self.charge_hist = self._load_charge_hist() or []
        self._tick = 0
        self._gpu_cache = None
        self._gpu_skip = 0
        self._ppd_cache = None
        self._prime_cache = None

    # ---------------- CPU ----------------
    def _cpu_cores(self):
        """返回 [(usage_pct|None, freq_mhz|None), ...] 每线程"""
        out = []
        try:
            with open("/proc/stat") as f:
                lines = f.readlines()
            now, now_idle = {}, {}
            for line in lines:
                p = line.split()
                if len(p) >= 5 and p[0].startswith("cpu") and p[0] != "cpu":
                    vals = [int(x) for x in p[1:]]
                    now[p[0]] = sum(vals)
                    now_idle[p[0]] = vals[3] + vals[4]  # idle + iowait
            n = max((int(k[3:]) for k in now if k[3:].isdigit()), default=-1) + 1
            for i in range(n):
                key = "cpu%d" % i
                pct = None
                if self._prev_stat and key in self._prev_stat:
                    dt = now[key] - self._prev_stat[key]
                    di = now_idle[key] - self._prev_stat_idle[key]
                    if dt > 0:
                        pct = max(0.0, min(100.0, 100.0 * (1.0 - di / dt)))
                freq = _read_int("/sys/devices/system/cpu/cpu%d/cpufreq/scaling_cur_freq" % i)
                if freq:
                    freq = freq // 1000
                out.append((pct, freq))
            self._prev_stat, self._prev_stat_idle = now, now_idle
        except Exception:
            pass
        return out

    # ---------------- 功耗 RAPL ----------------
    def _power_w(self):
        # 2026-09-11 修复+审计修正: 主包域 energy_uj 实际存在(当时误诊为"文件名错误"),
        # 读不到的根因是差分首调无基线 + 部分启动早期节点未就绪。两层机制:
        # sysfs energy_uj 优先, 失败回退 MSR 0x611 能量计数器差分(rdmsr 免密白名单)。
        now = _read_int(RAPL_E)
        if now is None:
            now = self._read_msr_energy()
        if now is None:
            return None
        t = time.monotonic()
        if self._prev_rapl:
            t0, e0 = self._prev_rapl
            dt = t - t0
            if dt > 0.5:  # 至少间隔 0.5s 才计算，避免噪声
                # 计数器回绕保护: 0x611 是 32bit, 满量程约 2^32/1e6 s·W ≈ 4295 J
                if now < e0:
                    e0 -= (1 << 32)  # 回绕, 补偿
                w = (now - e0) / dt / 1e6
                if 0.0 <= w < 100.0:
                    self._prev_rapl = (t, now)
                    return w
        self._prev_rapl = (t, now)
        return None

    def _read_msr_energy(self):
        """MSR_RAPL_POWER_UNIT 换算: 0x611 读数 × 2^-32 J 单位在老平台上不同,
        本机(i5-8250U)为 1/2^32 J 每位 → 直接当 µJ 用会差 1e6 倍。
        实测以 rdmsr 裸值差分即 µJ 口径(与旧 energy_uw 一致), 保持与 _prev_rapl 单位统一。"""
        try:
            import subprocess
            r = subprocess.run(["sudo", "-n", "rdmsr", "0x611"],
                               capture_output=True, text=True, timeout=3)
            if r.returncode == 0 and r.stdout.strip():
                return int(r.stdout.strip(), 16)
        except Exception:
            pass
        return None

    # RAPL 多域功耗分解（内核 7.0 新增：core/uncore/dram 子域）
    RAPL_SUBS = [("core", "intel-rapl:0:0"), ("uncore", "intel-rapl:0:1"), ("dram", "intel-rapl:0:2")]

    def _power_decompose(self):
        """返回 {域: 功耗W} 差分计算（package/core/uncore/dram）。低频：每 3 tick 采样。"""
        if self._tick % 3 != 1:
            return getattr(self, "_pd_cache", None)
        res = {}
        t = time.monotonic()
        for name, dom in self.RAPL_SUBS:
            e = _read_int("/sys/class/powercap/%s/energy_uj" % dom)
            if e is None:
                continue
            prev = getattr(self, "_pd_prev_%s" % name, None)
            if prev is not None:
                dt = t - self._pd_prev_t
                if dt > 1.0:
                    w = (e - prev) / dt / 1e6
                    if 0.0 <= w < 60.0:
                        res[name] = w
            setattr(self, "_pd_prev_%s" % name, e)
        self._pd_prev_t = t
        self._pd_cache = res
        return res

    def _persist_charge(self, cap, cur_ma, vol_v):
        """充电历史持久化：按天追加到数据盘 TSV（重启后可恢复）。
        时间驱动：每 60s 落盘一次（采样频率 1-5s 不等，避免频繁写 ntfs）。"""
        try:
            day = time.strftime("%Y%m%d")
            if self._charge_file_day != day:
                self._charge_file_day = day
                self._charge_file = open(
                    os.path.join(CHARGE_DATA_DIR, "charge_curve_%s.tsv" % day), "a")
            now = time.monotonic()
            if now - self._charge_last_flush >= 60:
                self._charge_last_flush = now
                self._charge_file.write("%s\t%d\t%s\t%d\t%d\t%d\n" % (
                    time.strftime("%H:%M:%S"), cap, "Charging",
                    int(cur_ma * 1000), int(vol_v * 1e6), 0))
                self._charge_file.flush()
        except (OSError, ValueError):
            pass

    def _load_charge_hist(self):
        """启动时恢复当天充电历史（数据盘文件）。"""
        try:
            day = time.strftime("%Y%m%d")
            p = os.path.join(CHARGE_DATA_DIR, "charge_curve_%s.tsv" % day)
            if not os.path.exists(p):
                return []
            hist = []
            with open(p) as f:
                for line in f:
                    parts = line.strip().split("\t")
                    if len(parts) >= 5:
                        hist.append((int(parts[1]), int(parts[3]) / 1000.0,
                                     int(parts[4]) / 1e6))
            return hist[-CHARGE_HIST_MAX:]
        except (OSError, ValueError, IndexError):
            return []

    # ---------------- 电池 ----------------
    def _battery(self):
        cap = _read_int(BAT_DIR + "/capacity")
        status = _read(BAT_DIR + "/status")
        full = _read_int(BAT_DIR + "/charge_full")
        design = _read_int(BAT_DIR + "/charge_full_design")
        health = (full / design * 100.0) if (full and design) else None
        # 充电中 charge_full 会虚高漂移（实测 2625 vs 基线 2618）→ 标注可靠性
        health_reliable = status != "Charging"
        # 充电历史（内存，供曲线）：每次采样附加 (容量%, 电流mA, 电压V)
        cur_ma = (_read_int(BAT_DIR + "/current_now") or 0) / 1000
        vol_v = (_read_int(BAT_DIR + "/voltage_now") or 0) / 1e6
        if cap is not None and (status in ("Charging", "Full")):
            # 2026-08-31 修复: 满电浮充数据污染真实充电曲线。
            # 原逻辑只在 Full 且 last<95 时清空, 而"从满电开始充电"的浮充点(全 100%)
            # 会无限堆积(实测 31 点全 100%), 污染下一周期的真实曲线。
            # 新逻辑:
            #   ① 真实充电(Charging 且 <100%) → 若之前是浮充态则清空, 开新周期
            #   ② 满电(100%) 点只保留最近 FLOAT_KEEP 个(浮充是"稳态"无曲线价值)
            #   ③ 99% 是正常充电尾声, 正常追加(不算浮充)
            is_float = (cap >= 100) and status in ("Charging", "Full")
            if status == "Charging" and cap < 100:
                # 真实充电点: 若前一刻是浮充/满电, 视为新周期开始
                if self.charge_hist and (self.charge_hist[-1][0] >= 100 or self._prev_float):
                    self.charge_hist.clear()
                    self._charge_file_day = None  # 新周期 → 新文件
                self._prev_float = False
                self.charge_hist.append((cap, cur_ma, vol_v))
            elif is_float:
                # 满电浮充: 限长保留最近 FLOAT_KEEP 个, 防无限堆积
                self._prev_float = True
                self.charge_hist.append((cap, cur_ma, vol_v))
                if len(self.charge_hist) > FLOAT_KEEP:
                    del self.charge_hist[0]
            self._persist_charge(cap, cur_ma, vol_v)
        # 功率：charge_now(µAh) × voltage_now(µV) 差分
        power = None
        cn = _read_int(BAT_DIR + "/charge_now")
        vn = _read_int(BAT_DIR + "/voltage_now")
        if cn is not None and vn:
            t = time.monotonic()
            if self._prev_bat:
                t0, c0, v0 = self._prev_bat
                dt = t - t0
                if dt > 2.0:
                    uwh = (cn - c0) * (vn / 1e6)  # µAh * V = µWh
                    p = uwh / dt / 1e6 * 3600      # W
                    if 0.1 < abs(p) < 30:          # 差分过小/异常视为噪声
                        power = abs(p)
            self._prev_bat = (t, cn, vn)
        return {"capacity": cap, "status": status, "health": health, "power_w": power,
                "temp_c": self._bat_temp_c(),
                "float_min": self._float_minutes(),
                "phase": self._charge_phase(cap, status, cn, vn),
                "health_reliable": health_reliable,
                "charge_hist": list(self.charge_hist),
                "model": self._bat_model(),
                "thermal": self._thermal_zones(),
                "health_trend": self._health_trend()}

    BAT_TEMP_SYSFS = "/sys/bus/wmi/drivers/acer-wmi-battery/temperature"
    BT_INTERVAL = 60  # 秒——SMI 排查期降频读取（每秒 SMI 查询曾触发死机）

    def _bat_temp_c(self):
        """真实电池温度（°C）：acer-wmi-battery 模块（WMBE method 19 查询）。
        模块未加载时返回 None（不显示）。60s 节流：每次读取经 WMI→SMI→EC，降频降低固件风险。"""
        now = time.monotonic()
        if (now - getattr(self, "_bt_last", 0)) < self.BT_INTERVAL:
            return getattr(self, "_bt_cache", None)
        try:
            with open(self.BAT_TEMP_SYSFS) as f:
                v = int(f.read().strip()) / 1000.0
            self._bt_last = now
            self._bt_cache = v
            return v
        except (OSError, ValueError):
            return None

    FLOAT_LOG = "/var/lib/battery-care/float_minutes"

    def _float_minutes(self):
        """今日累计浮充分钟数（battery-care 维护）。"""
        v = _read_int(self.FLOAT_LOG)
        return v if v is not None else None

    HEALTH_LOG = "/var/lib/battery-care/health_log.tsv"

    def _thermal_zones(self):
        """ACPI 温度区（非 EC 直读，纯 sysfs）：acpitz x2（机壳/EC 温度）+ x86_pkg_temp（CPU）。"""
        out = {}
        for z in ("thermal_zone0", "thermal_zone1", "thermal_zone2"):
            t = _read_int("/sys/class/thermal/%s/temp" % z)
            out[z] = (t / 1000.0) if t is not None else None
        return out

    def _bat_model(self):
        """电池型号/厂商（sysfs，无需特权）。model_name 是 hex 字符串 → 解码 ASCII。"""
        m = _read(BAT_DIR + "/model_name")
        v = _read(BAT_DIR + "/manufacturer")
        if m:
            try:
                dec = bytes.fromhex(m.removeprefix("0x")).decode("ascii", "replace")
                if dec.isprintable():
                    m = dec
            except ValueError:
                pass
        if not m:
            return None
        return "%s %s" % (v, m) if v else m

    def _health_trend(self):
        """健康协议采样记录（date temp_c charge_full health_pct），返回最近采样 + 全部列表。"""
        try:
            rows = []
            with open(self.HEALTH_LOG) as f:
                for line in f.readlines()[1:]:
                    parts = line.strip().split("\t")
                    if len(parts) >= 4:
                        rows.append({"date": parts[0], "temp": parts[1],
                                     "full": int(parts[2]), "health": float(parts[3])})
            return {"latest": rows[-1] if rows else None, "history": rows}
        except (OSError, ValueError, IndexError):
            return {"latest": None, "history": []}

    def _charge_phase(self, cap, status, cn, vn):
        """充电阶段识别（学术标准: CV 终止电流 ≤0.05C ≈ 160mA，本机 3220mAh → 300mA 阈值）:
        - Charging + 电流 <300mA + 电压顶格(≥16.9V) → CV（恒压，高损伤区）
        - Charging + 其他 → CC（恒流）
        - Full → 已充满
        - 其他 → None"""
        if status == "Full":
            return "full"
        if status != "Charging":
            return None
        if cn is None or vn is None:
            return "cc"
        # 电荷增量差分 → 电流 mA（µAh/s × 3.6），3 点平滑抗分辨率噪声
        t = time.monotonic()
        if self._prev_charge and t - self._prev_charge[0] > 2.0:
            dt = t - self._prev_charge[0]
            cur_mA = (cn - self._prev_charge[1]) / dt * 3.6
            self._charge_samples.append(cur_mA)
            if len(self._charge_samples) > 3:
                self._charge_samples.pop(0)
        self._prev_charge = (t, cn)
        if len(self._charge_samples) < 3:
            return "cc"
        cur = sum(self._charge_samples) / len(self._charge_samples)
        if cur < 300 and vn >= 16900000:
            return "cv"
        return "cc"

    # ---------------- GPU（低频子进程）----------------
    def _gpu(self):
        if self._gpu_skip > 0:
            self._gpu_skip -= 1
            return self._gpu_cache
        self._gpu_skip = 2  # 每 3 次采样一次
        try:
            # P1-C: 同时检查当前 prime-select 模式
            mode_out = subprocess.run(
                ["prime-select", "query"],
                capture_output=True, text=True, timeout=2
            )
            current_mode = mode_out.stdout.strip() if mode_out.returncode == 0 else "unknown"

            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,power.draw,temperature.gpu,memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5)
            if out.returncode == 0:
                fields = [x.strip() for x in out.stdout.strip().split(",")]
                if len(fields) >= 5:
                    def _f(s):
                        try:
                            return float(s)
                        except Exception:
                            return None
                    self._gpu_cache = {
                        "util": _f(fields[0]), "power": _f(fields[1]),
                        "temp": _f(fields[2]), "mem_used": _f(fields[3]),
                        "mem_total": _f(fields[4]),
                        "mode": current_mode,
                    }
                else:
                    self._gpu_cache = None
            else:
                # nvidia-smi 失败（如 intel 模式）
                self._gpu_cache = {
                    "util": None, "power": None, "temp": None,
                    "mem_used": None, "mem_total": None,
                    "mode": current_mode,
                    "status": f"当前 {current_mode} 模式，nvidia-smi 不可用（驱动未运行）",
                }
        except Exception:
            self._gpu_cache = None
        return self._gpu_cache

    # ---------------- 内存 ----------------
    @staticmethod
    def _memory():
        total = used = None
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        total = int(line.split()[1]) // 1024
                    elif line.startswith("MemAvailable:"):
                        used = total - int(line.split()[1]) // 1024
        except Exception:
            pass
        pct = (used / total * 100.0) if (total and used is not None) else None
        return {"total_mb": total, "used_mb": used, "pct": pct}

    # ---------------- 电源状态参数 ----------------
    @staticmethod
    def _power_params():
        pl1 = _read_int(PL1)
        pl2 = _read_int(PL2)
        nt = _read(NO_TURBO)
        epp = _read("/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference")
        gov = _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
        return {
            "pl1_w": (pl1 / 1e6) if pl1 else None,
            "pl2_w": (pl2 / 1e6) if pl2 else None,
            "turbo": (nt == "0") if nt is not None else None,
            "epp": epp, "governor": gov,
        }

    # ---------------- PPD / GPU 模式（低频）----------------
    def _ppd(self):
        self._tick += 1
        if self._tick % 3 == 1:
            try:
                out = subprocess.run(["powerprofilesctl", "get"], capture_output=True,
                                     text=True, timeout=3)
                self._ppd_cache = out.stdout.strip() if out.returncode == 0 else None
            except Exception:
                self._ppd_cache = None
        return self._ppd_cache

    def _prime(self):
        if self._tick % 3 == 1:
            try:
                out = subprocess.run(["prime-select", "query"], capture_output=True,
                                     text=True, timeout=3)
                self._prime_cache = out.stdout.strip() if out.returncode == 0 else None
            except Exception:
                self._prime_cache = None
        return self._prime_cache

    # ---------------- 生态状态（2026-08-20 落地项）----------------
    ECO_PATHS = {
        "zswap": "/sys/module/zswap/parameters/enabled",
        "zswap_shrinker": "/sys/module/zswap/parameters/shrinker_enabled",
        "hwp_boost": "/sys/devices/system/cpu/intel_pstate/hwp_dynamic_boost",
        "brightness": "/sys/class/backlight/intel_backlight/brightness",
        "brightness_max": "/sys/class/backlight/intel_backlight/max_brightness",
        "mx150": "/sys/bus/pci/devices/0000:01:00.0/power/runtime_status",
        "journald_max": "/etc/systemd/journald.conf",
        "gt_max": "/sys/class/drm/card1/gt_max_freq_mhz",
        "gt_rp0": "/sys/class/drm/card1/gt_RP0_freq_mhz",
    }

    def _ecosystem(self):
        """本会话落地的生态优化项状态（sysfs 直读 + 低频子进程）。"""
        eco = {}
        # sysfs 直读
        for k, path in self.ECO_PATHS.items():
            if k == "journald_max":
                eco[k] = _read(path)
            else:
                eco[k] = _read(path)
        # 内核命令行
        cl = _read("/proc/cmdline") or ""
        m = None
        for w in cl.split():
            if w.startswith("intel_idle.max_cstate="):
                m = w.split("=")[1]
        eco["max_cstate"] = m
        eco["zswap_cmdline"] = "zswap.enabled=1" in cl
        eco["shrinker_cmdline"] = "zswap.shrinker_enabled=1" in cl
        # swap
        eco["swap"] = None
        try:
            for line in open("/proc/swaps"):
                parts = line.split()
                if len(parts) >= 3 and parts[0] == "/swapfile":
                    eco["swap"] = "%.1fG" % (int(parts[2]) / 1048576.0)
        except Exception:
            pass
        # 放电率（current×voltage，power_now 本机为空）
        cur = _read_int(BAT_DIR + "/current_now")
        vol = _read_int(BAT_DIR + "/voltage_now")
        if cur is not None and vol:
            eco["discharge_w"] = cur * vol / 1e12
        else:
            eco["discharge_w"] = None
        # 服务状态（低频）
        if self._tick % 3 == 1:
            svc = {}
            for s in ("acdc-profile", "m3-power-saver", "smartd"):
                try:
                    r = subprocess.run(["systemctl", "is-active", s],
                                       capture_output=True, text=True, timeout=3)
                    svc[s] = r.stdout.strip()
                except Exception:
                    svc[s] = None
            try:
                r = subprocess.run(["systemctl", "is-enabled", "NetworkManager-wait-online"],
                                   capture_output=True, text=True, timeout=3)
                svc["wait-online"] = r.stdout.strip()
            except Exception:
                svc["wait-online"] = None
            try:
                r = subprocess.run(["systemctl", "is-active", "fwupd"],
                                   capture_output=True, text=True, timeout=3)
                svc["fwupd"] = r.stdout.strip()
            except Exception:
                svc["fwupd"] = None
            try:
                r = subprocess.run(["systemctl", "is-active", "undervolt"],
                                   capture_output=True, text=True, timeout=3)
                svc["undervolt"] = r.stdout.strip()
            except Exception:
                svc["undervolt"] = None
            try:
                r = subprocess.run(["systemctl", "cat", "undervolt"],
                                   capture_output=True, text=True, timeout=3)
                for line in r.stdout.splitlines():
                    if line.startswith("ExecStart="):
                        svc["undervolt_cfg"] = line.split("=", 1)[1]
                        break
            except Exception:
                pass
            self._svc_cache = svc
        eco["services"] = getattr(self, "_svc_cache", {})
        return eco

    # ---------------- 汇总快照 ----------------
    def sample(self):
        ac_raw = _read_int(AC_FILE)
        # CPU 封装温度优先; 缺失时回退到 thermal_zone0
        temp_raw = _read_int(THERMAL_PKG)
        if temp_raw is None:
            temp_raw = _read_int(THERMAL_FALLBACK)
        return {
            "ts": time.time(),
            "ac": (ac_raw == 1) if ac_raw is not None else None,
            "temp": (temp_raw / 1000.0) if temp_raw else None,
            "power_w": self._power_w(),
            "cpu": self._cpu_cores(),
            "mem": self._memory(),
            "bat": self._battery(),
            "gpu": self._gpu(),
            "params": self._power_params(),
            "ppd": self._ppd(),
            "prime": self._prime(),
            "eco": self._ecosystem(),
            "power_dc": self._power_decompose(),
        }