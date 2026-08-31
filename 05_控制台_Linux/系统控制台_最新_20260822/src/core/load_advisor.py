#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Load Advisor - 负载自适应建议
检测持续高负载 + 当前在电池场景 → 通知建议切换到性能场景
"""

import time
import threading
from collections import deque
from typing import Optional, Callable

from src.core.notification import get_notification_manager


class LoadAdvisor:
    """负载自适应建议器
    
    监控 CPU 使用率，当检测到持续高负载且当前在电池场景时，
    发送通知建议用户切换到性能场景（不自动切，避免抢控制权）。
    """
    
    def __init__(self,
                 high_threshold_pct: float = 70.0,   # 高负载阈值 %
                 sustain_sec: int = 30,               # 持续时间秒
                 check_interval: int = 5,             # 检查间隔秒
                 cooldown_min: int = 15):             # 建议冷却分钟
        self.high_threshold = high_threshold_pct
        self.sustain_sec = sustain_sec
        self.check_interval = check_interval
        self.cooldown_sec = cooldown_min * 60
        
        self._history: deque = deque(maxlen=max(1, sustain_sec // check_interval))
        self._last_advice_time: float = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._get_current_scene: Optional[Callable] = None
        self._lock = threading.Lock()
    
    def set_scene_provider(self, provider: Callable[[], str]):
        """设置当前场景查询函数（返回 'ac-*' 或 'bat-*'）"""
        self._get_current_scene = provider
    
    def _is_battery_scene(self) -> bool:
        """当前是否在电池场景"""
        if self._get_current_scene is None:
            return False
        try:
            scene = self._get_current_scene()
            return scene and scene.startswith("bat-")
        except Exception:
            return False
    
    def _read_cpu_usage(self) -> float:
        """读取 CPU 总使用率 %"""
        try:
            with open('/proc/stat') as f:
                line = f.readline()  # cpu 总计行
            parts = line.split()
            # user nice system idle iowait irq softirq steal ...
            vals = [int(x) for x in parts[1:8]]
            total = sum(vals)
            idle = vals[3] + vals[4]  # idle + iowait
            return (total, idle)
        except Exception:
            return (0, 0)
    
    def _check_once(self) -> Optional[str]:
        """单次检查，返回建议消息或 None"""
        with open('/proc/stat') as f:
            line = f.readline()
        parts = line.split()
        vals = [int(x) for x in parts[1:8]]
        total = sum(vals)
        idle = vals[3] + vals[4]
        
        # 与上次比较计算使用率
        if hasattr(self, '_prev_stat'):
            pt, pi = self._prev_stat
            dt = total - pt
            di = idle - pi
            if dt > 0:
                usage = 100.0 * (1 - di / dt)
            else:
                usage = 0
        else:
            usage = 0
        
        self._prev_stat = (total, idle)
        
        # 记录历史
        with self._lock:
            self._history.append(usage)
            
            # 判断：持续高负载 + 电池场景
            if len(self._history) >= self._history.maxlen:
                avg_usage = sum(self._history) / len(self._history)
                all_high = all(u >= self.high_threshold * 0.8 for u in self._history)
                
                if avg_usage >= self.high_threshold and all_high and self._is_battery_scene():
                    now = time.time()
                    if now - self._last_advice_time > self.cooldown_sec:
                        self._last_advice_time = now
                        self._history.clear()  # 清空避免重复建议
                        return (f"检测到持续高负载（平均 {avg_usage:.0f}%），"
                                f"当前在电池场景可能受限。建议切换到性能场景获得更好体验。")
        return None
    
    def start(self):
        """启动后台监控线程"""
        if self._running:
            return
        self._running = True
        
        def loop():
            while self._running:
                try:
                    advice = self._check_once()
                    if advice:
                        nm = get_notification_manager()
                        nm.notify_custom("💡 性能建议", advice, icon="dialog-suggestion")
                except Exception:
                    pass
                time.sleep(self.check_interval)
        
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        self._running = False


# 全局单例
_advisor: Optional['LoadAdvisor'] = None


def get_load_advisor() -> LoadAdvisor:
    global _advisor
    if _advisor is None:
        _advisor = LoadAdvisor()
    return _advisor


def start_load_advisor(scene_provider=None):
    """启动负载建议器"""
    advisor = get_load_advisor()
    if scene_provider:
        advisor.set_scene_provider(scene_provider)
    advisor.start()


# 测试
if __name__ == '__main__':
    import time
    advisor = LoadAdvisor(high_threshold_pct=30, sustain_sec=6, check_interval=2, cooldown_min=0)
    advisor.set_scene_provider(lambda: "bat-save")
    advisor.start()
    print("监控中（阈值 30%，持续 6s）... 按 Ctrl+C 退出")
    try:
        time.sleep(20)
    except KeyboardInterrupt:
        pass
    advisor.stop()