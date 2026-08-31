#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ui_dashboard.py — 总览页：模块化布局（4 状态卡 + 曲线 + 明细）
布局配置文件: data/layout.json（模块顺序 = 显示顺序，可隐藏/重排/上下移动）
"""
import json
import os
from collections import deque

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango, cairo

HISTORY = 150  # 曲线点数
CPU_COLORS = [
    (0.22, 0.55, 0.95), (0.91, 0.30, 0.24), (0.18, 0.72, 0.40), (0.89, 0.66, 0.12),
    (0.61, 0.35, 0.92), (0.93, 0.46, 0.16), (0.30, 0.74, 0.83), (0.76, 0.33, 0.56),
]

# 模块定义: (key, 显示名, 垂直扩展)
MODULES = [
    ("cards", "状态卡", False),
    ("pwr", "实时功耗", False),
    ("cpu", "CPU 使用率曲线", True),
    ("btemp", "电池温度曲线", True),
    ("details", "实时明细", False),
]
LAYOUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "layout.json")


class DashboardPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)

        # 共享数据
        self.history = deque(maxlen=HISTORY)
        self.charge_hist = []
        self.health_hist = []
        self.details = {}
        self.bt_history = deque(maxlen=HISTORY)

        self._order = self._load_layout()
        self._rebuild()

    # ---------------- 布局配置 ----------------
    def _load_layout(self):
        try:
            with open(LAYOUT_PATH) as f:
                order = json.load(f).get("order", [])
            valid = [m for m in order if m in dict((m[0], m) for m in MODULES)]
            return valid + [m[0] for m in MODULES if m[0] not in valid]
        except Exception:
            return [m[0] for m in MODULES]

    def _save_layout(self):
        try:
            os.makedirs(os.path.dirname(LAYOUT_PATH), exist_ok=True)
            with open(LAYOUT_PATH, "w") as f:
                json.dump({"order": self._order}, f, ensure_ascii=False)
        except Exception:
            pass

    def _rebuild(self):
        """按当前顺序重建页面（所有模块都构建，隐藏的仅不显示——保证 update 引用安全）"""
        for child in self.get_children():
            self.remove(child)
        builders = {
            "cards": self._b_cards, "pwr": self._b_pwr, "cpu": self._b_cpu, "btemp": self._b_btemp,
            "details": self._b_details,
        }
        roots = {key: builders[key]() for key in builders}
        expand = dict((m[0], m[2]) for m in MODULES)
        for key in self._order:
            root = roots.get(key)
            if root is not None:
                self.pack_start(root, expand.get(key, False), True, 0)
        self.show_all()

    def _open_layout_dialog(self, _btn=None):
        """布局设置弹窗：显隐 + 上移/下移"""
        dlg = Gtk.Dialog(title="总览布局设置", transient_for=self.get_toplevel(), modal=True)
        dlg.set_default_size(360, 380)
        box = dlg.get_content_area()
        lab = Gtk.Label(
            label="勾选 = 显示；取消 = 隐藏。↑↓ 调整显示顺序。修改即时生效。",
            xalign=0, wrap=True)
        lab.set_margin_top(8)
        lab.set_margin_start(8)
        lab.set_margin_end(8)
        box.pack_start(lab, False, False, 0)

        rows = {}
        for key in self._order:
            rows[key] = self._layout_row(dlg, box, key)
        # 未显示的模块（补在列表末尾，勾选即显示）
        for key, name, _ in MODULES:
            if key not in rows:
                rows[key] = self._layout_row(dlg, box, key, visible=False)

        dlg.add_button("关闭", Gtk.ResponseType.CLOSE)
        dlg.show_all()
        dlg.run()
        dlg.destroy()

    def _layout_row(self, dlg, box, key, visible=True):
        name = dict((m[0], m[1]) for m in MODULES)[key]
        row = Gtk.Box(spacing=6)
        row.set_margin_start(8)
        row.set_margin_end(8)
        check = Gtk.CheckButton(label=name)
        check.set_active(visible)
        btn_up = Gtk.Button(label="↑")
        btn_dn = Gtk.Button(label="↓")
        btn_up.set_size_request(34, 26)
        btn_dn.set_size_request(34, 26)

        def on_toggle(cb, k=key):
            if cb.get_active():
                if k not in self._order:
                    self._order.append(k)
            else:
                if k in self._order:
                    self._order.remove(k)
            self._save_layout()
            self._rebuild()

        def move(delta, k=key):
            if k not in self._order:
                return
            i = self._order.index(k)
            j = i + delta
            if 0 <= j < len(self._order):
                self._order[i], self._order[j] = self._order[j], self._order[i]
                self._save_layout()
                self._rebuild()

        check.connect("toggled", on_toggle)
        btn_up.connect("clicked", lambda *_: move(-1))
        btn_dn.connect("clicked", lambda *_: move(1))
        row.pack_start(check, True, True, 0)
        row.pack_start(btn_up, False, False, 0)
        row.pack_start(btn_dn, False, False, 0)
        box.pack_start(row, False, False, 0)
        return row

    # ---------------- 模块构建 ----------------
    def _b_cards(self):
        card_box = Gtk.Box(spacing=10)
        self.temp_card = self._make_card("温度", "—", "°C")
        self.throttle_card = self._make_card("限流状态", "—", "")
        self.bat_card = self._make_card("电池", "—", "%")
        self.ac_card = self._make_card("供电", "—", "")
        card_box.pack_start(self.temp_card, True, True, 0)
        card_box.pack_start(self.throttle_card, True, True, 0)
        card_box.pack_start(self.bat_card, True, True, 0)
        card_box.pack_start(self.ac_card, True, True, 0)
        btn = Gtk.Button(label="⚙ 布局")
        btn.set_tooltip_text("自定义总览页模块显示与顺序")
        btn.connect("clicked", self._open_layout_dialog)
        card_box.pack_start(btn, False, False, 0)
        return card_box

    def _b_pwr(self):
        """实时功耗统一区：整机/核心/缓存/内存/GPU/电池 —— 集中一处查看所有实时功耗"""
        plab = Gtk.Label(label="实时功耗（RAPL + GPU + 电池）", xalign=0)
        plab.get_style_context().add_class("section-title")
        self.pwr = {}
        pg = Gtk.Grid(column_spacing=20, row_spacing=4)
        prows = [
            ("total", "整机", "RAPL package"), ("core", "CPU 核心", "core 域"),
            ("uncore", "CPU 缓存", "uncore 域"), ("dram", "内存", "dram 域"),
            ("gpu", "GPU", "独显/集显"), ("bat", "电池", "充/放电"),
        ]
        for i, (key, title, desc) in enumerate(prows):
            lab = Gtk.Label(label=title, xalign=0)
            val = Gtk.Label(label="—", xalign=0)
            val.get_style_context().add_class("detail-value")
            dsc = Gtk.Label(label=desc, xalign=0)
            dsc.get_style_context().add_class("dim-text")
            self.pwr[key] = val
            col = (i % 2) * 3
            pg.attach(lab, col, i // 2, 1, 1)
            pg.attach(val, col + 1, i // 2, 1, 1)
            pg.attach(dsc, col + 2, i // 2, 1, 1)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.pack_start(plab, False, False, 0)
        vbox.pack_start(pg, False, False, 0)
        return vbox

    def _b_cpu(self):
        curve_label = Gtk.Label(label="CPU 使用率（每线程）", xalign=0)
        curve_label.get_style_context().add_class("section-title")
        self.darea = Gtk.DrawingArea()
        self.darea.set_size_request(-1, 190)
        self.darea.set_hexpand(True)
        self.darea.connect("draw", self._on_draw)
        frame = Gtk.Frame()
        frame.add(self.darea)
        frame.set_hexpand(True)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.pack_start(curve_label, False, False, 0)
        vbox.pack_start(frame, True, True, 0)
        return vbox

    def _b_btemp(self):
        bt_label = Gtk.Label(label="电池温度（°C，acer-wmi-battery 模块）", xalign=0)
        bt_label.get_style_context().add_class("section-title")
        self.bt_label = bt_label
        self.bt_area = Gtk.DrawingArea()
        self.bt_area.set_size_request(-1, 70)
        self.bt_area.set_hexpand(True)
        self.bt_area.connect("draw", self._on_draw_temp)
        bt_frame = Gtk.Frame()
        bt_frame.add(self.bt_area)
        bt_frame.set_vexpand(True)
        bt_frame.set_hexpand(True)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.pack_start(bt_label, False, False, 0)
        vbox.pack_start(bt_frame, True, True, 0)
        return vbox

        ch_label.get_style_context().add_class("section-title")
        self.ch_area = Gtk.DrawingArea()
        self.ch_area.set_size_request(-1, 175)
        self.ch_area.set_hexpand(True)
        self.ch_area.connect("draw", self._on_draw_charge)
        ch_frame = Gtk.Frame()
        ch_frame.add(self.ch_area)
        ch_frame.set_vexpand(True)
        ch_frame.set_hexpand(True)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.pack_start(ch_label, False, False, 0)
        vbox.pack_start(ch_frame, True, True, 0)
        return vbox

        hk_label.get_style_context().add_class("section-title")
        self.hk_label = hk_label
        self.hk_area = Gtk.DrawingArea()
        self.hk_area.set_size_request(-1, 70)
        self.hk_area.set_hexpand(True)
        self.hk_area.connect("draw", self._on_draw_health)
        hk_frame = Gtk.Frame()
        hk_frame.add(self.hk_area)
        hk_frame.set_vexpand(True)
        hk_frame.set_hexpand(True)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.pack_start(hk_label, False, False, 0)
        vbox.pack_start(hk_frame, True, True, 0)
        return vbox

    def _b_details(self):
        det_label = Gtk.Label(label="实时明细", xalign=0)
        det_label.get_style_context().add_class("section-title")
        grid = Gtk.Grid(column_spacing=20, row_spacing=4)
        grid.set_hexpand(True)
        names = [
            # 2026-08-31: 移除"电源档位(PPD)"——PPD 被 masked 后 powerprofilesctl 失效恒显示"—"
            ("freq", "CPU 频率"), ("mem", "内存"), ("gpu", "GPU"),
            ("pl", "PL1 / PL2"), ("turbo", "Turbo"), ("epp", "EPP"),
            ("gov", "Governor"),
            ("tzones", "温度传感器"),
        ]
        for i, (key, title) in enumerate(names):
            lab = Gtk.Label(label=title, xalign=0)
            val = Gtk.Label(label="—", xalign=0)
            val.get_style_context().add_class("detail-value")
            self.details[key] = val
            grid.attach(lab, i % 2 * 2, i // 2, 1, 1)
            grid.attach(val, i % 2 * 2 + 1, i // 2, 1, 1)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.pack_start(det_label, False, False, 0)
        vbox.pack_start(grid, False, False, 0)
        return vbox

    # ---------------- 卡片 ----------------
    def _make_card(self, title, value, unit):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_name("stat-card")
        t = Gtk.Label(label=title)
        t.get_style_context().add_class("card-title")
        v = Gtk.Label(label=value)
        v.get_style_context().add_class("card-value")
        v.set_use_markup(True)
        u = Gtk.Label(label=unit)
        u.get_style_context().add_class("card-unit")
        box.pack_start(t, False, False, 0)
        box.pack_start(v, False, False, 0)
        box.pack_start(u, False, False, 0)
        return box

    # ---------------- 曲线绘制 ----------------
    def _on_draw(self, widget, cr):
        cr.set_source_rgb(0.95, 0.95, 0.95)
        cr.paint()
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        hist = list(self.history)
        n = len(hist)
        if n < 2:
            cr.set_source_rgb(0.6, 0.6, 0.6)
            cr.set_font_size(12)
            cr.move_to(w / 2 - 60, h / 2)
            cr.show_text("采样中…")
            return
        # 网格线
        cr.set_source_rgba(0.85, 0.85, 0.85, 1.0)
        cr.set_line_width(1)
        for pct in (25, 50, 75):
            y = h - h * pct / 100.0
            cr.move_to(0, y)
            cr.line_to(w, y)
            cr.stroke()
        # 每线程曲线
        ncores = len(hist[-1])
        for c in range(ncores):
            cr.set_source_rgba(*(CPU_COLORS[c % len(CPU_COLORS)] + (0.85,)))
            cr.set_line_width(1.4)
            first = True
            for i, point in enumerate(hist):
                if c >= len(point):
                    continue
                x = i / max(1, n - 1) * w   # 按实际点数缩放，未满屏时铺满
                y = h - h * max(0.0, min(100.0, point[c])) / 100.0
                if first:
                    cr.move_to(x, y)
                    first = False
                else:
                    cr.line_to(x, y)
            cr.stroke()

    # ---------------- 电池温度曲线绘制 ----------------
    def _on_draw_temp(self, widget, cr):
        cr.set_source_rgb(0.95, 0.95, 0.95)
        cr.paint()
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        hist = list(self.bt_history)
        n = len(hist)
        if n < 2:
            cr.set_source_rgb(0.6, 0.6, 0.6)
            cr.set_font_size(11)
            cr.move_to(10, h / 2 + 4)
            cr.show_text("等待电池温度数据（acer-wmi-battery 模块，每分钟读取一次）")
            return
        vals = [v for v in hist if v is not None]
        if len(vals) < 2:
            return
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1.0
        cr.set_source_rgba(0.91, 0.30, 0.24, 0.9)
        cr.set_line_width(1.6)
        first = True
        for i, v in enumerate(hist):
            if v is None:
                continue
            x = i / (HISTORY - 1) * w
            y = h - (v - lo) / span * (h - 8) - 4
            if first:
                cr.move_to(x, y)
                first = False
            else:
                cr.line_to(x, y)
        cr.stroke()
        # 45°C 警戒线
        if hi >= 40:
            y = h - (45 - lo) / span * (h - 8) - 4
            if 0 <= y <= h:
                cr.set_source_rgba(0.8, 0.2, 0.2, 0.7)
                cr.set_line_width(0.8)
                cr.set_dash([3, 3], 0)
                cr.move_to(0, y)
                cr.line_to(w, y)
                cr.stroke()
                cr.set_dash([], 0)
                cr.set_font_size(10)
                cr.move_to(w - 46, y - 3)
                cr.show_text("45°C")
        cr.set_source_rgb(0.3, 0.3, 0.3)
        cr.set_font_size(10)
        cr.move_to(4, 10)
        cr.show_text("%.0f°C" % hi)
        cr.move_to(w - 30, h - 4)
        cr.show_text("%.0f°C" % lo)

        cr.paint()
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        hist = self.charge_hist
        n = len(hist)
        if n < 2:
            cr.set_source_rgb(0.6, 0.6, 0.6)
            cr.set_font_size(11)
            cr.move_to(10, h / 2 + 4)
            cr.show_text("插电充电时自动记录（本次充电周期实时曲线）")
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
        cr.show_text("%d%% · %.0fmA · %.2fV · %d点" % (last[0], last[1], last[2], n))
        cr.move_to(pl + pw - 70, h - 4)
        cr.show_text("蓝=容量 红=电流")

        cr.paint()
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        hist = self.health_hist
        if len(hist) < 1:
            cr.set_source_rgb(0.6, 0.6, 0.6)
            cr.set_font_size(11)
            cr.move_to(10, h / 2 + 4)
            cr.show_text("等待首次协议采样（放电到 40-60% 时自动记录）")
            return
        if len(hist) == 1:
            # 单条采样：大数字显示，说明采样机制
            v = hist[0][1]
            cr.set_source_rgb(0.18, 0.72, 0.40)
            cr.set_font_size(30)
            cr.move_to(14, h / 2 + 10)
            cr.show_text("%.1f%%" % v)
            cr.set_source_rgb(0.3, 0.3, 0.3)
            cr.set_font_size(11)
            cr.move_to(110, h / 2 + 2)
            cr.show_text("健康度（%s 采样）" % hist[0][0][:10])
            cr.move_to(110, h / 2 + 18)
            cr.show_text("下一条：放电至 40-60%% 自动记录 → 出趋势线")
            return
        # 健康度折线（纵轴以首条为基准 ±5% 窗口）
        base = hist[0][1]
        vals = [v for _, v in hist]
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1.0
        cr.set_source_rgba(0.18, 0.72, 0.40, 0.9)
        cr.set_line_width(1.8)
        first = True
        for i, (date, v) in enumerate(hist):
            x = i / max(1, len(hist) - 1) * w
            y = h - (v - lo) / span * (h - 8) - 4
            if first:
                cr.move_to(x, y)
                first = False
            else:
                cr.line_to(x, y)
        cr.stroke()
        # 数值标注
        cr.set_source_rgb(0.3, 0.3, 0.3)
        cr.set_font_size(10)
        cr.move_to(4, 10)
        cr.show_text("%.1f%% → %.1f%%" % (lo, hi))
        last = hist[-1]
        cr.move_to(w - 110, h - 4)
        cr.show_text("%s: %.1f%%" % (last[0][5:], last[1]))

    # ---------------- 数据更新 ----------------
    def update(self, d):
        # 卡片
        temp = d["temp"]
        self.temp_card.get_children()[1].set_markup(
            "<span size='x-large'>%s</span>" % (("%.0f" % temp) if temp is not None else "—"))
        pw = d["power_w"]
        # 实时功耗统一区（pwr 模块）
        if hasattr(self, "pwr"):
            # 整机功耗
            self.pwr["total"].set_text(("%.1f W" % pw) if pw is not None else "—")
            # 功耗分解 core/uncore/dram
            pd = d.get("power_dc") or {}
            for k in ("core", "uncore", "dram"):
                self.pwr[k].set_text(("%.1f W" % pd[k]) if k in pd else "—")
            # GPU 功耗（nvidia 模式有 power.draw；intel 模式显示 iGPU 状态）
            g = d["gpu"]
            if g and g.get("power") is not None:
                self.pwr["gpu"].set_text("%.1f W（独显）" % g["power"])
            else:
                self.pwr["gpu"].set_text("iGPU（MX150 断电）" if not d["ac"] else "iGPU（集显）")
            # 电池功耗
            b = d["bat"]
            if b["status"] == "Discharging" and b.get("power_w"):
                self.pwr["bat"].set_text("%.1f W（放电）" % b["power_w"])
            elif b["status"] == "Charging":
                self.pwr["bat"].set_text("充电中")
            else:
                self.pwr["bat"].set_text("—")
        b = d["bat"]
        if b["capacity"] is not None:
            # 电池卡: 容量 + 状态短标（充电/满电/放电/阶段）
            st = {"Charging": "充", "Full": "满", "Discharging": "放"}.get(b["status"], "")
            ph = {"cv": " CV", "cc": "", "full": ""}.get(b["phase"], "")
            self.bat_card.get_children()[1].set_markup(
                "<span size='x-large'>%d%%</span>" % b["capacity"])
            self.bat_card.get_children()[2].set_text(
                (st + ph) if st else "")
        else:
            self.bat_card.get_children()[1].set_markup("<span size='x-large'>—</span>")
        ac = d["ac"]
        if ac is True:
            self.ac_card.get_children()[1].set_markup("<span size='x-large'>AC</span>")
            self.ac_card.get_style_context().add_class("ac-on")
        elif ac is False:
            self.ac_card.get_children()[1].set_markup("<span size='x-large'>DC</span>")
            self.ac_card.get_style_context().remove_class("ac-on")
        else:
            self.ac_card.get_children()[1].set_markup("<span size='x-large'>—</span>")

        # 限流状态卡片更新
        if hasattr(self, 'throttle_card'):
            try:
                from src.core.msr_reader import get_throttle_status
                status = get_throttle_status()
                self.throttle_card.get_children()[1].set_markup(
                    "<span size='x-large'>{}</span>".format(status.summary_text().replace("|", " | "))
                )
                # tooltip 显示详情
                self.throttle_card.set_tooltip_text(status.summary_text())
            except Exception:
                self.throttle_card.get_children()[1].set_markup("<span size='x-large'>—</span>")

        # 曲线
        usages = [c[0] for c in d["cpu"]]
        if usages and all(u is not None for u in usages):
            self.history.append(usages)
            self.darea.queue_draw()

        # 明细
        cpu = d["cpu"]
        freqs = [f for _, f in cpu if f]
        if freqs:
            self.details["freq"].set_text("%d – %d MHz" % (min(freqs), max(freqs)))
        else:
            self.details["freq"].set_text("—")
        m = d["mem"]
        if m["used_mb"] is not None and m["total_mb"]:
            self.details["mem"].set_text("%d / %d MB (%.0f%%)"
                                         % (m["used_mb"], m["total_mb"], m["pct"]))
        else:
            self.details["mem"].set_text("—")
        g = d["gpu"]
        if g:
            parts = []
            if g["util"] is not None:
                parts.append("%.0f%%" % g["util"])
            if g["temp"] is not None:
                parts.append("%.0f°C" % g["temp"])
            if g["power"] is not None:
                parts.append("%.1fW" % g["power"])
            if g["mem_used"] is not None and g["mem_total"]:
                parts.append("%.0f/%.0fMB" % (g["mem_used"], g["mem_total"]))
            self.details["gpu"].set_text(" · ".join(parts) if parts else "不可用")
        else:
            self.details["gpu"].set_text("集显/不可用")
        p = d["params"]
        self.details["pl"].set_text(
            "%s / %s W" % (self._w(p["pl1_w"]), self._w(p["pl2_w"])))
        t = p["turbo"]
        self.details["turbo"].set_text("ON" if t is True else ("OFF" if t is False else "—"))
        self.details["epp"].set_text(p["epp"] or "—")
        # 2026-08-31: PPD 已从实时明细移除（PPD masked 后恒"—"）
        self.details["gov"].set_text(p["governor"] or "—")
        # 健康协议采样与健康趋势已迁移至【电池保养】页
        # thermal 传感器
        tz = b.get("thermal", {})
        parts = []
        for key, lab in (("thermal_zone0", "机壳A"), ("thermal_zone1", "机壳B"), ("thermal_zone2", "CPU")):
            v = tz.get(key)
            if v is not None:
                parts.append("%s %.0f°C" % (lab, v))
        self.details["tzones"].set_text("  ·  ".join(parts) if parts else "—")
        # 电池温度曲线数据积累（明细行已迁至电池页，但曲线保留在总览）
        btd = b.get("temp_c")
        if btd is not None:
            self.bt_history.append(btd)
            self.bt_area.queue_draw()
            self.bt_label.set_text("电池温度（°C，acer-wmi-battery 模块）")


    @staticmethod
    def _w(v):
        return "%.1f" % v if v is not None else "—"