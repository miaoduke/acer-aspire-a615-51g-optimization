#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notification Module - 桌面通知系统
支持温度告警、限流告警、电池状态变化等桌面通知
"""

import gi
gi.require_version('Notify', '0.7')
gi.require_version('Gtk', '3.0')
from gi.repository import Notify, GLib, GdkPixbuf
from pathlib import Path
from typing import Optional, Dict, Any
import threading
import time
from dataclasses import dataclass
from enum import Enum


class NotificationUrgency(Enum):
    LOW = Notify.Urgency.LOW
    NORMAL = Notify.Urgency.NORMAL
    CRITICAL = Notify.Urgency.CRITICAL


@dataclass
class NotificationConfig:
    """通知配置"""
    enabled: bool = True
    temp_warning_c: float = 80.0      # 温度警告阈值
    temp_critical_c: float = 85.0     # 温度临界阈值
    throttle_notify: bool = True      # 限流时通知
    battery_low_pct: int = 15         # 电池低电量阈值
    battery_critical_pct: int = 5     # 电池临界电量
    cooldown_sec: int = 300           # 同类通知冷却时间(秒)
    show_battery_charging: bool = True
    show_battery_discharging: bool = True


class NotificationManager:
    """统一通知管理器"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self.config = NotificationConfig()
        self._last_notify: Dict[str, float] = {}
        self._initialized_notify = False
        self._init_notify()
    
    def _init_notify(self):
        """初始化 libnotify"""
        try:
            Notify.init("系统控制台")
            self._initialized_notify = True
        except Exception as e:
            print(f"Notify 初始化失败: {e}")
            self._initialized_notify = False
    
    def update_config(self, **kwargs):
        """更新配置"""
        for k, v in kwargs.items():
            if hasattr(self.config, k):
                setattr(self.config, k, v)
    
    def _can_notify(self, key: str) -> bool:
        """检查冷却时间"""
        if not self.config.enabled:
            return False
        now = time.time()
        last = self._last_notify.get(key, 0)
        if now - last < self.config.cooldown_sec:
            return False
        self._last_notify[key] = now
        return True
    
    def _show(self, summary: str, body: str, urgency: NotificationUrgency = NotificationUrgency.NORMAL,
              icon: str = "dialog-information", actions: list = None) -> bool:
        """显示通知"""
        if not self._initialized_notify or not self.config.enabled:
            return False
        
        try:
            n = Notify.Notification.new(summary, body, icon)
            n.set_urgency(urgency.value)
            n.set_timeout(5000)  # 5秒
            
            if actions:
                for action_id, label, callback in actions:
                    n.add_action(action_id, label, callback)
            
            n.show()
            return True
        except Exception as e:
            print(f"通知显示失败: {e}")
            return False
    
    # === 公开 API ===
    
    def notify_temp_warning(self, temp_c: float, sensor_name: str = "CPU"):
        """温度警告通知"""
        key = f"temp_warning_{sensor_name}"
        if not self._can_notify(key):
            return
        
        if temp_c >= self.config.temp_critical_c:
            urgency = NotificationUrgency.CRITICAL
            summary = f"🔴 温度临界: {sensor_name} {temp_c:.0f}°C"
            body = f"已超过临界阈值 {self.config.temp_critical_c}°C，可能触发降频保护"
            urgency_enum = NotificationUrgency.CRITICAL
        elif temp_c >= self.config.temp_warning_c:
            urgency = NotificationUrgency.NORMAL
            summary = f"🟡 温度警告: {sensor_name} {temp_c:.0f}°C"
            body = f"接近警告阈值 {self.config.temp_warning_c}°C，建议检查散热"
            urgency_enum = NotificationUrgency.NORMAL
        else:
            return
        
        self._show(summary, body, urgency_enum, "temperature-high")
    
    def notify_throttle(self, status_summary: str, core_details: str = ""):
        """限流状态变化通知"""
        if not self.config.throttle_notify:
            return
        key = "throttle_change"
        if not self._can_notify(key):
            return
        
        summary = "⚡ CPU 限流状态变化"
        body = f"检测到限流状态: {status_summary}"
        if core_details:
            body += f"\n详情: {core_details}"
        
        self._show(summary, body, NotificationUrgency.NORMAL, "cpu-throttle")
    
    def notify_battery_low(self, percent: int, status: str):
        """电池电量低通知"""
        if not self.config.enabled:
            return
        key = "battery_low"
        if not self._can_notify(key):
            return
        
        if percent <= self.config.battery_critical_pct:
            urgency = NotificationUrgency.CRITICAL
            summary = f"🔴 电池电量临界: {percent}%"
            body = f"电池即将耗尽，请立即连接电源！当前状态: {status}"
            urgency_enum = NotificationUrgency.CRITICAL
        elif percent <= self.config.battery_low_pct:
            urgency = NotificationUrgency.NORMAL
            summary = f"🟡 电池电量低: {percent}%"
            body = f"建议尽快连接电源适配器。当前状态: {status}"
            urgency_enum = NotificationUrgency.NORMAL
        else:
            return
        
        self._show(summary, body, urgency_enum, "battery-caution")
    
    def notify_battery_charging(self, percent: int, charging: bool):
        """充电状态变化通知"""
        if not self.config.enabled:
            return
        if charging and not self.config.show_battery_charging:
            return
        if not charging and not self.config.show_battery_discharging:
            return
        
        key = "battery_charging" if charging else "battery_discharging"
        if not self._can_notify(key):
            return
        
        if charging:
            summary = f"🔋 开始充电: {percent}%"
            body = "电源适配器已连接"
            icon = "battery-charging"
        else:
            summary = f"🔌 断开电源: {percent}%"
            body = "已切换至电池供电模式"
            icon = "battery-discharging"
        
        self._show(summary, body, NotificationUrgency.LOW, icon)
    
    def notify_throttle_detected(self, status_summary: str):
        """检测到限流"""
        self.notify_throttle(status_summary)
    
    def notify_custom(self, summary: str, body: str, urgency: NotificationUrgency = NotificationUrgency.NORMAL,
                      icon: str = "dialog-information"):
        """自定义通知"""
        self._show(summary, body, urgency, icon)


# 全局单例
_notification_manager: Optional['NotificationManager'] = None


def get_notification_manager() -> NotificationManager:
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
    return _notification_manager


# 便捷函数
def notify_temp_warning(temp_c: float, sensor: str = "CPU"):
    get_notification_manager().notify_temp_warning(temp_c, sensor)

def notify_throttle(summary: str, details: str = ""):
    get_notification_manager().notify_throttle(summary)

def notify_battery_low(percent: int, status: str):
    get_notification_manager().notify_battery_low(percent, status)

def notify_battery_charging(percent: int, charging: bool):
    get_notification_manager().notify_battery_charging(percent, charging)


# 测试代码
if __name__ == '__main__':
    import time
    nm = get_notification_manager()
    nm.config.enabled = True
    nm.config.cooldown_sec = 1  # 测试用短冷却
    
    print("测试通知...")
    nm.notify_temp_warning(82.0, "CPU")
    time.sleep(1)
    nm.notify_temp_warning(86.0, "CPU")
    time.sleep(1)
    nm.notify_throttle("检测到热降频", "Core 0,2 热降频中")
    time.sleep(1)
    nm.notify_battery_low(12, "Discharging")
    time.sleep(1)
    nm.notify_battery_charging(45, True)
    
    # 等待通知显示
    import time
    time.sleep(2)
    print("测试完成")