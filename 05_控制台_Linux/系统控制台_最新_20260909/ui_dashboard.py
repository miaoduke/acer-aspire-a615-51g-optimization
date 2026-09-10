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

from src.core.i18n import T

HISTORY = 150  # 曲线点数
CPU_COLORS = [
    (0.22, 0.55, 0.95), (0.91, 0.30, 0.24), (0.18, 0.72, 0.40), (0.89, 0.66, 0.12),
    (0.61, 0.35, 0.92), (0.93, 0.46, 0.16), (0.30, 0.74, 0.83), (0.76, 0.33, 0.56),
]

# 模块定义: (key, 显示名, 垂直扩展)
# 2026-09-01: ①btemp(电池温度)→gpu ②details 并入 pwr(实时功耗+明细合一, 减少纵向滚动)
MODULES = [
    ("cards", T("状态卡"), False),
    ("pwr", T("实时功耗与明细"), False),
    ("cpu", T("CPU 占用/温度曲线"), True),
    ("gpu", T("GPU 占用/温度曲线"), True),
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
        except Exception as e:
            # 2026-09-07 审计：布局保存失败不能静默（用户会困惑为何设置丢失）
            print(f"[layout] 保存失败: {e}")

    def _rebuild(self):
        """按当前顺序重建页面（所有模块都构建，隐藏的仅不显示——保证 update 引用安全）"""
        for child in self.get_children():
            self.remove(child)
        builders = {
            "cards": self._b_cards, "pwr": self._b_pwr, "cpu": self._b_cpu, "gpu": self._b_gpu,
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
        dlg = Gtk.Dialog(title=T("总览布局设置"), transient_for=self.get_toplevel(), modal=True)
        dlg.set_default_size(360, 380)
        box = dlg.get_content_area()
        lab = Gtk.Label(
            label=T("勾选 = 显示；取消 = 隐藏。↑↓ 调整显示顺序。修改即时生效。"),
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

        dlg.add_button(T("关闭"), Gtk.ResponseType.CLOSE)
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
        self.temp_card = self._make_card(T("温度"), "—", "°C")
        self.throttle_card = self._make_card(T("限流状态"), "—", "")
        self.bat_card = self._make_card(T("电池"), "—", "%")
        self.ac_card = self._make_card(T("供电"), "—", "")
        card_box.pack_start(self.temp_card, True, True, 0)
        card_box.pack_start(self.throttle_card, True, True, 0)
        card_box.pack_start(self.bat_card, True, True, 0)
        card_box.pack_start(self.ac_card, True, True, 0)
        btn = Gtk.Button(label=T("⚙ 布局"))
        btn.set_tooltip_text(T("自定义总览页模块显示与顺序"))
        btn.connect("clicked", self._open_layout_dialog)
        card_box.pack_start(btn, False, False, 0)
        return card_box

    def _b_pwr(self):
        """实时功耗与明细统一区（2026-09-01 合并: 原 pwr + details 两模块合一, 减少纵向滚动）"""
        plab = Gtk.Label(label=T("实时功耗与明细"), xalign=0)
        plab.get_style_context().add_class("section-title")
        self.pwr = {}
        pg = Gtk.Grid(column_spacing=20, row_spacing=4)
        prows = [
            ("total", T("整机"), "RAPL package"), ("core", T("CPU 核心"), T("core 域")),
            ("uncore", T("CPU 缓存"), T("uncore 域")), ("dram", T("内存"), T("dram 域")),
            ("gpu", T("GPU"), T("独显/集显")), ("bat", T("电池"), T("充/放电")),
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
        # 明细网格（原 _b_details 的内容合并至此）
        dgrid = Gtk.Grid(column_spacing=20, row_spacing=4)
        dgrid.set_hexpand(True)
        self.details = {}
        dnames = [
            ("freq", T("CPU 频率")), ("mem", T("内存")), ("gpu", T("GPU")),
            ("pl", "PL1 / PL2"), ("turbo", "Turbo"), ("epp", "EPP"),
            ("gov", "Governor"),
            ("tzones", T("温度传感器")),
        ]
        for i, (key, title) in enumerate(dnames):
            lab = Gtk.Label(label=title, xalign=0)
            val = Gtk.Label(label="—", xalign=0)
            val.get_style_context().add_class("detail-value")
            self.details[key] = val
            dgrid.attach(lab, (i % 2) * 2, i // 2, 1, 1)
            dgrid.attach(val, (i % 2) * 2 + 1, i // 2, 1, 1)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.pack_start(plab, False, False, 0)
        vbox.pack_start(pg, False, False, 0)
        sep = Gtk.Separator()
        sep.set_margin_top(6)
        sep.set_margin_bottom(2)
        vbox.pack_start(sep, False, False, 0)
        vbox.pack_start(dgrid, False, False, 0)
        return vbox

    def _b_cpu(self):
        curve_label = Gtk.Label(label=T("CPU 使用率（每线程）"), xalign=0)
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

    def _b_gpu(self):
        # 2026-09-01: 电池温度曲线 → GPU 占用/温度曲线（总览页只关注 GPU 状态）
        bt_label = Gtk.Label(label=T("GPU 占用/温度（独显 nvidia-smi / 集显 i915）"), xalign=0)
        bt_label.get_style_context().add_class("section-title")
        self.bt_label = bt_label
        self.bt_area = Gtk.DrawingArea()
        self.bt_area.set_size_request(-1, 80)
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
        # 2026-09-01: 原充电/健康曲线死代码已删
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
            cr.show_text(T("采样中…"))
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

        # 2026-09-01: CPU 封装温度叠加线（红色，0-100°C 右侧轴）
        temps = getattr(self, "cpu_temp_hist", None)
        if temps and len(temps) >= 2:
            tvals = [t for t in temps if t is not None]
            if tvals:
                cr.set_source_rgba(0.91, 0.30, 0.24, 0.8)
                cr.set_line_width(1.6)
                first = True
                for i, tv in enumerate(temps):
                    if tv is None:
                        continue
                    x = i / max(1, len(temps) - 1) * w
                    y = h - h * min(100.0, tv) / 100.0
                    if first:
                        cr.move_to(x, y)
                        first = False
                    else:
                        cr.line_to(x, y)
                cr.stroke()
                # 标注
                cr.set_source_rgb(0.3, 0.3, 0.3)
                cr.set_font_size(10)
                cr.move_to(4, h - 6)
                cr.show_text(T("占用(每线程)  温度(红) %.0f°C") % tvals[-1])

    # ---------------- GPU 占用/温度曲线绘制（2026-09-01: 原电池温度曲线）---------------
    def _on_draw_temp(self, widget, cr):
        cr.set_source_rgb(0.95, 0.95, 0.95)
        cr.paint()
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        hist = list(self.bt_history)
        # 过滤掉 None 项（集显模式不可用）
        pts = [(i, u, t) for i, (u, t) in enumerate(hist) if u is not None]
        if len(pts) < 2:
            cr.set_source_rgb(0.6, 0.6, 0.6)
            cr.set_font_size(11)
            cr.move_to(10, h / 2 + 4)
            cr.show_text(T("GPU 数据不可用（集显模式 / nvidia-smi 无输出）"))
            return
        # 占用率（左轴 0-100%，蓝）
        cr.set_source_rgba(0.22, 0.55, 0.95, 0.9)
        cr.set_line_width(1.6)
        first = True
        for i, u, t in pts:
            x = i / (HISTORY - 1) * w
            y = h - u / 100.0 * (h - 8) - 4
            if first:
                cr.move_to(x, y)
                first = False
            else:
                cr.line_to(x, y)
        cr.stroke()
        # 温度（右轴 0-100°C，红）
        cr.set_source_rgba(0.91, 0.30, 0.24, 0.9)
        cr.set_line_width(1.3)
        first = True
        for i, u, t in pts:
            x = i / (HISTORY - 1) * w
            y = h - (t / 100.0 if t else 0) * (h - 8) - 4
            if first:
                cr.move_to(x, y)
                first = False
            else:
                cr.line_to(x, y)
        cr.stroke()
        # 标注最新值
        lu, lt = pts[-1][1], pts[-1][2]
        cr.set_source_rgb(0.3, 0.3, 0.3)
        cr.set_font_size(10)
        cr.move_to(4, 10)
        cr.show_text(T("占用 %.0f%%") % lu)
        cr.move_to(w - 60, 10)
        cr.show_text(T("温度 %.0f°C") % (lt or 0))
        cr.move_to(4, h - 4)
        cr.show_text(T("蓝=占用 红=温度"))
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
                self.pwr["gpu"].set_text(T("%.1f W（独显）") % g["power"])
            else:
                self.pwr["gpu"].set_text(T("iGPU（MX150 断电）") if not d["ac"] else T("iGPU（集显）"))
            # 电池功耗
            b = d["bat"]
            if b["status"] == "Discharging" and b.get("power_w"):
                self.pwr["bat"].set_text(T("%.1f W（放电）") % b["power_w"])
            elif b["status"] == "Charging":
                self.pwr["bat"].set_text(T("充电中"))
            else:
                self.pwr["bat"].set_text("—")
        b = d["bat"]
        if b["capacity"] is not None:
            # 电池卡: 容量 + 状态短标（充电/满电/放电/阶段）
            st = {"Charging": T("充"), "Full": T("满"), "Discharging": T("放")}.get(b["status"], "")
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
                from src.core.throttle_history import get_throttle_history
                status = get_throttle_status()
                self.throttle_card.get_children()[1].set_markup(
                    "<span size='x-large'>{}</span>".format(status.summary_text().replace("|", " | "))
                )
                # G6: tooltip 加 24h 历史摘要
                try:
                    _, hist = get_throttle_history(hours=24)
                    tooltip = "{}\n\n{}\n{}".format(status.summary_text(), T("━━ 24h 历史 ━━"), hist)
                    self.throttle_card.set_tooltip_text(tooltip)
                except Exception:
                    self.throttle_card.set_tooltip_text(status.summary_text())
            except Exception:
                self.throttle_card.get_children()[1].set_markup("<span size='x-large'>—</span>")

        # 曲线（2026-09-01: 并排记录 CPU 温度，供 _on_draw 叠加温度线）
        usages = [c[0] for c in d["cpu"]]
        if usages and all(u is not None for u in usages):
            self.history.append(usages)
            # 同步记录 CPU 封装温度（d["temp"] 已是 CPU 封装优先）
            if not hasattr(self, "cpu_temp_hist"):
                self.cpu_temp_hist = deque(maxlen=HISTORY)
            self.cpu_temp_hist.append(d.get("temp"))
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
            self.details["gpu"].set_text(" · ".join(parts) if parts else T("不可用"))
        else:
            self.details["gpu"].set_text(T("集显/不可用"))
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
        for key, lab in (("thermal_zone0", T("机壳A")), ("thermal_zone1", T("机壳B")), ("thermal_zone2", T("CPU"))):
            v = tz.get(key)
            if v is not None:
                parts.append("%s %.0f°C" % (lab, v))
        self.details["tzones"].set_text("  ·  ".join(parts) if parts else "—")
        # GPU 占用/温度曲线数据积累（2026-09-01: 原电池温度曲线，电池页已有独立曲线）
        # bt_history 存 (占用%, 温度°C) 元组；intel 集显模式 nvidia-smi 不可用，用 i915 状态
        g = d.get("gpu")
        if g and g.get("util") is not None:
            self.bt_history.append((g.get("util") or 0, g.get("temp") or 0))
        else:
            # 集显模式: 记录 GPU 状态（如 i915 活跃则占用按 CPU 渲染负载近似，此处标记不可用）
            self.bt_history.append((None, None))
        self.bt_area.queue_draw()


    @staticmethod
    def _w(v):
        return "%.1f" % v if v is not None else "—"