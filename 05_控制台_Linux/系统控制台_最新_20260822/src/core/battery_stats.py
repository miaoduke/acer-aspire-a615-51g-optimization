#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Battery Usage Stats - 电池使用统计
1. 离电运行时间统计：AC/DC 切换跟踪、会话记录、日/周/总时长、续航效果评估
2. 电池循环计数：本机固件不报告 cycle_count，用充电量累积法自算等效循环
"""

import os
import json
import time
import threading
from pathlib import Path
from datetime import datetime, date
from typing import Dict, List, Optional

BAT = "/sys/class/power_supply/BAT1"
AC = "/sys/class/power_supply/ACAD/online"
DATA_FILE = Path(os.path.expanduser("~/桌面/系统控制台/data/battery_usage.json"))


def _read(path, default=None):
    try:
        return open(path).read().strip()
    except Exception:
        return default


class BatteryUsageTracker:
    """电池使用统计器（单例，tick 驱动）"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._data = self._load()
        # 运行时状态
        self._last_ac: Optional[bool] = None      # 上次供电状态
        self._session_start: float = 0             # 当前离电会话开始时间
        self._session_start_cap: int = 0           # 会话开始电量%
        self._session_min_cap: int = 100           # 会话最低电量
        self._session_charge_start: float = 0      # 充电起点电荷量 µAh
        self._last_charge_now: Optional[int] = None  # 上次电荷量（充电累积用）
        self._last_tick: float = 0
    
    # ---------- 持久化 ----------
    def _load(self) -> Dict:
        try:
            with open(DATA_FILE) as f:
                return json.load(f)
        except Exception:
            return {
                "total_dc_sec": 0,          # 总离电秒数
                "daily_dc": {},             # {YYYYMMDD: 秒} 每日离电时长
                "sessions": [],             # 最近离电会话 [{start,end,start_cap,end_cap,avg_w}]
                "equiv_cycles": 0.0,        # 等效循环数（累计充电量/设计容量）
                "total_charge_uah": 0,      # 累计充入电荷量 µAh
                "full_cycles": 0,           # 完整循环检测计数（粗略）
                "design_uwh": 0,            # 设计容量快照
                "first_seen": datetime.now().strftime("%Y-%m-%d"),
            }
    
    def _save(self):
        """节流保存（最多每 60s 写一次盘）"""
        now = time.time()
        if now - getattr(self, "_last_save", 0) < 60:
            return
        self._last_save = now
        try:
            DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = str(DATA_FILE) + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, DATA_FILE)
        except Exception:
            pass
    
    def force_save(self):
        self._last_save = 0
        self._save()
    
    # ---------- 核心更新（tick 驱动，每 2-5s 调一次）----------
    def update(self) -> Dict:
        """
        由控制台主循环调用。返回当前统计快照供 UI 显示。
        """
        now = time.time()
        ac_raw = _read(AC)
        is_ac = (ac_raw == "1")
        cap = int(_read(BAT + "/capacity", "0") or 0)
        status = _read(BAT + "/status", "Unknown")
        
        # 电荷量（µAh）用于循环累积
        charge_now = None
        try:
            charge_now = int(_read(BAT + "/charge_now", "0") or 0)
        except ValueError:
            pass
        
        design_uwh = 0
        try:
            design_uah = int(_read(BAT + "/charge_full_design", "0") or 0)
            volt_uv = int(_read(BAT + "/voltage_now", "0") or 0) if _read(BAT + "/voltage_now") else 11600000
            design_uwh = int(design_uah * volt_uv / 1e6) if design_uah else 0
        except Exception:
            pass
        if design_uwh and not self._data.get("design_uwh"):
            self._data["design_uwh"] = design_uwh
        
        with self._lock:
            # ---- AC/DC 切换检测 ----
            if self._last_ac is None:
                self._last_ac = is_ac
                if not is_ac:
                    self._session_start = now
                    self._session_start_cap = cap
                    self._session_min_cap = cap
            
            elif is_ac != self._last_ac:
                if is_ac:
                    # DC → AC：结束离电会话
                    self._end_session(now, cap)
                else:
                    # AC → DC：开始新会话
                    self._session_start = now
                    self._session_start_cap = cap
                    self._session_min_cap = cap
                self._last_ac = is_ac
            
            # ---- 离电中：累计时长 ----
            if not is_ac and self._session_start:
                dc_delta = now - max(self._last_tick, self._session_start) if self._last_tick else 0
                dc_delta = min(dc_delta, 30)  # 防休眠后大跳变
                if dc_delta > 0:
                    self._data["total_dc_sec"] += dc_delta
                    day = datetime.now().strftime("%Y%m%d")
                    self._data["daily_dc"][day] = self._data["daily_dc"].get(day, 0) + dc_delta
                self._session_min_cap = min(self._session_min_cap, cap)
            
            self._last_tick = now
            
            # ---- 循环计数（充电量累积法）----
            # 仅在 Charging 状态且电荷量有效时累积增量
            if status == "Charging" and charge_now is not None:
                last = self._last_charge_now
                if last is not None and charge_now > last:
                    delta_uah = charge_now - last
                    # 过滤异常跳变（满充重置等）
                    if 0 < delta_uah < 500000:
                        self._data["total_charge_uah"] += delta_uah
                        if self._data.get("design_uwh"):
                            design_uah_approx = self._data["design_uwh"] * 1e6 // max(1, volt_uv_safe())
                            if design_uah_approx > 0:
                                self._data["equiv_cycles"] = round(
                                    self._data["total_charge_uah"] / design_uah_approx, 2)
                self._last_charge_now = charge_now
            elif status in ("Discharging", "Full"):
                self._last_charge_now = charge_now  # 更新基线不累积
            
            self._save()
        
        return self.snapshot(is_ac, cap, status)
    
    def _end_session(self, end_time: float, end_cap: int):
        """结束离电会话并记录"""
        if not self._session_start:
            return
        duration = end_time - self._session_start
        if duration < 60:  # <1 分钟的闪断不记录
            return
        session = {
            "date": datetime.fromtimestamp(self._session_start).strftime("%m-%d %H:%M"),
            "duration_min": round(duration / 60),
            "start_cap": self._session_start_cap,
            "end_cap": end_cap,
            "used_pct": max(0, self._session_start_cap - self._session_min_cap),
        }
        sessions = self._data.setdefault("sessions", [])
        sessions.append(session)
        # 只保留最近 20 条
        self._data["sessions"] = sessions[-20:]
        self.force_save()
    
    # ---------- 快照（UI 显示）----------
    def snapshot(self, is_ac: bool, cap: int, status: str) -> Dict:
        d = self._data
        today = datetime.now().strftime("%Y%m%d")
        
        # 当前会话时长
        current_session_min = 0
        if not is_ac and self._session_start:
            current_session_min = (time.time() - self._session_start) / 60
        
        # 今日离电
        today_sec = d.get("daily_dc", {}).get(today, 0)
        if not is_ac and self._session_start:
            today_sec += time.time() - self._session_start
        
        # 近 7 天
        week_sec = 0
        for i in range(7):
            day = (date.today().timedelta(days=-i) if hasattr(date.today(), 'timedelta')
                   else datetime.fromtimestamp(time.time() - i * 86400).strftime("%Y%m%d"))
            week_sec += d.get("daily_dc", {}).get(day, 0)
        
        # 平均放电功率（近会话估算续航）
        sessions = d.get("sessions", [])
        
        return {
            "is_ac": is_ac,
            "current_session_min": current_session_min,
            "today_dc_min": today_sec / 60,
            "week_dc_hours": week_sec / 3600,
            "total_dc_hours": d.get("total_dc_sec", 0) / 3600,
            "sessions": list(reversed(sessions[-10:])),  # 最新在前
            "equiv_cycles": d.get("equiv_cycles", 0),
            "total_charge_ah": d.get("total_charge_uah", 0) / 1e6,
            "first_seen": d.get("first_seen", ""),
        }
    
    def format_summary(self, snap: Dict) -> str:
        """格式化摘要文本"""
        lines = []
        if not snap["is_ac"]:
            m = snap["current_session_min"]
            lines.append("本次离电：%s" % fmt_dur(m * 60))
        lines.append("今日离电：%s" % fmt_dur(snap["today_dc_min"] * 60))
        lines.append("近 7 天：%s" % fmt_dur(snap["week_dc_hours"] * 3600))
        lines.append("累计离电：%s" % fmt_dur(snap["total_dc_hours"] * 3600))
        lines.append("等效循环：%.1f 次（自统计 %.1f Ah）" % (
            snap["equiv_cycles"], snap["total_charge_ah"]))
        return "\n".join(lines)


def volt_uv_safe():
    try:
        return int(_read(BAT + "/voltage_now", "11600000") or 11600000)
    except Exception:
        return 11600000


def fmt_dur(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return "%ds" % s
    m, sec = divmod(s, 60)
    if m < 60:
        return "%dm%02ds" % (m, sec)
    h, m = divmod(m, 60)
    return "%dh%02dm" % (h, m)


# 全局单例
_tracker: Optional['BatteryUsageTracker'] = None


def get_tracker() -> BatteryUsageTracker:
    global _tracker
    if _tracker is None:
        _tracker = BatteryUsageTracker()
    return _tracker


# 测试
if __name__ == '__main__':
    t = get_tracker()
    print("=== 连续更新测试 ===")
    for i in range(3):
        snap = t.update()
        print(t.format_summary(snap))
        print("---")
        time.sleep(1)
    print("会话历史:", json.dumps(snap["sessions"], ensure_ascii=False, indent=1))