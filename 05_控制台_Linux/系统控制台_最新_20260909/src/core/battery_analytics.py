#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Battery Analytics - 电池使用情况的科学统计分析
基于锂电化学原理对使用数据进行多维分析，输出指标 + 分级评价 + 科学说明。
分析结论随数据积累动态更新（数据不足时明确标注置信度）。

科学依据来源:
- Battery University (BU-808): DoD 与循环寿命关系
- IOP 2025 大样本研究: 限充 80% 循环寿命翻倍 (6000+ vs 3000 EFC)
- Arrhenius 方程: 温度每升 10°C 电化学反应速率约翻倍
- CV 恒压阶段高电压应力是主要老化因素之一
"""

import json
import os
import time
import statistics
from pathlib import Path
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple
from src.core.i18n import T

HOME = Path.home()
BASE = HOME / "桌面" / "系统控制台"  # ⚠ 路径组成部分不可 T()（en 翻译成 Desktop 会断链）
USAGE_FILE = BASE / "data" / "battery_usage.json"
HEALTH_LOG = Path("/var/lib/battery-care/health_log.tsv")
FLOAT_LOG = Path("/var/lib/battery-care/float_minutes")
PERF_DIR = BASE / "data" / "perf"

BAT = "/sys/class/power_supply/BAT1"


def _read(path, default=None):
    try:
        return open(path).read().strip()
    except Exception:
        return default





class BatteryAnalytics:
    """电池科学分析引擎"""

    def __init__(self):
        pass

    # ---------- 数据加载 ----------
    def _load_usage(self) -> Dict:
        try:
            with open(USAGE_FILE) as f:
                return json.load(f)
        except Exception:
            return {}

    def _load_health_log(self) -> List[Dict]:
        rows = []
        try:
            with open(HEALTH_LOG) as f:
                lines = f.readlines()[1:]
            for line in lines:
                parts = line.strip().split("\t")
                if len(parts) >= 4:
                    rows.append({"date": parts[0], "temp": parts[1],
                                 "full": int(parts[2]), "health": float(parts[3])})
        except Exception:
            pass
        return rows

    def _load_battery_tsv(self, days: int = 7) -> List[Dict]:
        """读取最近 N 天的电池 TSV 数据"""
        rows = []
        if not PERF_DIR.exists():
            return rows
        cutoff = time.time() - days * 86400
        for f in sorted(PERF_DIR.glob("batt_*.tsv"), reverse=True):
            try:
                with open(f) as fh:
                    lines = fh.readlines()[1:]
                for line in reversed(lines):
                    parts = line.strip().split("\t")
                    if len(parts) >= 13:
                        try:
                            ts = float(parts[0])
                            if ts < cutoff:
                                continue
                            rows.append({
                                "ts": ts,
                                "cap": int(float(parts[2])),
                                "status": parts[3],
                                "power_w": float(parts[4]),
                                "current_ma": int(float(parts[5])),
                                "temp_c": float(parts[12]),
                            })
                        except (ValueError, IndexError):
                            continue
            except Exception:
                continue
        return rows

    def _load_float_minutes(self) -> Optional[int]:
        try:
            return int(_read(FLOAT_LOG, "0") or 0)
        except ValueError:
            return None

    # ---------- 分析引擎 ----------
    def analyze(self) -> Dict:
        """
        执行全部分析。返回:
        {
          "items": [ {title, value, grade, grade_color, explanation, science}, ... ],
          "data_quality": {...},
          "summary": str,
        }
        """
        usage = self._load_usage()
        health_rows = self._load_health_log()
        batt_rows = self._load_battery_tsv(7)
        sessions = usage.get("sessions", [])

        items = []
        items.append(self._analyze_efc_rate(usage))
        items.append(self._analyze_dod(sessions))
        items.append(self._analyze_endurance_efficiency(sessions, usage))
        items.append(self._analyze_charge_behavior(batt_rows))
        items.append(self._analyze_temperature(batt_rows))
        items.append(self._analyze_health_trend(health_rows))
        items.append(self._analyze_float(self._load_float_minutes()))

        # 数据质量评估
        days_used = max(1, len(usage.get("daily_dc", {})))
        data_quality = {
            "usage_days": days_used,
            "sessions": len(sessions),
            "health_samples": len(health_rows),
            "tsv_points_7d": len(batt_rows),
            "sufficient": len(sessions) >= 3 and days_used >= 3,
        }

        summary = self._build_summary(items, data_quality)
        return {"items": items, "data_quality": data_quality, "summary": summary}

    # ---------- 各维度分析 ----------

    def _grade(self, value_good: bool) -> Tuple[str, str]:
        return (T("✓ 良好"), "#2e7d32") if value_good else (T("⚠ 需注意"), "#e65100")

    def _analyze_efc_rate(self, usage: Dict) -> Dict:
        """1. 等效满循环 (EFC) 速率 → 寿命预测"""
        equiv = usage.get("equiv_cycles", 0.0)
        days = len(usage.get("daily_dc", {})) or 1
        # 用首次记录日期更准确
        first = usage.get("first_seen")
        if first:
            try:
                d0 = datetime.strptime(first, "%Y-%m-%d")
                days = max(days, (datetime.now() - d0).days or 1)
            except Exception:
                pass

        efc_per_day = equiv / days
        # 科学依据: 笔记本典型 0.3-1.0 EFC/天; 80%限充下 3000-6000 EFC 到 80% 健康
        if efc_per_day <= 0.05:
            value = T("{:.3f} 次/天（累计 {:.1f} 次）").format(efc_per_day, equiv)
            good, note = True, T("数据积累中")
        else:
            value = T("{:.2f} 次/天（累计 {:.1f} 次）").format(efc_per_day, equiv)
            good = efc_per_day < 0.8

        # 寿命外推（假设当前健康度 ~80%，每天 efc 次）
        years_to_70pct = ""
        if efc_per_day > 0.02:
            # 保守: 从当前状态再走 1200 EFC 到 70%（80%限充下偏保守估计）
            remain_efc = max(0, 1200 - equiv)
            days_left = remain_efc / efc_per_day
            years_to_70pct = T("按此速率约 {:.1f} 年后健康度降至 ~70%").format(days_left/365)

        science = (T("等效满循环(EFC)=累计充入电荷÷设计容量。锂电循环寿命与 DoD 强相关:"
                   "100% DoD 约 300-500 次循环衰减至 80%，50% DoD 约 1200-1500 次，"
                   "25% 浅循环可达 2000-5000 次(BU-808)。限充 80% 可使循环寿命翻倍"
                   "(IOP 2025: 6000+ vs 3000 EFC)。笔记本典型使用强度为 0.3-1.0 EFC/天。"))

        return {
            "title": T("循环速率与寿命预测"),
            "value": value + (f"\n{years_to_70pct}" if years_to_70pct else ""),
            "grade": T("✓ 良好") if good else T("⚠ 偏高"),
            "grade_color": "#2e7d32" if good else "#e65100",
            "explanation": (T("循环速率低 → 电池老化慢。当前速率处于正常范围。")
                            if good else
                            T("循环速率偏高（>0.8 EFC/天），建议减少深放电、多用插电。")),
            "science": science,
            "confidence": T("高") if days >= 7 and equiv > 1 else T("低（数据积累中，≥7 天且 ≥1 循环后有参考价值）"),
        }

    def _analyze_dod(self, sessions: List[Dict]) -> Dict:
        """2. 放电深度 (DoD) 分析"""
        if not sessions:
            return self._insufficient(T("放电深度 (DoD)"), T("完成 1 次以上离电会话后可用"),
                                      T("DoD=单次放电的电量百分比。浅放电显著延长循环寿命:"))
        # 会话记录无 used_pct 字段时从 start/end 电量计算
        dods = []
        for s in sessions:
            used = s.get("used_pct")
            if used is None:
                used = max(0, s.get("start_cap", 0) - s.get("end_cap", 0))
            dods.append(used)
        avg_dod = statistics.mean(dods)
        deep_count = sum(1 for d in dods if d >= 60)

        good = avg_dod < 60
        value = T("平均 {:.0f}%（{} 次会话，深放 {} 次）").format(avg_dod, len(dods), deep_count)

        science = (T("DoD 与循环寿命近似幂律关系(BU-808 实测): 100% DoD≈300-500 次、"
                   "60% DoD≈800-1200 次、40% DoD≈1500-2500 次、20% DoD≈4000+ 次"
                   "(衰减至初始容量 80%)。避免深放(<20%)是延长寿命最有效的习惯之一;"
                   "锂电无记忆效应，随用随充无害。"))

        return {
            "title": T("放电深度 (DoD)"),
            "value": value,
            "grade": T("✓ 良好") if good else T("⚠ 偏深"),
            "grade_color": "#2e7d32" if good else "#e65100",
            "explanation": (T("平均放电深度适中，浅充放习惯有利寿命。")
                            if good else
                            T("平均放电较深。建议电量低于 25-30% 即充电，避免用到 15% 以下。")),
            "science": science,
            "confidence": T("中") if len(sessions) >= 3 else T("低（≥3 次会话后更准）"),
        }

    def _analyze_endurance_efficiency(self, sessions: List[Dict], usage: Dict) -> Dict:
        """3. 续航效率趋势（同电量使用时长变化 → 健康衰减的体感指标）"""
        valid = [s for s in sessions
                 if s.get("duration_min", 0) >= 20 and
                 max(0, s.get("start_cap", 0) - s.get("end_cap", 0)) >= 10]
        if len(valid) < 2:
            return self._insufficient(
                T("续航效率趋势"), T("完成 2 次以上有效离电会话（≥20 分钟、耗电 ≥10%）后可用"),
                T("健康衰减的直接体感: 同样 100%→30%,使用时间越来越短。"
                "效率指数 = 会话时长 ÷ 耗电量(%·h),归一化后可观察衰减斜率。"))

        # 效率指数: 分钟 / 耗电百分比 × 100 (即 100% 电量理论可用分钟)
        effs = []
        for s in valid:
            used = max(1, s.get("start_cap", 0) - s.get("end_cap", 0))
            effs.append(s["duration_min"] / used * 100)

        latest = statistics.mean(effs[-2:])
        baseline = statistics.mean(effs[:2])
        change_pct = (latest - baseline) / baseline * 100 if baseline else 0

        full_wh = None
        try:
            full_uah = int(_read(BAT + "/charge_full", "0") or 0)
            volt_v = float(_read(BAT + "/voltage_now", "11600000") or 11600000) / 1e6
            full_wh = full_uah * volt_v / 1e6
        except Exception:
            pass

        value = T("最新 {:.0f} 分钟/100% vs 基线 {:.0f} 分钟/100%").format(latest, baseline)
        if full_wh:
            value += T("\n当前满充 ≈ {:.1f} Wh").format(full_wh)

        trend_txt = ""
        if abs(change_pct) < 8:
            trend_txt = T("稳定")
            good = True
        elif change_pct < -8:
            trend_txt = T("下降 {:.0f}%").format(-change_pct)
            good = False
        else:
            trend_txt = T("提升 {:+.0f}%（负载差异所致）").format(change_pct)
            good = True

        science = (T("续航效率 = 会话时长 ÷ 耗电百分比,即折算 100% 电量的可用时长。"
                   "排除负载差异后,该值持续下降反映内阻增大/容量衰减(健康度下降的体感表现)。"
                   "单次波动受亮度/负载/WiFi 影响大,需多次会话才有统计意义。"))

        return {
            "title": T("续航效率趋势"),
            "value": value + T("\n趋势: {}").format(trend_txt),
            "grade": T("✓ 稳定") if good else T("⚠ 下降"),
            "grade_color": "#2e7d32" if good else "#c62828",
            "explanation": (T("效率稳定,无明显衰减迹象。") if good else
                            T("效率呈下降趋势——可能为健康衰减或近期负载更高,继续观察。")),
            "science": science,
            "confidence": T("中") if len(valid) >= 4 else T("低（会话越多越准）"),
        }

    def _analyze_charge_behavior(self, batt_rows: List[Dict]) -> Dict:
        """4. 充电行为分析（近 7 天 TSV）"""
        charging = [r for r in batt_rows if r["status"] == "Charging"]
        if len(charging) < 10:
            return self._insufficient(
                T("充电行为"), T("插电使用积累更多采样后可用"),
                T("充电行为影响寿命的两个维度: 充电时电池温度、以及是否长期维持高电量(浮充)。"))

        temps = [r["temp_c"] for r in charging if r["temp_c"] > 0]
        caps = [r["cap"] for r in charging]
        avg_temp = statistics.mean(temps) if temps else 0
        high_temp_ratio = sum(1 for t in temps if t >= 40) / len(temps) * 100 if temps else 0
        high_cap_ratio = sum(1 for c in caps if c >= 95) / len(caps) * 100 if caps else 0

        good = avg_temp < 38 and high_temp_ratio < 20
        value = (T("充电均温 {:.1f}°C | ≥40°C 占比 {:.0f}%\n").format(avg_temp, high_temp_ratio)
                 + T("高电量(≥95%)时段占比 {:.0f}%").format(high_cap_ratio))

        science = (T("充电过程本身产热(内阻损耗)+高 SoC 电压应力是两大老化因素:"
                   "充电最佳温度区间 15-35°C;≥40°C 且高 SoC 时负极 SEI 膜生长加速,"
                   "析锂风险上升。长期 100% 满电存放/浮充在 25°C 下约 5 个月健康度跌破 80%。"))

        return {
            "title": T("充电行为（近 7 天）"),
            "value": value,
            "grade": T("✓ 良好") if good else T("⚠ 注意"),
            "grade_color": "#2e7d32" if good else "#e65100",
            "explanation": (T("充电温度与电量区间健康。") if good else
                            T("存在高温充电或长时间满电情况——若常插电使用，"
                            "建议进 Windows 设 80% 限充（如固件支持）。")),
            "science": science,
            "confidence": T("中"),
        }

    def _analyze_temperature(self, batt_rows: List[Dict]) -> Dict:
        """5. 温度暴露分析（近 7 天全部采样）"""
        if len(batt_rows) < 20:
            return self._insufficient(
                T("温度暴露"), T("控制台运行积累更多采样后可用"),
                T("Arrhenius 定律: 温度每升 10°C,电化学副反应速率约提升一倍,"
                "容量衰减相应加速。35°C 长期使用的衰减速度约为 25°C 的 1.5-2 倍。"))

        temps = [r["temp_c"] for r in batt_rows if r["temp_c"] > 0]
        avg = statistics.mean(temps)
        mx = max(temps)
        hot_ratio = sum(1 for t in temps if t >= 40) / len(temps) * 100

        good = avg < 35 and hot_ratio < 10
        value = T("均值 {:.1f}°C | 峰值 {:.0f}°C | ≥40°C 占比 {:.0f}%").format(avg, mx, hot_ratio)

        science = (T("锂电池理想工作温度 15-35°C(BU-808)。温度对老化的影响符合 Arrhenius "
                   "方程,经验上 40°C 以上每持续 1 小时相当于 25°C 下数小时的等效老化。"
                   "高温+高 SoC 是最不利组合(如夏天满电暴晒)。"))

        return {
            "title": T("温度暴露（近 7 天）"),
            "value": value,
            "grade": T("✓ 良好") if good else T("⚠ 偏热"),
            "grade_color": "#2e7d32" if good else "#e65100",
            "explanation": (T("电池温度控制在理想区间。") if good else
                            T("电池环境偏热——检查通风、避免阳光直晒、"
                            "高负载时注意散热口不被遮挡。")),
            "science": science,
            "confidence": T("中"),
        }

    def _analyze_health_trend(self, health_rows: List[Dict]) -> Dict:
        """6. 健康度趋势外推（协议采样线性回归）"""
        if len(health_rows) < 2:
            return self._insufficient(
                T("健康度趋势外推"), T("需 ≥2 次协议采样（放电 40-60% 自动记录，间隔 ≥12h）"),
                T("健康度 = 当前满充容量 ÷ 设计容量。周期性采样做线性回归,"
                "可外推到达 80%(更换建议线)和 70%(体验明显下降线)的时间点。"))

        # 时间轴: 天数
        t0 = datetime.strptime(health_rows[0]["date"].split()[0], "%Y-%m-%d")
        xs, ys = [], []
        for r in health_rows:
            try:
                dt = (datetime.strptime(r["date"].split()[0], "%Y-%m-%d") - t0).days
                xs.append(dt)
                ys.append(r["health"])
            except Exception:
                continue

        n = len(xs)
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        denom = sum((x - mean_x) ** 2 for x in xs)
        slope = (sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom) if denom else 0

        current = ys[-1]
        span_days = xs[-1] - xs[0]

        value = T("当前 {:.1f}% | 斜率 {:+.3f}%/天（{} 次采样，跨 {} 天）").format(current, slope, n, span_days)

        extrapolate = ""
        if slope < -0.005:  # 明显下降
            days_to_80 = (current - 80) / (-slope)
            days_to_70 = (current - 70) / (-slope)
            extrapolate = (T("\n外推: 约 {:.0f} 天后到 80%，{:.0f} 天后到 70%").format(
                days_to_80, days_to_70) if current > 80 else "")
        elif slope >= 0:
            extrapolate = T("\n未见下降趋势（或测量噪声掩盖）")

        good = slope > -0.02  # 每天掉 <0.02% 属于缓慢
        science = (T("健康度采样在放电 40-60% 窗口进行以减少读数噪声。线性回归外推的前提是"
                   "衰减近似匀速——实际为非线性(前期快后期慢),因此外推仅作参考,"
                   "采样点越多越准。行业惯例: 健康度 <80% 视为建议更换,<70% 体验明显受损。"))

        return {
            "title": T("健康度趋势外推"),
            "value": value + extrapolate,
            "grade": T("✓ 缓慢") if good else T("⚠ 偏快"),
            "grade_color": "#2e7d32" if good else "#e65100",
            "explanation": (T("衰减速度缓慢,按当前趋势无需担心。") if good else
                            T("衰减偏快——结合 DoD/温度/循环速率几项找原因。")),
            "science": science,
            "confidence": T("高") if n >= 5 and span_days >= 14 else (T("中") if n >= 3 else T("低")),
        }

    def _analyze_float(self, float_min: Optional[int]) -> Dict:
        """7. 浮充分析"""
        if float_min is None:
            return self._insufficient(
                T("浮充管理"), T("battery-care 服务运行后可用"),
                T("浮充=满电状态下继续插电。高 SoC+持续外接电源使电池长期处于 4.2V/C 高电压应力,"
                "是最伤电池的使用模式之一。"))
        
        hours = float_min / 60
        good = hours < 120  # 今日浮充 <2h
        value = T("今日浮充 {:.1f} 小时").format(hours)
        science = (T("满电(4.2V/cell)持续浮充时,负极 SEI 持续增厚、电解液氧化分解加速。"
                   "BU-808: 25°C 满电存放一年容量约剩 80%;40°C 满电一年仅剩 65%。"
                   "缓解: 插电为主时设 80% 限充,或定期拔电使用至中等电量。"))

        return {
            "title": T("浮充管理（今日）"),
            "value": value,
            "grade": T("✓ 正常") if good else T("⚠ 浮充多"),
            "grade_color": "#2e7d32" if good else "#e65100",
            "explanation": (T("浮充时长可控。") if good else
                            T("今日浮充较长。插电为主的使用建议设置充电上限。")),
            "science": science,
            "confidence": T("高"),
        }

    def _insufficient(self, title: str, need: str, science: str) -> Dict:
        return {
            "title": title,
            "value": T("数据不足 — {}").format(need),
            "grade": T("⏳ 积累中"),
            "grade_color": "#757575",
            "explanation": T("该分析将随数据积累自动启用。"),
            "science": science,
            "confidence": T("数据不足"),
        }

    def _build_summary(self, items: List[Dict], dq: Dict) -> str:
        ok = sum(1 for i in items if i["grade"].startswith(("✓",)))
        warn = sum(1 for i in items if i["grade"].startswith("⚠"))
        pending = sum(1 for i in items if i["grade"].startswith("⏳"))
        if dq.get("sufficient"):
            head = T("综合评价: {} 项良好 / {} 项需注意 / {} 项待数据").format(ok, warn, pending)
        else:
            head = (T("数据积累期（使用 {} 天、{} 次会话）——多数分析将在数据充足后自动给出结论")
                       .format(dq.get('usage_days', 0), dq.get('sessions', 0)))
        return head


# 全局单例
_analytics = None


def get_analytics() -> BatteryAnalytics:
    global _analytics
    if _analytics is None:
        _analytics = BatteryAnalytics()
    return _analytics


def run_analysis() -> Dict:
    return get_analytics().analyze()


if __name__ == '__main__':
    result = run_analysis()
    print(result["summary"])
    print("=" * 60)
    for item in result["items"]:
        print(f"\n【{item['title']}】 {item['grade']}")
        print(T("  数值: {}").format(item['value']))
        print(T("  解读: {}").format(item['explanation']))
        print(T("  科学依据: {}...").format(item['science'][:80]))
        print(T("  置信度: {}").format(item['confidence']))