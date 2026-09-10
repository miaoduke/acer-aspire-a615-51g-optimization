#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ui_battery.py — 电池保养页：健康趋势 + 温度历史 + 充电状态 + 保养规则"""
import os
import math
import time

from src.core.i18n import T

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk, cairo

HEALTH_LOG = "/var/lib/battery-care/health_log.tsv"
TEMP_LOG = "/var/lib/battery-care/temp_log.tsv"
FLOAT_LOG = "/var/lib/battery-care/float_log.tsv"
BAT = "/sys/class/power_supply/BAT1"
BAT_TEMP = "/sys/bus/wmi/drivers/acer-wmi-battery/temperature"
THERMAL = "/sys/class/thermal/thermal_zone0/temp"


def _read(path, default=None):
    try:
        return open(path).read().strip()
    except Exception:
        return default


class Curve(Gtk.DrawingArea):
    """Cairo 折线图（数据点 + 线性趋势线）"""

    def __init__(self, height=140):
        super().__init__()
        self.set_size_request(-1, height)
        self._points = []      # [(x_val, y_val, label)]
        self._xlabel = ""
        self._ylabel = ""
        self._trend = False
        self.connect("draw", self._draw)

    def set_data(self, points, xlabel="", ylabel="", trend=False):
        self._points = points
        self._xlabel = xlabel
        self._ylabel = ylabel
        self._trend = trend
        self.queue_draw()

    def _draw(self, _w, cr):
        w = self.get_allocated_width()
        h = self.get_allocated_height()
        if not self._points or w < 60:
            cr.set_source_rgb(0.45, 0.45, 0.45)
            cr.set_font_size(11)
            cr.move_to(8, h / 2)
            cr.show_text(T("暂无数据（等待采样…）"))
            return
        pts = self._points
        xmin = min(p[0] for p in pts)
        xmax = max(p[0] for p in pts)
        ymin = min(p[1] for p in pts)
        ymax = max(p[1] for p in pts)
        if xmax == xmin:
            xmax = xmin + 1
        if ymax == ymin:
            ymax = ymin + 1
        pad = 0.12 * (ymax - ymin) or 1
        ymin -= pad
        ymax += pad
        m = 10
        def X(v):
            return m + (v - xmin) / (xmax - xmin) * (w - 2 * m)
        def Y(v):
            return h - m - (v - ymin) / (ymax - ymin) * (h - 2 * m)
        # 网格
        cr.set_source_rgba(0.9, 0.9, 0.9, 0.5)
        cr.set_line_width(1)
        for i in range(5):
            y = m + i * (h - 2 * m) / 4
            cr.move_to(m, y)
            cr.line_to(w - m, y)
            cr.stroke()
        # 趋势线（最小二乘）
        if self._trend and len(pts) >= 2:
            n = len(pts)
            sx = sum(p[0] for p in pts)
            sy = sum(p[1] for p in pts)
            sxx = sum(p[0] ** 2 for p in pts)
            sxy = sum(p[0] * p[1] for p in pts)
            d = n * sxx - sx * sx
            if abs(d) > 1e-9:
                a = (n * sxy - sx * sy) / d
                b = (sy - a * sx) / n
                cr.set_source_rgba(0.98, 0.35, 0.25, 0.55)
                cr.set_line_width(2)
                cr.set_dash([5, 3])
                cr.move_to(X(xmin), Y(a * xmin + b))
                cr.line_to(X(xmax), Y(a * xmax + b))
                cr.stroke()
                cr.set_dash([])
        # 数据点
        cr.set_source_rgb(0.13, 0.55, 0.95)
        cr.set_line_width(1.5)
        for i, (xv, yv, lab) in enumerate(pts):
            x, y = X(xv), Y(yv)
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()
        cr.set_source_rgb(0.13, 0.55, 0.95)
        for xv, yv, lab in pts:
            x, y = X(xv), Y(yv)
            cr.arc(x, y, 3.2, 0, 2 * math.pi)
            cr.fill()
        # 标签
        cr.set_source_rgb(0.3, 0.3, 0.3)
        cr.set_font_size(10)
        for xv, yv, lab in pts:
            if lab:
                cr.move_to(X(xv) + 6, Y(yv) - 6)
                cr.show_text(lab)
        cr.set_font_size(11)
        cr.move_to(m, h - 3)
        cr.show_text(self._xlabel)
        cr.move_to(2, m)
        cr.save()
        cr.rotate(-math.pi / 2)
        cr.move_to(-h / 2, 12)
        cr.show_text(self._ylabel)
        cr.restore()


class BatteryPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)

        head = Gtk.Label(label=T("电池保养"), xalign=0)
        head.get_style_context().add_class("section-title")
        self.pack_start(head, False, False, 0)

        # ---- 状态卡 ----
        cards = Gtk.Box(spacing=10)
        self.health_card = self._make_card(T("健康度"), "—", "%")
        self.cap_card = self._make_card(T("当前容量"), "—", "")
        self.temp_card = self._make_card(T("电池温度"), "—", "°C")
        self.state_card = self._make_card(T("充电状态"), "—", "")
        for c in (self.health_card, self.cap_card, self.temp_card, self.state_card):
            cards.pack_start(c, True, True, 0)
        self.pack_start(cards, False, False, 0)
        # ---- 温度历史 ----
        tlab = Gtk.Label(label=T("电池温度历史（近 24 小时，每 10 分钟采样）"), xalign=0)
        tlab.get_style_context().add_class("section-title")
        self.pack_start(tlab, False, False, 0)
        self.temp_curve = Curve(150)
        self.pack_start(self.temp_curve, False, False, 0)
        # ---- 充电曲线（自总览页迁移，2026-08-21）----
        chlab = Gtk.Label(label=T("充电曲线（容量% / 电流 mA）"), xalign=0)
        chlab.get_style_context().add_class("section-title")
        self.pack_start(chlab, False, False, 0)
        self.ch_area = Gtk.DrawingArea()
        self.ch_area.set_size_request(-1, 175)
        self.ch_area.set_hexpand(True)
        self.charge_hist = []
        self.ch_area.connect("draw", self._on_draw_charge)
        self.pack_start(self.ch_area, False, False, 0)

        # ---- 浮充统计 ----
        flab = Gtk.Label(label=T("满电浮充时长（近 7 天）"), xalign=0)
        flab.get_style_context().add_class("section-title")
        self.pack_start(flab, False, False, 0)
        self.float_curve = Curve(110)
        self.pack_start(self.float_curve, False, False, 0)
        # ---- 健康趋势 ----
        hlab = Gtk.Label(label=T("健康度趋势（放电 40-60% 窗口采样，≥12h 间隔）"), xalign=0)
        hlab.get_style_context().add_class("section-title")
        self.pack_start(hlab, False, False, 0)
        self.health_curve = Curve(150)
        self.pack_start(self.health_curve, False, False, 0)
        self.health_note = Gtk.Label(label="", xalign=0, wrap=True)
        self.health_note.get_style_context().add_class("dim-text")
        self.pack_start(self.health_note, False, False, 0)
        # ---- 使用统计（离电时长 + 循环计数，2026-08-21）----
        ulab = Gtk.Label(label=T("使用统计（续航监测 + 等效循环）"), xalign=0)
        ulab.get_style_context().add_class("section-title")
        self.pack_start(ulab, False, False, 0)
        
        urow = Gtk.Box(spacing=20)
        # 2026-09-01 修复: 原 _usage_labels 存的是 _make_stat 返回的【字符串】而非 Gtk.Label 对象,
        # 后续 .set_text() 调用报 AttributeError 被吞 → UI 永远显示"—"。
        # 现直接保存创建出的值 label 对象。
        self._usage_labels = {}
        for key, title in [("current", T("本次离电")), ("today", T("今日离电")),
                           ("week", T("近 7 天")), ("total", T("累计离电")),
                           ("cycles", T("等效循环"))]:
            box2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            t = Gtk.Label(label=title)
            t.get_style_context().add_class("card-title")
            v = Gtk.Label(label="—")
            v.get_style_context().add_class("detail-value")
            box2.pack_start(t, False, False, 0)
            box2.pack_start(v, False, False, 0)
            self._usage_labels[key] = v
            urow.pack_start(box2, True, True, 0)
        self.pack_start(urow, False, False, 0)
        
        # 会话历史（最近离电记录）
        self.session_label = Gtk.Label(label="", xalign=0)
        self.session_label.get_style_context().add_class("dim-text")
        self.session_label.set_line_wrap(True)
        self.pack_start(self.session_label, False, False, 0)
        # ---- 科学统计分析（2026-08-21）----
        alab = Gtk.Label(label=T("科学统计分析"), xalign=0)
        alab.get_style_context().add_class("section-title")
        self.pack_start(alab, False, False, 0)
        
        self.analytics_summary = Gtk.Label(label=T("分析加载中..."), xalign=0)
        self.analytics_summary.get_style_context().add_class("dim-text")
        self.pack_start(self.analytics_summary, False, False, 0)
        
        arow = Gtk.Box(spacing=8)
        a_btn = Gtk.Button(label=T("📋 查看完整分析报告"))
        a_btn.set_tooltip_text(T("7 维度科学分析：循环速率/放电深度/续航效率/充电行为/温度/健康度外推/浮充，含科学依据说明"))
        a_btn.connect("clicked", self._open_analytics)
        arow.pack_start(a_btn, False, False, 0)
        self.analytics_refresh_label = Gtk.Label(label="", xalign=0)
        self.analytics_refresh_label.get_style_context().add_class("dim-text")
        arow.pack_start(self.analytics_refresh_label, False, False, 0)
        self.pack_start(arow, False, False, 0)

        # ---- 保养规则（科学依据） ----
        rlab = Gtk.Label(label=T("保养规则（系统自动提醒）"), xalign=0)
        rlab.get_style_context().add_class("section-title")
        self.pack_start(rlab, False, False, 0)
        rules = (
            T('· 充电至 80% 提醒：限充 80% 循环寿命翻倍（6000+ vs 3000 EFC，IOP 2025 大样本）\n· 充电高温提醒：≥45°C 显著加速老化（充电最佳 15-35°C）\n· 浮充提醒：满电长期插电 ≈ 浮充，25°C 满电存放约 5 个月跌破 80% 健康度\n· 低电量提醒：<20% 深放区衰减权重最高（25-0 窗口权重 1.0）\n· 健康采样：放电 40-60% 窗口自动记录，间隔 ≥12h（容量测量需周-月尺度）\n· 校准指引：每 3 个月或 40 次部分循环校准一次（充满→深放→充满，BU-603）；与日常 80% 规则不冲突'))
        rnote = Gtk.Label(label=rules, xalign=0, wrap=True)
        rnote.get_style_context().add_class("dim-text")
        self.pack_start(rnote, False, False, 0)

    def _make_card(self, title, val, unit):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_size_request(110, 64)
        box.get_style_context().add_class("stat-card")
        t = Gtk.Label(label=title)
        t.get_style_context().add_class("stat-title")
        v = Gtk.Label(label=val)
        v.get_style_context().add_class("stat-value")
        box.pack_start(t, False, False, 0)
        box.pack_start(v, True, True, 0)
        box._val = v
        box._unit = unit
        return box

    # ---------------- 刷新 ----------------
    # ---------------- 充电曲线绘制 ----------------
    def _on_draw_charge(self, widget, cr):
        cr.set_source_rgb(0.95, 0.95, 0.95)
        cr.paint()
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        hist = self.charge_hist
        n = len(hist)
        if n < 2:
            cr.set_source_rgb(0.6, 0.6, 0.6)
            cr.set_font_size(11)
            cr.move_to(10, h / 2 + 4)
            cr.show_text(T("插电充电时自动记录（本次充电周期实时曲线）"))
            return
        # 绘图区（留边标注）
        pl, pr, pt, pb = 34, 40, 30, 18
        pw, ph = w - pl - pr, h - pt - pb
        # 网格（20% 一格）
        cr.set_source_rgba(0.75, 0.75, 0.75, 0.5)
        cr.set_line_width(0.6)
        for g in range(0, 101, 20):
            y = pt + ph * (1 - g / 100.0)
            cr.move_to(pl, y)
            cr.line_to(pl + pw, y)
            cr.stroke()
            cr.set_source_rgb(0.5, 0.5, 0.5)
            cr.set_font_size(9)
            cr.move_to(pl - 30, y + 3)
            cr.show_text("%d%%" % g)
            cr.set_source_rgba(0.75, 0.75, 0.75, 0.5)
        # 电流刻度（右轴 0-2000mA，500 一格）
        for g in range(0, 2001, 500):
            y = pt + ph * (1 - g / 2000.0)
            cr.set_source_rgb(0.5, 0.5, 0.5)
            cr.set_font_size(9)
            cr.move_to(pl + pw + 4, y + 3)
            cr.show_text("%dmA" % g)
        cr.set_source_rgba(0.75, 0.75, 0.75, 0.5)
        for g in range(500, 2000, 500):
            y = pt + ph * (1 - g / 2000.0)
            cr.move_to(pl, y)
            cr.line_to(pl + pw, y)
            cr.stroke()
        # 容量% 曲线（蓝，左轴 0-100%）
        cr.set_source_rgba(0.22, 0.55, 0.95, 0.95)
        cr.set_line_width(1.8)
        first = True
        for i, (cap, cur, vol) in enumerate(hist):
            x = pl + i / (n - 1) * pw
            y = pt + ph * (1 - max(0.0, min(100.0, cap)) / 100.0)
            if first:
                cr.move_to(x, y)
                first = False
            else:
                cr.line_to(x, y)
        cr.stroke()
        # 电流曲线（红，右轴 0-2000mA）
        cr.set_source_rgba(0.91, 0.30, 0.24, 0.85)
        cr.set_line_width(1.2)
        first = True
        for i, (cap, cur, vol) in enumerate(hist):
            x = pl + i / (n - 1) * pw
            y = pt + ph * (1 - max(0.0, min(2000.0, cur)) / 2000.0)
            if first:
                cr.move_to(x, y)
                first = False
            else:
                cr.line_to(x, y)
        cr.stroke()
        # CV 转折标注：电流从 >1000mA 首次降到 <700mA
        cv_i = None
        for i in range(1, n):
            if hist[i - 1][1] > 1000 and hist[i][1] < 700:
                cv_i = i
                break
        if cv_i:
            x = pl + cv_i / (n - 1) * pw
            cr.set_source_rgba(0.91, 0.30, 0.24, 0.6)
            cr.set_line_width(1.0)
            cr.set_dash([4, 3], 0)
            cr.move_to(x, pt)
            cr.line_to(x, pt + ph)
            cr.stroke()
            cr.set_dash([], 0)
            cr.set_source_rgb(0.7, 0.2, 0.1)
            cr.set_font_size(9)
            cr.move_to(x + 3, pt + 10)
            cr.show_text("CV %d%%" % hist[cv_i][0])
        # 当前状态标注
        cr.set_source_rgb(0.3, 0.3, 0.3)
        cr.set_font_size(10)
        last = hist[-1]
        cr.move_to(pl, 12)
        cr.show_text(T("%d%% · %.0fmA · %.2fV · %d点") % (last[0], last[1], last[2], n))
        cr.move_to(pl + pw - 70, h - 4)
        cr.show_text(T("蓝=容量 红=电流"))

    def refresh_state(self, d=None, usage_snap=None):
        # 使用统计快照（console 传入）
        if usage_snap is not None:
            self._usage_snap = usage_snap
        self._update_usage_stats()
        # 科学分析摘要（60s 节流）
        now = time.time()
        if now - getattr(self, '_last_analytics_refresh', 0) > 60:
            self._last_analytics_refresh = now
            self._refresh_analytics_summary()
        # 健康度卡（2026-09-08 审计 B1/B2：型号 + 可信标志补显示，采集已有但此前不显示）
        hrows = self._tsv(HEALTH_LOG)
        if len(hrows) >= 2:
            hp = hrows[-1][3]
            self.health_card._val.set_text("%.1f%%" % float(hp))
        elif hrows:
            self.health_card._val.set_text("%.1f%%" % float(hrows[-1][3]))
        # B1: 电池型号 tooltip（sysfs model_name 是 hex 编码，复用 collector 解码逻辑）
        try:
            d0 = d if isinstance(d, dict) else {}
            model = (d0.get("bat") or {}).get("model")
            if not model:
                from collector import Collector
                model = Collector()._bat_model()
            if model:
                self.health_card.set_tooltip_text(T("电池型号: {}").format(model))
        except Exception:
            pass
        # B2: 健康度可信标志（False 时数值仅供参考）
        b = d.get("bat", {}) if isinstance(d, dict) else {}
        if b.get("health_reliable") is False:
            self.health_card._val.set_markup(
                "<span foreground='#e5a50a'>%.1f%%</span>" % float(hp if hrows else 0))
            self.health_card.set_tooltip_text(
                (self.health_card.get_tooltip_text() or "") + "\n" +
                T("⚠ 采样条件不满足（需放电中 40-60%），当前健康度仅供参考"))
        # 容量卡
        full = _read(BAT + "/charge_full", "")
        design = _read(BAT + "/charge_full_design", "")
        if full and design:
            self.cap_card._val.set_text("%.1f / %.1f Wh" % (
                float(full) / 1e6 * 11.4, float(design) / 1e6 * 11.4))
        # 温度卡
        t = _read(BAT_TEMP)
        if t:
            self.temp_card._val.set_text("%.0f" % (int(t) / 1000))
        else:
            tt = _read(THERMAL)
            self.temp_card._val.set_text(T("%.0f (整机)") % (int(tt) / 1000) if tt else "—")
        # 充电状态卡：状态 + 容量 + 充电阶段（CC/CV，自场景页迁移）
        # 统一从 d 快照取值（与 phase 同源，避免 sysfs 实时读与快照错位）
        b = (d or {}).get("bat", {})
        st = b.get("status") or _read(BAT + "/status", "Unknown")
        cap = b.get("capacity")
        cap = f"{cap}%" if cap is not None else (_read(BAT + "/capacity", "—") + "%")
        phase = b.get("phase", "")
        # 阶段标注仅在充电时有意义
        ph_txt = {"cc": T(" · CC恒流"), "cv": T(" · CV恒压(高损伤)")}.get(phase, "") if st == "Charging" else ""
        # 2026-09-08 夹杂清零：状态值（Full/Charging/...）为 sysfs 英文原值，en 界面显示原文即可，
        # zh 界面加映射（否则中文界面出现英文 Full）
        st_disp = {"Charging": T("充电中"), "Full": T("已充满"), "Discharging": T("放电中"),
                   "Unknown": T("未知")}.get(st, st)
        self.state_card._val.set_text(f"{st_disp} {cap}{ph_txt}")
        # 健康趋势曲线（点 + 趋势线 + 温度标注）
        pts = []
        for r in hrows[1:]:
            try:
                pts.append((time.mktime(time.strptime(r[0], "%Y-%m-%d %H:%M:%S")),
                            float(r[3]), "%s°C" % r[1]))
            except Exception:
                continue
        if pts:
            self.health_curve.set_data(pts, T("时间"), T("健康度 %"), trend=True)
            last = hrows[-1]
            if len(hrows) >= 2:
                p0, p1 = float(hrows[-2][3]), float(hrows[-1][3])
                delta = p1 - p0
                self.health_note.set_text(
                    T("最近采样：%s 健康度 %.2f%%（%s°C）｜较上次 %+.2f%% ｜采样 %d 次（容量测量需周-月尺度，趋势仅供参考）")
                    % (last[0], p1, last[1], delta, len(hrows) - 1))
            else:
                self.health_note.set_text(T("最近采样：%s 健康度 %.2f%%（%s°C）｜需 ≥2 次采样才显示趋势") % (last[0], float(last[3]), last[1]))
        else:
            self.health_note.set_text(T("暂无健康采样（自动记录条件：放电中且电量 40-60%，间隔 ≥12 小时）"))
        # 充电曲线数据（collector 的 charge_hist）
        if d is not None:
            b_data = d.get("bat", {})
            self.charge_hist = b_data.get("charge_hist", [])
            self.ch_area.queue_draw()
        
        # 温度曲线（近 24h）
        trows = self._tsv(TEMP_LOG)
        tpts = []
        now = time.time()
        for r in trows[1:]:
            try:
                ts = time.mktime(time.strptime(r[0], "%Y-%m-%d %H:%M:%S"))
            except Exception:
                continue
            if now - ts <= 86400:
                try:
                    tpts.append((ts, float(r[3]), ""))
                except Exception:
                    continue
        if tpts:
            self.temp_curve.set_data(tpts, T("时间（近24h）"), T("温度 °C"))
        else:
            self.temp_curve.set_data([], "", "")
        # 浮充曲线（近 7 天）
        frows = self._tsv(FLOAT_LOG)
        fpts = []
        for r in frows[1:]:
            try:
                ts = time.mktime(time.strptime(r[0], "%Y-%m-%d"))
                if now - ts <= 7 * 86400:
                    fpts.append((ts, float(r[1]), ""))
            except Exception:
                continue
        if fpts:
            self.float_curve.set_data(fpts, T("日期（近7天）"), T("浮充分钟"))
        else:
            self.float_curve.set_data([], "", "")

    # ---------------- 科学统计分析 ----------------
    def _refresh_analytics_summary(self):
        """刷新分析摘要（轻量，每次 refresh 调用）"""
        try:
            from src.core.battery_analytics import run_analysis
            result = run_analysis()
            self.analytics_summary.set_text(result["summary"])
            self.analytics_refresh_label.set_text(
                T("更新于 ") + time.strftime("%H:%M:%S"))
        except Exception as e:
            self.analytics_summary.set_text(T("分析暂不可用: {}").format(e))

    def _open_analytics(self, _btn=None):
        """打开科学统计分析报告对话框"""
        from src.core.battery_analytics import run_analysis
        result = run_analysis()

        dlg = Gtk.Dialog(title=T("电池使用 · 科学统计分析报告"),
                         transient_for=self.get_toplevel(), modal=True)
        dlg.set_default_size(760, 560)
        box = dlg.get_content_area()
        box.set_spacing(6)
        box.set_margin_top(10)
        box.set_margin_start(12)
        box.set_margin_end(12)

        # 摘要
        summary_label = Gtk.Label(xalign=0)
        summary_label.set_markup(f"<b>{result['summary']}</b>")
        summary_label.get_style_context().add_class("detail-value")
        box.pack_start(summary_label, False, False, 0)

        # 数据质量
        dq = result.get("data_quality", {})
        dq_txt = T("数据质量: 使用 {} 天 · {} 次离电会话 · {} 次健康采样 · {} 个近 7 天监测点").format(
            dq.get('usage_days', 0), dq.get('sessions', 0),
            dq.get('health_samples', 0), dq.get('tsv_points_7d', 0))
        dq_label = Gtk.Label(label=dq_txt, xalign=0)
        dq_label.get_style_context().add_class("dim-text")
        box.pack_start(dq_label, False, False, 0)

        # 各维度分析（可展开）
        for item in result["items"]:
            exp = Gtk.Expander()
            header = f"{item['grade']}  {item['title']}"
            exp.set_label(header)
            
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            content.set_margin_top(8)
            content.set_margin_start(12)
            
            # 数值
            val_label = Gtk.Label(label=item["value"], xalign=0)
            val_label.get_style_context().add_class("detail-value")
            val_label.set_line_wrap(True)
            content.pack_start(val_label, False, False, 0)
            
            # 分级着色
            grade_label = Gtk.Label(label=T("评价: {}").format(item['grade']), xalign=0)
            try:
                grade_label.override_color(Gtk.StateType.NORMAL, Gdk.RGBA())
                from gi.repository import Gdk
                rgba = Gdk.RGBA()
                if rgba.parse(item.get("grade_color", "#333333")):
                    grade_label.override_color(Gtk.StateType.NORMAL, rgba)
            except Exception:
                pass
            content.pack_start(grade_label, False, False, 0)
            
            # 解读
            exp2 = Gtk.Expander(label=T("解读"))
            ex_label = Gtk.Label(label=item["explanation"], xalign=0, wrap=True)
            ex_label.set_margin_start(14)
            exp2.add(ex_label)
            content.pack_start(exp2, False, False, 0)
            
            # 科学依据
            exp3 = Gtk.Expander(label=T("📖 科学依据"))
            sc_label = Gtk.Label(label=item["science"], xalign=0, wrap=True)
            sc_label.set_margin_start(14)
            sc_label.get_style_context().add_class("dim-text")
            exp3.add(sc_label)
            content.pack_start(exp3, False, False, 0)
            
            # 置信度
            conf_label = Gtk.Label(label=T("置信度: {}").format(item['confidence']), xalign=0)
            conf_label.get_style_context().add_class("dim-text")
            content.pack_start(conf_label, False, False, 0)
            
            exp.add(content)
            box.pack_start(exp, False, False, 0)

        # 底部说明
        foot = Gtk.Label(
            label=T('分析随数据变动自动更新。数据积累越多（离电会话、健康采样、运行时长），结论越可靠。所有建议基于公开锂电研究（BU-808 / IOP 2025 / Arrhenius 方程）。'),
            xalign=0, wrap=True)
        foot.get_style_context().add_class("dim-text")
        foot.set_margin_top(6)
        box.pack_start(foot, False, False, 0)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        # 把内容装进滚动窗
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for c in list(box.get_children()):
            box.remove(c)
            inner.pack_start(c, False, False, 0)
        sw.add(inner)
        box.pack_start(sw, True, True, 0)

        close_btn = Gtk.Button(label=T("关闭"))
        close_btn.connect("clicked", lambda _b: dlg.destroy())
        box.pack_start(close_btn, False, False, 0)

        dlg.show_all()

    @staticmethod
    def _make_stat(title, val):
        """使用统计的简易元组：(标题, 值)"""
        return (title, val)
    
    def _update_usage_stats(self):
        """更新使用统计显示（由 refresh_state 调用）"""
        try:
            from src.core.battery_stats import get_tracker, fmt_dur
            tracker = get_tracker()
            snap = getattr(self, '_usage_snap', None)
            if snap is None:
                return
            
            lab = self._usage_labels
            if not snap["is_ac"]:
                lab["current"].set_text(fmt_dur(snap["current_session_min"] * 60))
            else:
                lab["current"].set_text("—")
            lab["today"].set_text(fmt_dur(snap["today_dc_min"] * 60))
            lab["week"].set_text(T("%.1f 小时") % snap["week_dc_hours"])
            lab["total"].set_text(T("%.1f 小时") % snap["total_dc_hours"])
            lab["cycles"].set_text(T("%.1f 次") % snap["equiv_cycles"])
            
            # 会话历史
            sessions = snap.get("sessions", [])
            if sessions:
                lines = [T("最近离电记录：")]
                for s in sessions[:5]:
                    # 2026-09-01 修复: 原显示 end_cap(插电瞬间容量, 可能跳升) → 改用 used_pct(真实消耗)
                    lines.append(T("  %s · %d 分钟（%d%% 起，耗 %d%%）") % (
                        s.get("date", "?"), s.get("duration_min", 0),
                        s.get("start_cap", 0), s.get("used_pct", 0)))
                self.session_label.set_text("\n".join(lines))
        except Exception:
            pass

    @staticmethod
    def _make_stat_old(title, val):
        return (title, val)

    @staticmethod
    def _tsv(path):
        try:
            return [line.rstrip("\n").split("\t") for line in open(path)]
        except Exception:
            return []