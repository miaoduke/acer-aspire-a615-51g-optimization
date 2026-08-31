#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ui_maintenance.py — 系统维护页：服务状态 / 内核守卫 / 硬件诊断 / 日志回看
职责：系统健康监测与诊断维护（自高级页迁移，2026-08-21 科学重排）
"""
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from async_util import run_async
import controller


class MaintenancePage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)

        head = Gtk.Label(label="系统维护与诊断", xalign=0)
        head.get_style_context().add_class("section-title")
        self.pack_start(head, False, False, 0)

        hint = Gtk.Label(
            label="系统健康监测、内核变动防护、硬件错误诊断与性能数据回看。",
            xalign=0, wrap=True)
        hint.get_style_context().add_class("dim-text")
        self.pack_start(hint, False, False, 0)

        # ---- 服务状态 ----
        sbox = Gtk.Box(spacing=8)
        sl = Gtk.Label(label="优化栈服务状态", xalign=0)
        sl.get_style_context().add_class("section-title")
        sbox.pack_start(sl, False, False, 0)
        self.svc_refresh = Gtk.Button(label="刷新")
        self.svc_refresh.connect("clicked", lambda _b: self._load_services())
        sbox.pack_end(self.svc_refresh, False, False, 0)
        self.pack_start(sbox, False, False, 0)

        self.svc_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.add(self.svc_list)
        sw.set_size_request(-1, 150)
        self.pack_start(sw, False, False, 0)

        # ---- 内核变动检测 ----
        kbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        kbox.set_margin_top(12)
        krow = Gtk.Box(spacing=8)
        kl = Gtk.Label(label="内核变动检测 / 一键修复", xalign=0)
        kl.get_style_context().add_class("section-title")
        self.kern_ver = Gtk.Label(label="—", xalign=0)
        self.kern_ver.get_style_context().add_class("mono-text")
        self.kbtn_check = Gtk.Button(label="重新检测")
        self.kbtn_check.connect("clicked", lambda _b: self._kernel_guard("check"))
        self.kbtn_repair = Gtk.Button(label="一键修复")
        self.kbtn_repair.connect("clicked", lambda _b: self._kernel_guard("repair"))
        krow.pack_start(kl, False, False, 0)
        krow.pack_start(self.kern_ver, False, False, 0)
        krow.pack_end(self.kbtn_repair, False, False, 0)
        krow.pack_end(self.kbtn_check, False, False, 0)
        kbox.pack_start(krow, False, False, 0)

        self.kern_buf = Gtk.TextBuffer()
        self.kern_tv = Gtk.TextView(buffer=self.kern_buf)
        self.kern_tv.set_editable(False)
        self.kern_tv.set_cursor_visible(False)
        self.kern_tv.set_monospace(True)
        self.kern_tv.set_wrap_mode(Gtk.WrapMode.NONE)
        ksw = Gtk.ScrolledWindow()
        ksw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        ksw.add(self.kern_tv)
        ksw.set_size_request(-1, 160)
        kbox.pack_start(ksw, False, False, 0)
        self.pack_start(kbox, False, False, 0)

        # ---- 工具与诊断 ----
        tbox2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        tbox2.set_margin_top(12)
        tl2 = Gtk.Label(label="工具与诊断", xalign=0)
        tl2.get_style_context().add_class("section-title")
        tbox2.pack_start(tl2, False, False, 0)

        btn_row = Gtk.Box(spacing=8)

        perf_btn = Gtk.Button(label="📊 性能日志")
        perf_btn.set_tooltip_text("查看 CPU 频率/温度/功耗/限流历史记录")
        perf_btn.connect("clicked", self._open_perf_log)

        app_pwr_btn = Gtk.Button(label="🔋 应用功耗排行")
        app_pwr_btn.set_tooltip_text("查看哪些应用在消耗 CPU 和功耗（cgroup 分析）")
        app_pwr_btn.connect("clicked", self._open_app_power)

        mce_btn = Gtk.Button(label="🩺 MCE 硬件错误")
        mce_btn.set_tooltip_text("查看内存错误 / PCIe AER / 机器检查事件")
        mce_btn.connect("clicked", self._on_mce)

        btn_row.pack_start(perf_btn, False, False, 0)
        btn_row.pack_start(app_pwr_btn, False, False, 0)
        btn_row.pack_start(mce_btn, False, False, 0)
        tbox2.pack_start(btn_row, False, False, 0)
        self.pack_start(tbox2, False, False, 0)

        # ---- 运维工具区（2026-08-31 新增）----
        # 快照/备份/降权——铁律工具的 GUI 化，此前只能命令行
        otbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        otbox.set_margin_top(12)
        otl = Gtk.Label(label="运维工具（铁律 · 一键化）", xalign=0)
        otl.get_style_context().add_class("section-title")
        otbox.pack_start(otl, False, False, 0)

        orow1 = Gtk.Box(spacing=8)
        self.snap_create = Gtk.Button(label="📸 系统快照")
        self.snap_create.set_tooltip_text("Timeshift 快照（铁律 L1/L2：系统/高风险改动前必做）")
        self.snap_create.connect("clicked", self._on_snapshot_create)
        self.snap_list = Gtk.Button(label="🗂 快照列表")
        self.snap_list.set_tooltip_text("查看已有 Timeshift 快照")
        self.snap_list.connect("clicked", self._on_snapshot_list)
        self.snap_delete = Gtk.Button(label="🗑 删除快照")
        self.snap_delete.set_tooltip_text("删除选中的 Timeshift 快照（危险，需确认）")
        self.snap_delete.connect("clicked", self._on_snapshot_delete)
        orow1.pack_start(self.snap_create, False, False, 0)
        orow1.pack_start(self.snap_list, False, False, 0)
        orow1.pack_start(self.snap_delete, False, False, 0)
        otbox.pack_start(orow1, False, False, 0)

        orow2 = Gtk.Box(spacing=8)
        self.quiet_btn = Gtk.Button(label="🔇 后台降权")
        self.quiet_btn.set_tooltip_text("后台进程 renice+15（基准测试前用，数据更干净）")
        self.quiet_btn.connect("clicked", self._on_quiet, True)
        self.unquiet_btn = Gtk.Button(label="🔊 恢复优先级")
        self.unquiet_btn.set_tooltip_text("恢复后台进程优先级")
        self.unquiet_btn.connect("clicked", self._on_quiet, False)
        self.ops_state = Gtk.Label(label="", xalign=0)
        self.ops_state.get_style_context().add_class("dim-text")
        orow2.pack_start(self.quiet_btn, False, False, 0)
        orow2.pack_start(self.unquiet_btn, False, False, 0)
        orow2.pack_start(self.ops_state, False, False, 0)
        otbox.pack_start(orow2, False, False, 0)
        self.pack_start(otbox, False, False, 0)

        # ---- 电池温度模块 ----
        tbox = Gtk.Box(spacing=8)
        tbox.set_margin_top(10)
        tlab = Gtk.Label(label="电池温度模块（acer-wmi-battery）：", xalign=0)
        self.temp_load = Gtk.Button(label="加载")
        self.temp_load.connect("clicked", self._on_temp_mod, True)
        self.temp_unload = Gtk.Button(label="卸载")
        self.temp_unload.connect("clicked", self._on_temp_mod, False)
        self.temp_state = Gtk.Label(label="—", xalign=0)
        self.temp_state.get_style_context().add_class("dim-text")
        tbox.pack_start(tlab, False, False, 0)
        tbox.pack_start(self.temp_load, False, False, 0)
        tbox.pack_start(self.temp_unload, False, False, 0)
        tbox.pack_start(self.temp_state, False, False, 0)
        self.pack_start(tbox, False, False, 0)

        self._load_services()
        self.refresh_temp_state()
        self.refresh_kern_ver()

    # ---------------- 服务 ----------------
    def _load_services(self):
        def worker():
            return controller.service_states()

        def done(states):
            for ch in self.svc_list.get_children():
                self.svc_list.remove(ch)
            for name, desc, state in states:
                row = Gtk.Box(spacing=8)
                n = Gtk.Label(label=name, xalign=0)
                n.get_style_context().add_class("mono-text")
                dd = Gtk.Label(label=desc, xalign=0)
                dd.get_style_context().add_class("dim-text")
                st = Gtk.Label(label=state or "未知", xalign=0)
                st.get_style_context().add_class("svc-" + (state or "unknown"))
                row.pack_start(n, False, False, 0)
                row.pack_start(dd, False, False, 0)
                row.pack_end(st, False, False, 0)
                self.svc_list.pack_start(row, False, False, 0)
            self.svc_list.show_all()

        run_async(worker, done)

    # ---------------- 内核守卫 ----------------
    def _kernel_guard(self, mode):
        def worker():
            import subprocess
            try:
                r = subprocess.run(
                    ["sudo", "-n", "/home/<USER>/桌面/系统控制台/backend/kernel_guard.sh", mode],
                    capture_output=True, text=True, timeout=120)
                return (r.returncode, r.stdout, r.stderr)
            except Exception as e:
                return (1, "", str(e))

        def done(result):
            rc, out, err = result
            if rc == 0:
                self.kern_buf.set_text(out)
            else:
                self.kern_buf.set_text("内核守卫执行失败：%s\n%s" % (err or out, out))
            self.refresh_kern_ver()

        self.kern_buf.set_text("内核守卫运行中（%s）…" % ("修复" if mode == "repair" else "检测"))
        run_async(worker, done)

    def refresh_kern_ver(self):
        def worker():
            import subprocess
            try:
                r = subprocess.run(["uname", "-r"], capture_output=True, text=True, timeout=3)
                return r.stdout.strip()
            except Exception:
                return None

        def done(v):
            if v:
                self.kern_ver.set_text("内核 %s" % v)

        run_async(worker, done)

    # ---------------- 性能日志 ----------------
    def _open_perf_log(self, _btn=None):
        dlg = Gtk.Dialog(title="性能日志回看", transient_for=self.get_toplevel(), modal=True)
        dlg.set_default_size(720, 480)
        box = dlg.get_content_area()

        hbox = Gtk.Box(spacing=8)
        hbox.set_margin_top(8)
        hbox.set_margin_start(8)
        hbox.set_margin_end(8)
        lab = Gtk.Label(label="时间范围：", xalign=0)
        combo = Gtk.ComboBoxText()
        for label, hours in [("最近 1 小时", 1), ("最近 6 小时", 6), ("最近 24 小时", 24), ("最近 7 天", 168)]:
            combo.append(str(hours), label)
        combo.set_active(0)
        hbox.pack_start(lab, False, False, 0)
        hbox.pack_start(combo, False, False, 0)

        refresh_btn = Gtk.Button(label="刷新")
        hbox.pack_end(refresh_btn, False, False, 0)
        box.pack_start(hbox, False, False, 0)

        buf = Gtk.TextBuffer()
        tv = Gtk.TextView(buffer=buf)
        tv.set_editable(False)
        tv.set_monospace(True)
        tv.set_wrap_mode(Gtk.WrapMode.NONE)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.add(tv)
        sw.set_vexpand(True)
        box.pack_start(sw, True, True, 0)

        def load_data(_btn=None):
            hours = float(combo.get_active_id() or 1)
            try:
                from src.core.perf_logger import get_perf_history, get_perf_stats
                hist = get_perf_history(hours)
                stats = get_perf_stats(hours)

                lines = []
                lines.append(f"=== 性能数据统计（{hours}h） ===")
                lines.append(f"采样数: {stats.get('samples', 0)}")
                pw = stats.get('pkg_power', {})
                lines.append(f"整机功耗: 平均 {pw.get('avg', 0):.1f}W / 最大 {pw.get('max', 0):.1f}W / 最小 {pw.get('min', 0):.1f}W")
                tp = stats.get('temp', {})
                lines.append(f"CPU 温度: 平均 {tp.get('avg', 0):.1f}°C / 最高 {tp.get('max', 0):.1f}°C / 最低 {tp.get('min', 0):.1f}°C")
                lines.append(f"限流事件: {stats.get('throttle_events', 0)} 次")
                lines.append("")
                lines.append("=== 最近 20 条记录 ===")
                lines.append("时间          频率     温度   功耗   状态")
                lines.append("-" * 55)
                for d in hist[-20:]:
                    ts = time.strftime("%H:%M:%S", time.localtime(d['timestamp']))
                    th = []
                    if d.get('throttle_thermal'):
                        th.append(f"热({d['throttle_thermal']})")
                    if d.get('throttle_power'):
                        th.append(f"功({d['throttle_power']})")
                    status = ",".join(th) if th else "正常"
                    lines.append(
                        f"{ts}  {d.get('cpu_freq_max', 0):.0f}MHz  {d.get('cpu_temp', 0):.0f}°C  "
                        f"{d.get('pkg_w', 0):.1f}W  {status}"
                    )
                buf.set_text("\n".join(lines))
            except Exception as e:
                buf.set_text(f"加载失败: {e}\n可能尚未有性能数据记录")

        refresh_btn.connect("clicked", load_data)
        combo.connect("changed", load_data)

        dlg.show_all()
        load_data()
        dlg.run()
        dlg.destroy()

    # ---------------- 应用功耗排行 ----------------
    def _open_app_power(self, _btn=None):
        dlg = Gtk.Dialog(title="应用功耗排行（cgroup 分析）", transient_for=self.get_toplevel(), modal=True)
        dlg.set_default_size(640, 460)
        box = dlg.get_content_area()
        box.set_spacing(8)
        box.set_margin_top(10)
        box.set_margin_start(10)
        box.set_margin_end(10)

        note = Gtk.Label(label="基于 cgroup CPU 时间差分估算功耗占比。首次打开为基线，3 秒后点刷新看数据。", xalign=0)
        note.get_style_context().add_class("dim-text")
        box.pack_start(note, False, False, 0)

        store = Gtk.ListStore(str, float, float, float, str)
        tree = Gtk.TreeView(model=store, enable_grid_lines=True)

        for i, (title, xalign) in enumerate([("应用", 0.0), ("CPU %", 1.0), ("功耗 W", 1.0), ("占比 %", 1.0), ("类型", 0.5)]):
            cell = Gtk.CellRendererText()
            cell.set_property("xalign", xalign)
            col = Gtk.TreeViewColumn(title, cell, text=i)
            col.set_sort_column_id(i)
            col.set_resizable(True)
            if i > 0:
                col.set_alignment(xalign)
            tree.append_column(col)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.add(tree)
        sw.set_vexpand(True)
        box.pack_start(sw, True, True, 0)

        btn_row = Gtk.Box(spacing=8)
        refresh_btn = Gtk.Button(label="🔄 刷新")
        refresh_btn.get_style_context().add_class("suggested-action")
        auto_check = Gtk.CheckButton(label="自动刷新 (3s)")
        pkg_label = Gtk.Label(label="", xalign=0)
        pkg_label.get_style_context().add_class("dim-text")
        btn_row.pack_start(refresh_btn, False, False, 0)
        btn_row.pack_start(auto_check, False, False, 0)
        btn_row.pack_end(pkg_label, False, False, 0)
        box.pack_start(btn_row, False, False, 0)

        auto_id = [0]

        def refresh(_btn=None):
            try:
                pw = None
                try:
                    from collector import Collector
                    c = Collector()
                    d = c.sample()
                    pw = d.get("power_w")
                except Exception:
                    pass

                from src.core.app_power import get_app_power_ranking
                results = get_app_power_ranking(pw)

                store.clear()
                for r in results:
                    typ = "图形应用" if r.is_app else "服务/后台"
                    store.append([r.name, round(r.cpu_pct, 1), round(r.power_w, 2),
                                  round(r.pct_of_total, 1), typ])

                if pw:
                    pkg_label.set_text(f"整机功耗: {pw:.1f}W")
            except Exception as e:
                store.clear()
                store.append([f"加载失败: {e}", 0, 0, 0, ""])

        def toggle_auto(_btn):
            if auto_check.get_active():
                refresh(None)
                auto_id[0] = GLib.timeout_add_seconds(3, lambda: (refresh(None), True)[1])
            else:
                if auto_id[0]:
                    GLib.source_remove(auto_id[0])
                    auto_id[0] = 0

        refresh_btn.connect("clicked", refresh)
        auto_check.connect("toggled", toggle_auto)
        dlg.connect("destroy", lambda _w: GLib.source_remove(auto_id[0]) if auto_id[0] else None)

        dlg.show_all()
        refresh()

    # ---------------- MCE ----------------
    def _on_mce(self, _btn):
        def worker():
            return controller.ras_errors()

        def done(result):
            rc, out, err = result
            d = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK)
            if rc == 0:
                txt = out.strip() or "无记录"
                sw = Gtk.ScrolledWindow()
                sw.set_size_request(560, 320)
                buf = Gtk.TextBuffer()
                buf.set_text(txt)
                tv = Gtk.TextView(buffer=buf)
                tv.set_editable(False)
                tv.set_wrap_mode(Gtk.WrapMode.WORD)
                sw.add(tv)
                box = d.get_content_area()
                box.pack_start(sw, True, True, 0)
                d.set_markup("<b>RAS / MCE 事件</b>\n（内存错误 / PCIe AER / 机器检查）")
            else:
                d.set_markup("<b>查询失败</b>\n%s" % (err or out))
            d.show_all()
            d.run()
            d.destroy()

        run_async(worker, done)

    # ---------------- 运维工具（2026-08-31 新增）----------------
    def _show_ops_result(self, title, result, scroll=True):
        """统一结果对话框（长输出滚动显示）"""
        rc, out, err = result
        d = Gtk.MessageDialog(
            transient_for=self.get_toplevel(), modal=True,
            message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK)
        d.set_markup("<b>%s</b>" % title)
        txt = (out or "").strip() or "(无输出)"
        if err and rc != 0:
            txt += "\n\n[错误] " + err.strip()
        if scroll:
            sw = Gtk.ScrolledWindow()
            sw.set_size_request(580, 300)
            buf = Gtk.TextBuffer()
            buf.set_text(txt)
            tv = Gtk.TextView(buffer=buf)
            tv.set_editable(False)
            tv.set_wrap_mode(Gtk.WrapMode.WORD)
            sw.add(tv)
            box = d.get_content_area()
            box.pack_start(sw, True, True, 0)
        else:
            d.format_secondary_text(txt)
        d.show_all()
        d.run()
        d.destroy()

    def _on_snapshot_create(self, _btn):
        # L1/L2 操作前快照：带说明输入 + 备份盘选择
        dlg = Gtk.Dialog(title="创建系统快照", transient_for=self.get_toplevel(),
                         modal=True, default_width=520)
        box = dlg.get_content_area()
        box.set_spacing(6)
        box.set_margin_top(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        lab = Gtk.Label(label="快照说明（例如：-100mV 降压前）：", xalign=0)
        entry = Gtk.Entry()
        entry.set_width_chars(40)
        box.pack_start(lab, False, False, 6)
        box.pack_start(entry, False, False, 6)
        # 备份盘选择
        dlab = Gtk.Label(label="备份位置（默认系统盘 /dev/sdb2）：", xalign=0)
        combo = Gtk.ComboBoxText()
        combo.append("", "（默认 - 系统盘）")
        for dev, size, fstype, label, mount in controller.snapshot_devices():
            desc = "%s (%s %s%s%s)" % (dev, size, fstype or "?",
                   (" " + label) if label else "",
                   (" → " + mount) if mount else "")
            combo.append(dev, desc)
        combo.set_active(0)
        box.pack_start(dlab, False, False, 6)
        box.pack_start(combo, False, False, 6)
        note = Gtk.Label(
            label="⚠ 选 NTFS(WS) 等数据盘可能不被 timeshift 支持，建议选未挂载的 ext4/btrfs 分区。",
            xalign=0, wrap=True)
        note.get_style_context().add_class("dim-text")
        box.pack_start(note, False, False, 4)
        dlg.add_button("取消", Gtk.ResponseType.CANCEL)
        dlg.add_button("创建", Gtk.ResponseType.OK)
        dlg.show_all()
        resp = dlg.run()
        desc = entry.get_text().strip()
        target = combo.get_active_id() or ""
        dlg.destroy()
        if resp != Gtk.ResponseType.OK:
            return
        if not desc:
            desc = "控制台手动快照"

        def worker():
            return controller.snapshot("create", desc, target)

        def done(result):
            self.ops_state.set_text("快照: " + ("完成" if result[0] == 0 else "失败"))
            self._show_ops_result("系统快照", result, scroll=False)

        run_async(worker, done)

    def _on_snapshot_list(self, _btn):
        def worker():
            return controller.snapshot("list")

        def done(result):
            self._show_ops_result("Timeshift 快照列表", result)

        run_async(worker, done)

    def _on_snapshot_delete(self, _btn):
        """删除快照：先列出选择，再危险确认"""
        def worker():
            return controller.snapshot("list")

        def choose(result):
            rc, out, err = result
            if rc != 0:
                self._show_ops_result("快照列表", result, scroll=False)
                return
            # 解析快照编号与标签
            import re
            snaps = []
            for line in (out or "").splitlines():
                m = re.match(r"^(\d+)\s+>\s+(\S+)\s+(\S+)", line.strip())
                if m and m.group(3) not in ("(current)",):
                    snaps.append((m.group(1), m.group(2), line.strip()))
            if not snaps:
                self.ops_state.set_text("无快照可删除")
                return
            # 选择对话框
            dlg = Gtk.Dialog(title="选择要删除的快照", transient_for=self.get_toplevel(),
                             modal=True, default_width=560)
            box = dlg.get_content_area()
            store = Gtk.ListStore(str, str, str)
            for idx, ts, raw in snaps:
                store.append([idx, ts, raw[:70]])
            tree = Gtk.TreeView(model=store)
            for i, title in enumerate(["编号", "时间", "详情"]):
                cell = Gtk.CellRendererText()
                col = Gtk.TreeViewColumn(title, cell, text=i)
                tree.append_column(col)
            sw = Gtk.ScrolledWindow()
            sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            sw.add(tree)
            sw.set_size_request(-1, 220)
            box.pack_start(sw, True, True, 0)
            dlg.add_button("取消", Gtk.ResponseType.CANCEL)
            dlg.add_button("删除选中", Gtk.ResponseType.OK)
            dlg.show_all()
            resp = dlg.run()
            sel = tree.get_selection().get_selected()
            dlg.destroy()
            if resp != Gtk.ResponseType.OK or not sel[1]:
                return
            idx, ts = store.get(sel[1], 0, 1)
            # 危险确认
            confirm = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.NONE)
            confirm.set_markup(
                "<b>确认删除快照？</b>\n\n"
                "快照: %s (%s)\n\n"
                "⚠ 删除后无法恢复！" % (idx, ts))
            confirm.add_button("取消", Gtk.ResponseType.NO)
            b_del = confirm.add_button("永久删除", Gtk.ResponseType.YES)
            b_del.get_style_context().add_class("destructive-action")
            r2 = confirm.run()
            confirm.destroy()
            if r2 != Gtk.ResponseType.YES:
                return

            def do_delete():
                return controller.snapshot("delete", idx)

            def deleted(result):
                self.ops_state.set_text("快照: " + ("已删除" if result[0] == 0 else "失败"))
                self._show_ops_result("删除快照", result, scroll=False)

            run_async(do_delete, deleted)

        run_async(worker, choose)

    def _on_quiet(self, _btn, quiet):
        def worker():
            return controller.quiet_background(quiet)

        def done(result):
            self.ops_state.set_text(result[1].strip()[:60] if result[0] == 0 else ("失败: " + result[2][:60]))
            self._show_ops_result("后台降权" if quiet else "恢复优先级", result, scroll=False)

        run_async(worker, done)

    # ---------------- 电池温度模块 ----------------
    def _on_temp_mod(self, _btn, load):
        def worker():
            return controller.temp_module(load)

        def done(result):
            rc, out, err = result
            self.refresh_temp_state()
            d = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK)
            if rc == 0:
                d.set_markup("<b>%s</b>" % ("已加载温度模块" if load else "已卸载温度模块"))
            else:
                d.set_markup("<b>操作失败</b>（rc=%s）\n%s" % (rc, err or out))
            d.run()
            d.destroy()

        run_async(worker, done)

    def refresh_temp_state(self):
        def worker():
            import subprocess
            r = subprocess.run(["lsmod"], capture_output=True, text=True)
            return "已加载" if "acer_wmi_battery" in r.stdout else "未加载"

        def done(s):
            self.temp_state.set_text(s)

        run_async(worker, done)

    # ---------------- 状态刷新（console tick 调用）----------------
    def refresh_state(self, d=None):
        pass  # 维护页无实时数据需求，服务状态手动刷新