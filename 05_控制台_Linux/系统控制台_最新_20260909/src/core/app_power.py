#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
App Power Monitor - 按应用(cgroup)功耗排行
通过 /sys/fs/cgroup 遍历 + CPU 时间差分估算每个应用的功耗占比
"""

import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class AppPowerInfo:
    """单个应用的功耗信息"""
    name: str              # 应用名（从 cgroup 路径提取）
    cgroup_path: str       # 完整 cgroup 路径
    cpu_pct: float         # CPU 使用率 %
    power_w: float         # 估算功耗 W
    pct_of_total: float    # 占总功耗百分比
    is_app: bool           # 是否为图形应用(.scope)
    mem_mb: float = 0      # 内存占用 MB（2026-09-11 维度增强: memory.current/1MiB）


class AppPowerMonitor:
    """按应用功耗监控器"""
    
    CGROUP_BASE = "/sys/fs/cgroup"
    
    def __init__(self):
        self._prev_cpu_times: Dict[str, float] = {}
        self._prev_timestamp: float = 0
    
    def _read_cpu_stat(self, cgroup_path: str) -> Optional[float]:
        """读取 cgroup 的 CPU 累计时间（usage_usec）"""
        stat_file = Path(cgroup_path) / "cpu.stat"
        try:
            with open(stat_file) as f:
                for line in f:
                    if line.startswith("usage_usec"):
                        return int(line.split()[1]) / 1_000_000  # µs → s
        except Exception:
            pass
        return None
    
    def _extract_name(self, cgroup_path: str) -> str:
        """从 cgroup 路径提取可读的应用名"""
        rel = cgroup_path.replace(self.CGROUP_BASE, "").strip("/")
        parts = rel.split("/")
        
        # 取最后一段，去掉 .scope/.service 后缀
        name = parts[-1] if parts else "unknown"
        for suffix in [".scope", ".service", ".slice"]:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                break
        
        # app-gnome-xxx.scope 格式处理
        if name.startswith("app-gnome-"):
            # app-gnome-firefox-1234.scope → firefox
            parts2 = name.split("-")
            if len(parts2) >= 3:
                name = "-".join(parts2[2:-1]) if len(parts2) > 3 else parts2[2]
        elif name.startswith("app-"):
            name = name[4:]
        
        # 常见映射
        aliases = {
            "firefox": "Firefox 浏览器",
            "chromium": "Chromium",
            "code": "VS Code",
            "org.gnome.Nautilus": "文件管理器",
            "nautilus": "文件管理器",
            "thunderbird": "Thunderbird",
            "libreoffice": "LibreOffice",
            "vlc": "VLC 播放器",
            "steam": "Steam",
            "gopeed": "Gopeed 下载",
            "cherrystudio": "Cherry Studio",
            "piliplus": "PiliPlus",
            "omniroute": "OmniRoute",
        }
        lower = name.lower()
        for key, val in aliases.items():
            if key in lower:
                return val
        
        return name or "未知"
    
    def _is_graphical_app(self, cgroup_path: str) -> bool:
        """判断是否为图形应用"""
        return ".scope" in cgroup_path and "app-" in cgroup_path

    def _read_mem_mb(self, cgroup_path: str) -> float:
        """cgroup v2 memory.current → MB（2026-09-11 维度增强）"""
        try:
            with open(Path(cgroup_path) / "memory.current") as f:
                return int(f.read().strip()) / 1048576.0
        except (OSError, ValueError):
            return 0.0
    
    def scan(self, package_power_w: float = None) -> List[AppPowerInfo]:
        """
        扫描所有 cgroup 的 CPU 使用并估算功耗
        
        Args:
            package_power_w: 当前整机功耗 W（用于按比例分摊）
        
        Returns:
            按 CPU 使用率降序排列的应用列表
        """
        now = time.monotonic()
        dt = now - self._prev_timestamp if self._prev_timestamp else 0
        
        results = []
        total_cpu_delta = 0.0
        current_times = {}
        
        # 遍历 user.slice 和 system.slice
        for slice_dir in ["user.slice", "system.slice"]:
            base = os.path.join(self.CGROUP_BASE, slice_dir)
            if not os.path.isdir(base):
                continue
            
            for root, dirs, files in os.walk(base):
                # 只看叶子层（有 cpu.stat 的）
                stat_file = os.path.join(root, "cpu.stat")
                if not os.path.isfile(stat_file):
                    continue
                
                cpu_time = self._read_cpu_stat(root)
                if cpu_time is None:
                    continue
                
                rel_path = root
                current_times[rel_path] = cpu_time
                
                # 计算时间差分
                prev = self._prev_cpu_times.get(rel_path)
                if prev is not None and dt > 0:
                    delta = cpu_time - prev
                    if delta < 0:
                        delta = 0  # 计数器重置
                    
                    # 核心数归一化（usage_usec 是所有核心累计的）
                    ncores = os.cpu_count() or 1
                    cpu_pct = (delta / dt / ncores * 100) if dt > 0 else 0
                    cpu_pct = min(100.0, cpu_pct)
                    
                    # 2026-09-11: 只保留终端节点(.scope/.service), 过滤 user/session/app 等
                    # cgroup 中间层级——它们是容器不是进程组, 展示出来全是层级噪音
                    base = os.path.basename(root)
                    if not (base.endswith(".scope") or base.endswith(".service")):
                        continue
                    # 会话容器本身(session-cX.scope 登录会话 / user@UID.service 用户管理器
                    # / init.scope)也是层级, 真实应用在它们的 app.slice/服务在 system.slice 下
                    if base.startswith("session-") or base.startswith("user@") or base == "init.scope":
                        continue

                    if cpu_pct > 0.5:  # 过滤掉几乎无使用的
                        name = self._extract_name(rel_path)
                        results.append(AppPowerInfo(
                            name=name,
                            cgroup_path=rel_path,
                            cpu_pct=cpu_pct,
                            power_w=0,  # 后面计算
                            pct_of_total=0,
                            is_app=self._is_graphical_app(rel_path),
                            mem_mb=self._read_mem_mb(root),
                        ))
                        total_cpu_delta += delta
        
        # 更新缓存
        self._prev_cpu_times = current_times
        self._prev_timestamp = now
        
        # 按比例分摊整机功耗
        if package_power_w and package_power_w > 0:
            # 核心/非核心功耗约占 package 的 80%（其余为常开损耗）
            distributable = package_power_w * 0.8
            for r in results:
                r.power_w = (r.cpu_pct / 100.0) * distributable
                r.pct_of_total = (r.power_w / package_power_w * 100) if package_power_w > 0 else 0
        
        # 按 CPU 使用率降序
        results.sort(key=lambda x: x.cpu_pct, reverse=True)
        return results[:20]  # 前 20 名
    



# 全局单例
_monitor: Optional['AppPowerMonitor'] = None


def get_app_power_monitor() -> AppPowerMonitor:
    global _monitor
    if _monitor is None:
        _monitor = AppPowerMonitor()
    return _monitor


def get_app_power_ranking(package_power_w: float = None) -> List[AppPowerInfo]:
    """获取应用功耗排行（供 GUI 调用）"""
    return get_app_power_monitor().scan(package_power_w)


# 测试
if __name__ == '__main__':
    import time
    mon = get_app_power_monitor()
    
    print("第一次扫描（建立基线）...")
    mon.scan()
    time.sleep(3)
    
    print("第二次扫描（计算差分）...")
    results = mon.scan(package_power_w=15.0)
    
    print(f"\n{'应用':<25} {'CPU%':>7} {'功耗W':>7} {'占比%':>6}")
    print("-" * 50)
    for r in results[:15]:
        print(f"{r.name:<25} {r.cpu_pct:>6.1f}% {r.power_w:>6.2f}W {r.pct_of_total:>5.1f}%")