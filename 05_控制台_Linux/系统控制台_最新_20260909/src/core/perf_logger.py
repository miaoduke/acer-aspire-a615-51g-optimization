#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Performance Logger Module - 性能数据记录与回看
支持：CPU 频率/温度/功耗/限流状态、电池充放电曲线、系统负载历史
"""

import os
import time
import threading
import csv
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Iterator
from dataclasses import dataclass, asdict
from collections import deque
import threading


@dataclass
class PerfSample:
    """单次性能采样点"""
    timestamp: float          # Unix 时间戳
    datetime_str: str         # 可读时间
    # CPU
    cpu_freq_max: float       # 最大频率 MHz
    cpu_freq_avg: float       # 平均频率 MHz
    cpu_temp: float           # CPU 温度 °C
    cpu_usage_pct: float      # CPU 总使用率 %
    # 功耗
    pkg_power_w: float        # 整机功耗 W
    core_power_w: float       # 核心域功耗 W
    uncore_power_w: float     # 非核心域功耗 W
    dram_power_w: float       # 内存域功耗 W
    # 限流状态
    throttle_thermal: int     # 热降频核心数
    throttle_power: int       # 功耗墙核心数
    throttle_current: int     # 电流墙核心数
    throttle_vr_thermal: int  # VR 热降频
    throttle_vr_current: int  # VR 电流限制
    pl1_active: bool          # PL1 限制
    pl2_active: bool          # PL2 限制
    bd_prochot: bool          # BD PROCHOT
    # GPU
    gpu_util: float
    gpu_temp: float
    gpu_power: float
    # 内存
    mem_used_mb: int
    mem_total_mb: int
    mem_pct: float
    # 网络/磁盘
    net_rx_kbps: float
    net_tx_kbps: float
    disk_read_kbps: float
    disk_write_kbps: float


@dataclass
class BatterySample:
    """电池采样点"""
    timestamp: float
    datetime_str: str
    capacity_pct: int
    status: str               # Charging/Discharging/Full/Unknown
    power_w: float            # 放电/充电功率 W
    current_ma: int           # 电流 mA
    voltage_mv: int           # 电压 mV
    charge_full_uwh: int      # 当前满充容量 uWh
    charge_full_design_uwh: int  # 设计容量 uWh
    health_pct: float         # 健康度 %
    cycle_count: int          # 循环次数
    phase: str                # cc/cv/full/unknown
    temp_c: float             # 电池温度 °C


class PerfDataManager:
    """性能数据管理器 - 负责采样、落盘、查询"""
    
    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = os.path.expanduser("~/.local/share/系统控制台/data/perf")
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 内存缓存 (最近 N 个采样点)
        self._perf_buffer: deque = deque(maxlen=300)  # 约 10 分钟 @ 2s 间隔
        self._battery_buffer: deque = deque(maxlen=300)
        
        # 文件锁
        self._file_lock = threading.Lock()
        
        # 当前日期文件
        self._perf_file: Optional[str] = None
        self._battery_file: Optional[str] = None
        self._current_date: str = ""
        
        # 后台写入线程
        self._write_thread: Optional[threading.Thread] = None
        self._write_queue: deque = deque()
        self._write_lock = threading.Lock()
        self._stop_write = False
        self._start_writer()
    
    def _get_date_file(self, prefix: str) -> Path:
        """获取当天的数据文件路径"""
        date_str = datetime.now().strftime("%Y%m%d")
        return self.data_dir / f"{prefix}_{date_str}.tsv"
    
    def _ensure_files(self):
        """确保当天文件存在，写入表头"""
        date_str = datetime.now().strftime("%Y%m%d")
        if date_str != self._current_date:
            self._current_date = date_str
            self._perf_file = self.data_dir / f"perf_{date_str}.tsv"
            self._battery_file = self.data_dir / f"batt_{date_str}.tsv"
            
            # 写入表头
            for fpath, header in [
                (self._perf_file, self._perf_header()),
                (self._battery_file, self._battery_header()),
            ]:
                if not fpath.exists():
                    with open(fpath, 'w', newline='') as f:
                        f.write(header + '\n')
    
    def _perf_header(self) -> str:
        return "\t".join([
            "timestamp", "datetime", "cpu_freq_max", "cpu_freq_avg", "cpu_temp",
            "cpu_usage", "pkg_w", "core_w", "uncore_w", "dram_w",
            "th_thermal", "th_power", "th_current", "th_vr_th", "th_vr_cur",
            "pl1", "pl2", "bd_prochot",
            "gpu_util", "gpu_temp", "gpu_power",
            "mem_used", "mem_total", "mem_pct",
            "net_rx", "net_tx", "disk_read", "disk_write"
        ])
    
    def _battery_header(self) -> str:
        return "\t".join([
            "timestamp", "datetime", "capacity_pct", "status", "power_w",
            "current_ma", "voltage_mv", "charge_full_uwh", "charge_full_design_uwh",
            "health_pct", "cycle_count", "phase", "temp_c"
        ])
    
    def _start_writer(self):
        """启动后台写入线程"""
        self._write_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._write_thread.start()
    
    def _writer_loop(self):
        """后台写入循环：批量写入减少 IO"""
        while not self._stop_write:
            time.sleep(5)  # 每 5 秒刷一次
            self.flush()
    
    def stop(self):
        """停止写入线程"""
        self._stop_write = True
        if self._write_thread:
            self._write_thread.join(timeout=2)
        self.flush()
    
    def record_perf(self, sample: PerfSample):
        """记录性能采样"""
        self._perf_buffer.append(sample)
        # 立即加入写入队列（不阻塞采样线程）
        with self._write_lock:
            self._write_queue.append(('perf', sample))
    
    def record_battery(self, sample: BatterySample):
        """记录电池采样"""
        self._battery_buffer.append(sample)
        with self._write_lock:
            self._write_queue.append(('battery', sample))
    
    def flush(self):
        """强制刷新缓存到磁盘"""
        self._ensure_files()
        
        # 写入性能数据
        with self._write_lock:
            perf_items = [(t, s) for t, s in self._write_queue if t == 'perf']
            batt_items = [(t, s) for t, s in self._write_queue if t == 'battery']
            # 清空已处理项
            self._write_queue = deque([item for item in self._write_queue if item[0] not in ('perf', 'battery')])
        
        if perf_items:
            self._write_perf_batch(perf_items)
        if batt_items:
            self._write_battery_batch(batt_items)
    
    def _write_perf_batch(self, items: List[tuple]):
        if not items:
            return
        try:
            with open(self._perf_file, 'a', newline='') as f:
                writer = csv.writer(f, delimiter='\t')
                for _, sample in items:
                    writer.writerow([
                        sample.timestamp, sample.datetime_str,
                        sample.cpu_freq_max, sample.cpu_freq_avg, sample.cpu_temp,
                        sample.cpu_usage_pct,
                        sample.pkg_power_w, sample.core_power_w, sample.uncore_power_w, sample.dram_power_w,
                        sample.throttle_thermal, sample.throttle_power, sample.throttle_current,
                        sample.throttle_vr_thermal, sample.throttle_vr_current,
                        sample.pl1_active, sample.pl2_active, sample.bd_prochot,
                        sample.gpu_util, sample.gpu_temp, sample.gpu_power,
                        sample.mem_used_mb, sample.mem_total_mb, sample.mem_pct,
                        sample.net_rx_kbps, sample.net_tx_kbps,
                        sample.disk_read_kbps, sample.disk_write_kbps
                    ])
        except Exception as e:
            print(f"写入性能数据失败: {e}")
    
    def _write_battery_batch(self, items: List[tuple]):
        if not items:
            return
        try:
            with open(self._battery_file, 'a', newline='') as f:
                writer = csv.writer(f, delimiter='\t')
                for _, sample in items:
                    writer.writerow([
                        sample.timestamp, sample.datetime_str,
                        sample.capacity_pct, sample.status, sample.power_w,
                        sample.current_ma, sample.voltage_mv,
                        sample.charge_full_uwh, sample.charge_full_design_uwh,
                        sample.health_pct, sample.cycle_count, sample.phase,
                        sample.temp_c
                    ])
        except Exception as e:
            print(f"写入电池数据失败: {e}")
    
    # === 查询接口 ===
    
    def get_perf_history(self, hours: float = 1) -> List[Dict]:
        """获取最近 N 小时的性能历史"""
        cutoff = time.time() - hours * 3600
        self._ensure_files()
        
        results = []
        # 先从内存缓存读
        for sample in reversed(self._perf_buffer):
            if sample.timestamp >= cutoff:
                results.append(asdict(sample))
            else:
                break
        
        # 如果内存不够，从文件读取
        if len(results) < 100 and self._perf_file.exists():
            try:
                with open(self._perf_file, 'r') as f:
                    reader = csv.DictReader(f, delimiter='\t')
                    for row in reversed(list(reader)):
                        ts = float(row['timestamp'])
                        if ts >= cutoff:
                            # 类型转换（2026-09-01 修复: bool 列写成了 'False'/'True' 字符串,
                            # int() 转换失败被吞 → 残留 str → 后续 max()/排序崩溃
                            # "<' not supported between str and float"）
                            for k in row:
                                if k == 'datetime':
                                    continue  # 唯一合法 str 列
                                v = row[k]
                                if k == 'timestamp':
                                    row[k] = ts  # 2026-09-11 修复: ts 已是 float,
                                    # 原"跳过不转"让文件路径的行残留 str timestamp,
                                    # time.localtime()/sorted() 在 str vs float 上崩溃
                                elif v in ('True', 'False'):
                                    # bool 字符串显式处理
                                    row[k] = 1 if v == 'True' else 0
                                else:
                                    try:
                                        row[k] = float(v) if '.' in v else int(v)
                                    except Exception:
                                        row[k] = 0.0  # 转换失败给默认 0，绝不残留 str
                            results.append(row)
                        else:
                            break
            except Exception:
                pass
        
        return sorted(results, key=lambda x: x['timestamp'])
    
    def get_battery_history(self, hours: float = 24) -> List[Dict]:
        """获取电池历史"""
        cutoff = time.time() - hours * 3600
        self._ensure_files()
        
        results = []
        for sample in reversed(self._battery_buffer):
            if sample.timestamp >= cutoff:
                results.append(asdict(sample))
            else:
                break
        
        if len(results) < 100 and self._battery_file.exists():
            try:
                with open(self._battery_file, 'r') as f:
                    reader = csv.DictReader(f, delimiter='\t')
                    for row in reversed(list(reader)):
                        ts = float(row['timestamp'])
                        if ts >= cutoff:
                            for k in row:
                                if k not in ('timestamp', 'datetime', 'status', 'phase'):
                                    v = row[k]
                                    if v in ('True', 'False'):
                                        row[k] = 1 if v == 'True' else 0
                                    else:
                                        try:
                                            row[k] = float(v) if '.' in v else int(v)
                                        except Exception:
                                            row[k] = 0.0
                            results.append(row)
                        else:
                            break
            except Exception:
                pass
        
        return sorted(results, key=lambda x: x['timestamp'])
    
    def get_latest_perf(self) -> Optional[Dict]:
        """获取最新性能样本"""
        if self._perf_buffer:
            return asdict(self._perf_buffer[-1])
        return None
    
    def get_latest_battery(self) -> Optional[Dict]:
        if self._battery_buffer:
            return asdict(self._battery_buffer[-1])
        return None
    
    def get_stats_summary(self, hours: float = 1) -> Dict[str, Any]:
        """获取统计摘要"""
        perf_data = self.get_perf_history(hours)
        if not perf_data:
            return {}
        
        pkg_w = [d['pkg_w'] for d in perf_data if d.get('pkg_w') is not None]
        temp = [d['cpu_temp'] for d in perf_data if d.get('cpu_temp') is not None]
        
        return {
            'duration_hours': hours,
            'samples': len(perf_data),
            'pkg_power': {
                'avg': sum(pkg_w)/len(pkg_w) if pkg_w else 0,
                'max': max(pkg_w) if pkg_w else 0,
                'min': min(pkg_w) if pkg_w else 0,
            },
            'temp': {
                'avg': sum(temp)/len(temp) if temp else 0,
                'max': max(temp) if temp else 0,
                'min': min(temp) if temp else 0,
            },
            'throttle_events': sum(1 for d in perf_data if any([
                d.get('throttle_thermal', 0), d.get('throttle_power', 0),
                d.get('throttle_current', 0)
            ])),
        }
    
    def cleanup_old_files(self, keep_days: int = 7):
        """清理过期数据文件"""
        cutoff = time.time() - keep_days * 86400
        for f in self.data_dir.glob("*.tsv"):
            try:
                mtime = f.stat().st_mtime
                if mtime < cutoff:
                    f.unlink()
            except Exception:
                pass


# 全局单例
_perf_manager: Optional['PerfDataManager'] = None
_manager_lock = threading.Lock()


def get_perf_manager() -> 'PerfDataManager':
    global _perf_manager
    if _perf_manager is None:
        with _manager_lock:
            if _perf_manager is None:
                _perf_manager = PerfDataManager()
    return _perf_manager


def record_perf_sample(sample: PerfSample):
    """便捷记录函数"""
    get_perf_manager().record_perf(sample)


def record_battery_sample(sample: BatterySample):
    get_perf_manager().record_battery(sample)


def get_perf_history(hours: float = 1) -> List[Dict]:
    return get_perf_manager().get_perf_history(hours)


def get_battery_history(hours: float = 24) -> List[Dict]:
    return get_perf_manager().get_battery_history(hours)


def get_perf_stats(hours: float = 1) -> Dict:
    return get_perf_manager().get_stats_summary(hours)


# 测试
if __name__ == '__main__':
    import random
    mgr = PerfDataManager("/tmp/test_perf")
    
    # 模拟记录
    for i in range(10):
        t = time.time()
        sample = PerfSample(
            timestamp=time.time(),
            datetime_str=datetime.now().strftime("%H:%M:%S"),
            cpu_freq_max=3400 + random.randint(-200, 200),
            cpu_freq_avg=3000 + random.randint(-300, 300),
            cpu_temp=55 + random.randint(-5, 10),
            cpu_usage_pct=random.uniform(5, 80),
            pkg_power_w=15 + random.uniform(-3, 10),
            core_power_w=10 + random.uniform(-2, 5),
            uncore_power_w=3 + random.uniform(-1, 2),
            dram_power_w=1 + random.uniform(-0.5, 1),
            throttle_thermal=random.randint(0, 4),
            throttle_power=random.randint(0, 2),
            throttle_current=random.randint(0, 1),
            throttle_vr_thermal=0,
            throttle_vr_current=0,
            pl1_active=True,
            pl2_active=False,
            bd_prochot=False,
            gpu_util=random.uniform(0, 50),
            gpu_temp=50 + random.randint(-5, 15),
            gpu_power=random.uniform(0, 15),
            mem_used_mb=8000 + random.randint(-500, 500),
            mem_total_mb=11500,
            mem_pct=random.uniform(60, 85),
            net_rx_kbps=random.uniform(0, 500),
            net_tx_kbps=random.uniform(0, 200),
            disk_read_kbps=random.uniform(0, 1000),
            disk_write_kbps=random.uniform(0, 500),
        )
        record_perf_sample(sample)
        time.sleep(0.2)
    
    # 测试读取
    mgr = get_perf_manager()
    time.sleep(1)
    hist = get_perf_history(0.1)
    print(f"记录数: {len(hist)}")
    stats = get_perf_stats(0.1)
    print(f"统计: {stats}")
    
    print("测试完成")