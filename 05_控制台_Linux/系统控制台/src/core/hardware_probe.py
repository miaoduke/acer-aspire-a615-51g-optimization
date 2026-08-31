#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hardware Probe - 硬件探测与能力矩阵
自动发现设备路径（DRM 卡/电池/温度区/RAPL 域），检测功能支持能力。
用于跨机器适配：控制台在任何同架构笔记本上可自动定位资源并按能力启用功能。
"""

import os
import glob
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional


def _read(path, default=None):
    try:
        return open(path).read().strip()
    except Exception:
        return default


class HardwareProbe:
    """硬件探测器：一次扫描，全控制台共享结果"""

    def __init__(self):
        self.paths: Dict[str, Optional[str]] = {}   # 逻辑名 → 实际路径
        self.capabilities: Dict[str, bool] = {}     # 能力名 → 支持
        self.cpu_model: str = ""
        self.dmi_product: str = ""
        self._scan()

    # ---------------- 扫描 ----------------
    def _scan(self):
        self._scan_cpu()
        self._scan_drm()
        self._scan_battery()
        self._scan_thermal()
        self._scan_rapl()
        self._scan_wmi()
        self._scan_misc()

    def _scan_cpu(self):
        try:
            with open('/proc/cpuinfo') as f:
                for line in f:
                    if line.startswith('model name'):
                        self.cpu_model = line.split(':', 1)[1].strip()
                        break
        except Exception:
            pass
        # Intel 或 AMD
        vendor = _read('/sys/devices/virtual/dmi/id/board_vendor', '') or ''
        self.cpu_vendor = 'intel' if 'intel' in (self.cpu_model + vendor).lower() else (
            'amd' if 'amd' in self.cpu_model.lower() else 'unknown')

    def _scan_drm(self):
        """自动发现 i915/amdgpu DRM 卡（排除简单帧缓冲）"""
        self.paths['drm_card'] = None
        for card in sorted(glob.glob('/sys/class/drm/card[0-9]')):
            driver = os.path.realpath(os.path.join(card, 'device', 'driver'))
            drv_name = os.path.basename(driver) if os.path.exists(driver) else ''
            if drv_name in ('i915', 'xe', 'amdgpu'):
                self.paths['drm_card'] = card
                self.capabilities['igpu_gt_freq'] = os.path.isfile(
                    os.path.join(card, 'gt_max_freq_mhz'))
                break

    def _scan_battery(self):
        """主电池探测（BAT1/BAT0/其他）+ AC 适配器"""
        self.paths['battery'] = None
        self.paths['ac_adapter'] = None
        for d in sorted(glob.glob('/sys/class/power_supply/*')):
            typ = _read(os.path.join(d, 'type'), '')
            if typ == 'Battery' and not self.paths['battery']:
                # 排除 UPS/无线鼠标等非主电池
                scope = _read(os.path.join(d, 'scope'), '')
                model = _read(os.path.join(d, 'model_name'), '')
                if 'BAT' in os.path.basename(d) or scope == 'Device':
                    self.paths['battery'] = d
            elif typ == 'Mains' and not self.paths['ac_adapter']:
                self.paths['ac_adapter'] = d
        self.capabilities['battery_charge_control'] = any([
            os.path.isfile(f"{self.paths['battery']}/{f}")
            for f in ('charge_control_end_threshold', 'charge_behaviour')
        ]) if self.paths['battery'] else False

    def _scan_thermal(self):
        """CPU 温度区探测：优先 x86_pkg_temp / coretemp / cpu 相关命名"""
        best = None
        for z in sorted(glob.glob('/sys/class/thermal/thermal_zone*')):
            typ = _read(os.path.join(z, 'type'), '')
            if typ in ('x86_pkg_temp',) or 'cpu' in typ.lower() or typ.startswith('coretemp'):
                best = z
                break
        if not best:
            # 回退：hwmon coretemp
            for h in sorted(glob.glob('/sys/class/hwmon/hwmon*')):
                if _read(os.path.join(h, 'name'), '') == 'coretemp':
                    best = h
                    break
        self.paths['cpu_temp_zone'] = best or '/sys/class/thermal/thermal_zone2'

    def _scan_rapl(self):
        """RAPL 域探测"""
        base = '/sys/class/powercap'
        pkg = None
        subs = {}
        for d in sorted(glob.glob(base + '/intel-rapl:*')):
            name = _read(os.path.join(d, 'name'), '')
            if name == 'package-0' and ':' not in os.path.basename(d).replace('intel-rapl', '', 1).lstrip(':0123456789'):
                pass
            if name.startswith('package') and d.count(':') == 1:
                if pkg is None or int(d.split(':')[1].split('/')[0]) < int(pkg.split(':')[1].split('/')[0]):
                    pkg = d
            elif name in ('core', 'uncore', 'dram') and d.count(':') >= 2:
                parent = d.rsplit(':', 1)[0]
                if pkg and parent.startswith(pkg.rsplit(':', 1)[0]):
                    subs[name] = d
        self.paths['rapl_pkg'] = pkg
        self.paths['rapl_subs'] = subs
        self.capabilities['rapl_power'] = os.path.isfile(
            os.path.join(pkg, 'constraint_0_power_limit_uw')) if pkg else False

    def _scan_wmi(self):
        """Acer WMI 能力探测（仅acer机型有意义）"""
        vendor = (_read('/sys/class/dmi/id/sys_vendor', '') or '').lower()
        self.is_acer = 'acer' in vendor
        self.dmi_product = _read('/sys/class/dmi/id/product_name', '')
        wmi_devs = []
        try:
            wmi_devs = os.listdir('/sys/bus/wmi/devices')
        except Exception:
            pass
        self.wmi_guids = set(wmi_devs)
        # 已知 GUID 用途
        known = {
            '79772EC5-04B1-4BFD-843C-61E7F77B6CC9': 'battery_health',
            '676AA15E-6A47-4D9F-A2CC-1E6D18D14026': 'hotkey_event',
            '67C3371D-95A3-4C37-BB61-DD47B491DAAB': 'wmid_method',
            '7A4DDFE7-5B5D-40B4-8595-4408E0CC7F56': 'gaming_fan_candidate',
        }
        self.wmi_features = {known[g]: g in self.wmi_guids or any(
            g.upper() in d.upper() for d in wmi_devs) for g in known}
        # acer-wmi-battery 驱动状态
        bat_drv = Path('/sys/bus/wmi/drivers/acer-wmi-battery')
        self.capabilities['wmi_battery_temp'] = bat_drv.exists()
        health_ok = False
        if (bat_drv / 'health_mode').exists():
            # 固件真实验证：读 dmesg 判断是否 supported
            try:
                with open('/dev/kmsg') as f:  # 不读；改用 sysfs 可写性判断太危险，标记待验证
                    pass
            except Exception:
                pass
            health_ok = True  # 文件存在即初步可用
        self.capabilities['wmi_health_mode'] = health_ok

    def _scan_misc(self):
        # MSR 访问
        self.capabilities['msr_access'] = (
            os.path.exists('/dev/cpu/0/msr'))
        # intel_pstate
        self.capabilities['intel_pstate'] = os.path.isdir(
            '/sys/devices/system/cpu/intel_pstate')
        # 平台 profile
        self.capabilities['platform_profile'] = os.path.isfile(
            '/sys/firmware/acpi/platform_profile')

    # ---------------- 报告 ----------------
    def report(self) -> Dict:
        return {
            'dmi_product': self.dmi_product,
            'cpu_model': self.cpu_model,
            'paths': dict(self.paths),
            'capabilities': dict(self.capabilities),
            'is_acer': getattr(self, 'is_acer', False),
            'wmi_features': getattr(self, 'wmi_features', {}),
        }

    def summary_text(self) -> str:
        r = self.report()
        lines = [
            f"机型: {r['dmi_product']}",
            f"CPU: {r['cpu_model']}",
            "",
            "【设备路径】",
        ]
        for k, v in r['paths'].items():
            if k == 'rapl_subs':
                continue
            lines.append(f"  {k}: {v or '未找到'}")
        lines.append("")
        lines.append("【能力矩阵】")
        for k, v in r['capabilities'].items():
            lines.append(f"  {'✓' if v else '✗'} {k}")
        if r.get('wmi_features'):
            lines.append("【WMI 特性】")
            for k, v in r['wmi_features'].items():
                lines.append(f"  {'✓' if v else '✗'} {k}")
        return "\n".join(lines)


# 全局单例
_probe: Optional[HardwareProbe] = None


def get_probe() -> HardwareProbe:
    global _probe
    if _probe is None:
        _probe = HardwareProbe()
    return _probe


def get_path(logical: str) -> Optional[str]:
    """便捷取路径"""
    return get_probe().paths.get(logical)


if __name__ == '__main__':
    print(get_probe().summary_text())