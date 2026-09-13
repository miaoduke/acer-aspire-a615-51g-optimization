#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSR Reader Module - Safe read-only access to Model Specific Registers
用于读取 CPU 限流状态：热降频、电流墙、功耗墙、PL 限制等
"""

import subprocess
import re
from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum


from src.core.i18n import T


class ThrottleType(Enum):
    """限流类型枚举"""
    NONE = "正常"
    THERMAL = "热降频"
    POWER = "功耗墙"
    CURRENT = "电流墙"
    VR_THERMAL = "VR 热降频"
    VR_CURRENT = "VR 电流墙"
    PL1_LIMIT = "PL1 功耗限制"
    PL2_LIMIT = "PL2 功耗限制"
    BD_PROCHOT = "BD PROCHOT"


@dataclass
class ThrottleStatus:
    """单个 CPU 核心的限流状态"""
    core: int
    active: bool
    types: list[ThrottleType]
    
    def summary(self) -> str:
        if not self.active:
            return "🟢 正常"
        icons = {
            ThrottleType.THERMAL: "🔴",
            ThrottleType.POWER: "🟡",
            ThrottleType.CURRENT: "🟠",
            ThrottleType.VR_THERMAL: "🟣",
            ThrottleType.VR_CURRENT: "🟤",
            ThrottleType.PL1_LIMIT: "🔵",
            ThrottleType.PL2_LIMIT: "🔵",
            ThrottleType.BD_PROCHOT: "🟤",
        }
        return " ".join(icons.get(t, "⚪") for t in self.types)


@dataclass
class SystemThrottleStatus:
    """全系统限流状态汇总"""
    cores: list[ThrottleStatus]
    pl1_active: bool
    pl2_active: bool
    bd_prochot_active: bool
    timestamp: float
    
    @property
    def any_throttling(self) -> bool:
        return any(c.active for c in self.cores) or self.pl1_active or self.pl2_active or self.bd_prochot_active
    
    def summary_text(self) -> str:
        if not self.any_throttling:
            return T("🟢 正常运行")
        
        parts = []
        # 统计核心限流类型
        thermal_count = sum(1 for c in self.cores if ThrottleType.THERMAL in c.types)
        power_count = sum(1 for c in self.cores if ThrottleType.POWER in c.types)
        current_count = sum(1 for c in self.cores if ThrottleType.CURRENT in c.types)
        vr_thermal_count = sum(1 for c in self.cores if ThrottleType.VR_THERMAL in c.types)
        vr_current_count = sum(1 for c in self.cores if ThrottleType.VR_CURRENT in c.types)
        
        if thermal_count:
            parts.append(T("🔴热降频({}核)").format(thermal_count))
        if power_count:
            parts.append(T("🟡功耗墙({}核)").format(power_count))
        if current_count:
            parts.append(T("🟠电流墙({}核)").format(current_count))
        if vr_thermal_count:
            parts.append(T("🟣VR热({}核)").format(vr_thermal_count))
        if vr_current_count:
            parts.append(T("🟤VR电流({}核)").format(vr_current_count))
        if self.pl1_active:
            parts.append(T("🔵PL1限制"))
        if self.pl2_active:
            parts.append(T("🔵PL2限制"))
        if self.bd_prochot_active:
            parts.append("🟤BD PROCHOT")
            
        return " | ".join(parts) if parts else T("⚪ 未知状态")


class MSRReader:
    """安全的只读 MSR 读取器

    ponytail: read_all 走 sudo -n rdmsr -a 单次全核读(免密白名单)。
    简化: 缓存 10s + 连续失败 3 次熔断(带 60s 自动恢复探测)。
    (2026-09-13 upgrade 已执行: CACHE_SEC 60→10, 原密码风暴动因随免密消失;
     熔断从"直到手动重置"改为 60s 半程试探自动恢复)
    ceiling: 限流状态最长滞后 10s；熔断期间时间轴显示旧数据(角标可见,见 dashboard)。
    upgrade: 若需真秒级, 把 GUI tick 内 read_all 旁路缓存; 熔断角标已实装。
    """

    CACHE_SEC = 10
    BREAKER_PROBE_SEC = 60   # 熔断后每 60s 半程试探一次(成功即复位)
    FAIL_BREAKER = 3  # 连续失败 N 次后熔断
    
    # MSR 寄存器定义
    IA32_THERM_STATUS = 0x19C          # 热状态/限流状态
    IA32_POWER_CTL = 0x1FC             # Power Control (BD PROCHOT)
    IA32_PLATFORM_INFO = 0xCE          # 平台信息
    MSR_PKG_POWER_LIMIT = 0x610        # PKG 功耗限制
    MSR_PP0_POWER_LIMIT = 0x638        # PP0 (核心) 功耗限制
    MSR_PP1_POWER_LIMIT = 0x640        # PP1 (非核心) 功耗限制
    MSR_PKG_ENERGY_STATUS = 0x611      # PKG 能量状态
    
    # IA32_THERM_STATUS (0x19C) 位定义
    THERM_STATUS_MASK = 0x1            # bit 0: 热降频状态
    THERM_STATUS_LOG = 0x2             # bit 1: 热降频日志
    POWER_LIMIT_MASK = 0x800           # bit 11: 电流/功耗限制
    CURRENT_LIMIT_MASK = 0x1000        # bit 12: 电流限制
    VR_THERMAL_MASK = 0x2000           # bit 13: VR 热降频
    VR_CURRENT_MASK = 0x4000           # bit 14: VR 电流限制
    PL1_STATUS_MASK = 0x10000          # bit 16: PL1 状态
    PL2_STATUS_MASK = 0x20000          # bit 17: PL2 状态
    BD_PROCHOT_MASK = 0x1              # bit 0: BD PROCHOT (在 0x1FC)
    
    def __init__(self):
        self._check_msr_access()
        self._num_cores = self._get_core_count()
        # 缓存与熔断
        self._cache_ts: float = 0
        self._cache_status: Optional[SystemThrottleStatus] = None
        self._consecutive_fails: int = 0
        self._breaker_open: bool = False
        self._breaker_since: float = 0  # 熔断打开时刻(自动恢复探测用)
    
    def _check_msr_access(self) -> bool:
        """检查 MSR 访问权限"""
        try:
            # 测试读取 IA32_THERM_STATUS
            result = subprocess.run(
                ['sudo', 'rdmsr', '-p', '0', f'0x{self.IA32_THERM_STATUS:X}'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass
        return False
    
    def _get_core_count(self) -> int:
        """获取 CPU 核心数"""
        try:
            with open('/proc/cpuinfo', 'r') as f:
                return sum(1 for line in f if line.startswith('processor'))
        except Exception:
            return 1
    
    def _read_msr(self, core: int, msr: int) -> Optional[int]:
        """读取指定核心的 MSR 寄存器"""
        try:
            result = subprocess.run(
                ['sudo', 'rdmsr', '-p', str(core), f'0x{msr:X}'],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip(), 16)
        except Exception:
            pass
        return None
    
    def read_therm_status(self, core: int) -> Optional[int]:
        """读取热状态寄存器 (IA32_THERM_STATUS 0x19C)"""
        return self._read_msr(core, self.IA32_THERM_STATUS)
    
    def read_power_ctl(self) -> Optional[int]:
        """读取功耗控制寄存器 (IA32_POWER_CTL 0x1FC) - BD PROCHOT"""
        return self._read_msr(0, self.IA32_POWER_CTL)
    
    def read_pkg_power_limit(self) -> Optional[int]:
        """读取 PKG 功耗限制"""
        return self._read_msr(0, self.MSR_PKG_POWER_LIMIT)
    
    def analyze_core_throttle(self, core: int) -> ThrottleStatus:
        """分析单核心限流状态"""
        therm_status = self.read_therm_status(core)
        if therm_status is None:
            return ThrottleStatus(core=core, active=False, types=[])
        
        types = []
        val = therm_status
        
        # bit 0: 热降频状态
        if val & self.THERM_STATUS_MASK:
            types.append(ThrottleType.THERMAL)
        
        # bit 11: 功耗/电流限制
        if val & self.POWER_LIMIT_MASK:
            types.append(ThrottleType.POWER)
        
        # bit 12: 电流限制
        if val & self.CURRENT_LIMIT_MASK:
            types.append(ThrottleType.CURRENT)
        
        # bit 13: VR 热降频
        if val & self.VR_THERMAL_MASK:
            types.append(ThrottleType.VR_THERMAL)
        
        # bit 14: VR 电流限制
        if val & self.VR_CURRENT_MASK:
            types.append(ThrottleType.VR_CURRENT)
        
        # bit 16: PL1 状态
        if val & self.PL1_STATUS_MASK:
            types.append(ThrottleType.PL1_LIMIT)
        
        # bit 17: PL2 状态
        if val & self.PL2_STATUS_MASK:
            types.append(ThrottleType.PL2_LIMIT)
        
        return ThrottleStatus(core=core, active=len(types) > 0, types=types)
    
    def read_all(self) -> SystemThrottleStatus:
        """读取全系统限流状态（10s 缓存 + 失败熔断，熔断带 60s 自动恢复探测）"""
        import time
        now = time.time()

        # 熔断打开：每 BREAKER_PROBE_SEC 半程试探一次，成功即复位（2026-09-13:
        # 免密白名单下失败已不产生密码弹窗，"直到手动重置"的设计随之退役）
        if self._breaker_open:
            if now - self._breaker_since < self.BREAKER_PROBE_SEC:
                if self._cache_status:
                    return self._cache_status
                return SystemThrottleStatus(
                    cores=[ThrottleStatus(core=i, active=False, types=[]) for i in range(self._num_cores)],
                    pl1_active=False, pl2_active=False, bd_prochot_active=False, timestamp=now)
            # 探测窗口到：清计数落回正常路径试读一次（失败会重新熔断并重置计时）
            self._consecutive_fails = 0
            self._breaker_open = False
        
        # 缓存有效：直接返回
        if now - self._cache_ts < self.CACHE_SEC and self._cache_status:
            return self._cache_status
        
        # 实际读取（一次 sudo 批量读所有核心）
        try:
            # rdmsr -a 单次读所有核心（输出按核序，一行一核）
            # 旧写法 sudo bash -c 'rdmsr; rdmsr...' 在 sudoers 白名单下永远不匹配
            # （sudo 记录的是 /usr/bin/bash）→ 认证风暴；-a 直读免密通过
            r = subprocess.run(["sudo", "-n", "rdmsr", "-a",
                                f"0x{self.IA32_THERM_STATUS:X}"],
                               capture_output=True, text=True, timeout=10)
            
            if r.returncode != 0 or "密码" in (r.stderr or "") or "password" in (r.stderr or "").lower():
                self._consecutive_fails += 1
                if self._consecutive_fails >= self.FAIL_BREAKER:
                    self._breaker_open = True  # 熔断：停止后续调用
                    self._breaker_since = now   # 记录打开时刻, 60s 后自动试探恢复
                if self._cache_status:
                    return self._cache_status
                return SystemThrottleStatus(
                    cores=[ThrottleStatus(core=i, active=False, types=[]) for i in range(self._num_cores)],
                    pl1_active=False, pl2_active=False, bd_prochot_active=False, timestamp=now)
            
            self._consecutive_fails = 0
            
            # 解析批量输出
            values = [int(line.strip(), 16) for line in r.stdout.strip().splitlines()
                      if line.strip()]
            cores = []
            for i in range(self._num_cores):
                val = values[i] if i < len(values) else 0
                types = []
                if val & self.THERM_STATUS_MASK:
                    types.append(ThrottleType.THERMAL)
                if val & self.POWER_LIMIT_MASK:
                    types.append(ThrottleType.POWER)
                if val & self.CURRENT_LIMIT_MASK:
                    types.append(ThrottleType.CURRENT)
                if val & self.VR_THERMAL_MASK:
                    types.append(ThrottleType.VR_THERMAL)
                if val & self.VR_CURRENT_MASK:
                    types.append(ThrottleType.VR_CURRENT)
                if val & self.PL1_STATUS_MASK:
                    types.append(ThrottleType.PL1_LIMIT)
                if val & self.PL2_STATUS_MASK:
                    types.append(ThrottleType.PL2_LIMIT)
                cores.append(ThrottleStatus(core=i, active=len(types) > 0, types=types))
            
            # PL / BD PROCHOT（同一次 sudo 会话内追加读取）
            pkg = self._read_msr(0, self.MSR_PKG_POWER_LIMIT) or 0
            pctl = self._read_msr(0, self.IA32_POWER_CTL) or 0
            
            status = SystemThrottleStatus(
                cores=cores,
                pl1_active=bool(pkg & 0x1),
                pl2_active=bool(pkg & 0x10000),
                bd_prochot_active=bool(pctl & 0x1),
                timestamp=now)
            
            self._cache_ts = now
            self._cache_status = status
            return status
            
        except Exception:
            self._consecutive_fails += 1
            if self._consecutive_fails >= self.FAIL_BREAKER:
                self._breaker_open = True
                self._breaker_since = time.time()  # 与主路径同步: 记录打开时刻供探测复位
            if self._cache_status:
                return self._cache_status
            return SystemThrottleStatus(
                cores=[ThrottleStatus(core=i, active=False, types=[]) for i in range(self._num_cores)],
                pl1_active=False, pl2_active=False, bd_prochot_active=False, timestamp=now)
    
    def get_package_power_limit(self) -> Dict[str, float]:
        """读取 PKG 功耗限制详情（瓦特）"""
        pkg_limit = self.read_pkg_power_limit()
        if pkg_limit is None:
            return {}
        
        # PL1: bit 0-14 (功率), bit 16-30 (时间窗口)
        # 简化版：仅提取功率值
        pl1_watts = (pkg_limit & 0x7FFF) * 0.125  # 0.125W per unit
        pl2_watts = ((pkg_limit >> 16) & 0x7FFF) * 0.125
        
        return {
            'pl1_watts': pl1_watts,
            'pl2_watts': pl2_watts,
            'pl1_enabled': bool(pkg_limit & 0x1),
            'pl2_enabled': bool(pkg_limit & 0x10000),
        }


# 全局单例
_msr_reader: Optional[MSRReader] = None


def get_msr_reader() -> MSRReader:
    global _msr_reader
    if _msr_reader is None:
        _msr_reader = MSRReader()
    return _msr_reader


def get_throttle_status() -> SystemThrottleStatus:
    """获取当前限流状态（供 GUI 调用）"""
    return get_msr_reader().read_all()


def is_breaker_open() -> bool:
    """MSR 读取熔断是否处于打开状态（供 GUI 角标，2026-09-13 upgrade 实装）"""
    return get_msr_reader()._breaker_open


def get_power_limits() -> Dict[str, float]:
    """获取功耗限制（瓦特）"""
    return get_msr_reader().get_package_power_limit()


# 测试代码
if __name__ == '__main__':
    import time
    print("=== MSR Reader 测试 ===")
    reader = get_msr_reader()
    status = reader.read_all()
    print(f"系统限流状态: {status.summary_text()}")
    print(f"任意限流: {status.any_throttling}")
    for c in status.cores:
        if c.active:
            print(f"  Core {c.core}: {c.summary()}")
    print(f"PL1: {status.pl1_active}, PL2: {status.pl2_active}, BD_PROCHOT: {status.bd_prochot_active}")
    print(f"功耗限制: {reader.get_package_power_limit()}")