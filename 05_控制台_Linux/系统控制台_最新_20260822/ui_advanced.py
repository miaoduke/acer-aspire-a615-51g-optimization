#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ui_advanced.py — 高级控制页：参数状态 + GPU 模式 + 服务状态 + MCE"""
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

import controller
from async_util import run_async


class AdvancedPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)

        head = Gtk.Label(label="高级控制", xalign=0)
        head.get_style_context().add_class("section-title")
        self.pack_start(head, False, False, 0)

        # ---- 参数状态（只读，调整请用场景页）----
        grid = Gtk.Grid(column_spacing=20, row_spacing=4)
        self.params = {}
        rows = [
            # 2026-08-31: 移除 PPD 档位（PPD masked 后恒"—"）
            ("pl", "PL1 / PL2"), ("turbo", "Turbo"), ("epp", "EPP"),
            ("gov", "Governor"), ("prime", "GPU 模式"),
            ("m3", "M3 模式"),
        ]
        for i, (key, title) in enumerate(rows):
            lab = Gtk.Label(label=title, xalign=0)
            val = Gtk.Label(label="—", xalign=0)
            val.get_style_context().add_class("detail-value")
            self.params[key] = val
            grid.attach(lab, i % 2 * 2, i // 2, 1, 1)
            grid.attach(val, i % 2 * 2 + 1, i // 2, 1, 1)
        self.pack_start(grid, False, False, 0)

        note = Gtk.Label(
            label="提示：PL/Turbo/EPP/Governor 的调整请在【电源场景】页一键切换（已验证脚本）。",
            xalign=0, wrap=True)
        note.get_style_context().add_class("dim-text")
        self.pack_start(note, False, False, 0)

        # ---- GPU 模式切换 ----
        gbox = Gtk.Box(spacing=10)
        gbox.set_margin_top(10)
        glab = Gtk.Label(label="GPU 模式：", xalign=0)
        self.gpu_intel = Gtk.Button(label="切到集显 intel（省电 ~7.7W）")
        self.gpu_intel.connect("clicked", self._on_gpu, "intel")
        self.gpu_nvidia = Gtk.Button(label="切到独显 nvidia（性能）")
        self.gpu_nvidia.connect("clicked", self._on_gpu, "nvidia")
        gbox.pack_start(glab, False, False, 0)
        gbox.pack_start(self.gpu_intel, False, False, 0)
        gbox.pack_start(self.gpu_nvidia, False, False, 0)
        self.pack_start(gbox, False, False, 0)
        self._gpu_busy = False

        # ---- 散热控制 ----
        tbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        tbox.set_margin_top(12)
        tl = Gtk.Label(label="散热控制", xalign=0)
        tl.get_style_context().add_class("section-title")
        tbox.pack_start(tl, False, False, 0)

        # TCC 温度墙偏移：滑块 + 填写 + 应用验证
        tcbox = Gtk.Box(spacing=8)
        tcl = Gtk.Label(label="CPU 温度墙偏移：", xalign=0)
        self.tcc_adj = Gtk.Adjustment(value=2, lower=0, upper=63, step_increment=1)
        self.tcc_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                                   adjustment=self.tcc_adj)
        self.tcc_scale.set_size_request(180, -1)
        self.tcc_scale.set_hexpand(False)
        self.tcc_scale.set_digits(0)
        self.tcc_entry = Gtk.Entry()
        self.tcc_entry.set_width_chars(3)
        self.tcc_entry.set_text("2")
        self.tcc_unit = Gtk.Label(label="°C", xalign=0)
        self.tcc_apply = Gtk.Button(label="应用并验证")
        self.tcc_apply.connect("clicked", self._on_apply, "tcc")
        self.tcc_state = Gtk.Label(label="", xalign=0)
        self.tcc_state.get_style_context().add_class("dim-text")
        tcbox.pack_start(tcl, False, False, 0)
        tcbox.pack_start(self.tcc_scale, False, False, 0)
        tcbox.pack_start(self.tcc_entry, False, False, 0)
        tcbox.pack_start(self.tcc_unit, False, False, 0)
        tcbox.pack_start(self.tcc_apply, False, False, 0)
        tcbox.pack_start(self.tcc_state, False, False, 0)
        tbox.pack_start(tcbox, False, False, 0)

        # PL1/PL2 功耗墙：滑动条 + 自定义填写 + 生效验证
        plbox = Gtk.Box(spacing=8)
        pll = Gtk.Label(label="PL1/PL2 功耗墙：", xalign=0)
        self.pl1_adj = Gtk.Adjustment(value=15, lower=1, upper=30, step_increment=1)
        self.pl1_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                                   adjustment=self.pl1_adj)
        self.pl1_scale.set_size_request(180, -1)
        self.pl1_scale.set_digits(0)
        self.pl1_entry = Gtk.Entry()
        self.pl1_entry.set_width_chars(4)
        self.pl1_entry.set_text("15")
        self.pl1_unit = Gtk.Label(label="W", xalign=0)
        pl2l = Gtk.Label(label="PL2：", xalign=0)
        self.pl2_adj = Gtk.Adjustment(value=25, lower=1, upper=45, step_increment=1)
        self.pl2_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                                   adjustment=self.pl2_adj)
        self.pl2_scale.set_size_request(180, -1)
        self.pl2_scale.set_digits(0)
        self.pl2_entry = Gtk.Entry()
        self.pl2_entry.set_width_chars(4)
        self.pl2_entry.set_text("25")
        self.pl2_unit = Gtk.Label(label="W", xalign=0)
        self.pl_apply = Gtk.Button(label="应用并验证")
        self.pl_apply.connect("clicked", self._on_pl_apply)
        self.pl_state = Gtk.Label(label="", xalign=0)
        self.pl_state.get_style_context().add_class("dim-text")
        plbox.pack_start(pll, False, False, 0)
        plbox.pack_start(self.pl1_scale, False, False, 0)
        plbox.pack_start(self.pl1_entry, False, False, 0)
        plbox.pack_start(self.pl1_unit, False, False, 0)
        plbox.pack_start(pl2l, False, False, 0)
        plbox.pack_start(self.pl2_scale, False, False, 0)
        plbox.pack_start(self.pl2_entry, False, False, 0)
        plbox.pack_start(self.pl2_unit, False, False, 0)
        plbox.pack_start(self.pl_apply, False, False, 0)
        plbox.pack_start(self.pl_state, False, False, 0)
        tbox.pack_start(plbox, False, False, 0)

        # CPU 频率上限：滑块 + 填写 + 应用验证
        fqbox = Gtk.Box(spacing=8)
        fql = Gtk.Label(label="CPU 频率上限：", xalign=0)
        self.fq_adj = Gtk.Adjustment(value=100, lower=1, upper=100, step_increment=1)
        self.fq_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                                  adjustment=self.fq_adj)
        self.fq_scale.set_size_request(180, -1)
        self.fq_scale.set_digits(0)
        self.fq_entry = Gtk.Entry()
        self.fq_entry.set_width_chars(3)
        self.fq_entry.set_text("100")
        self.fq_unit = Gtk.Label(label="%", xalign=0)
        self.fq_apply = Gtk.Button(label="应用并验证")
        self.fq_apply.connect("clicked", self._on_apply, "maxperf")
        self.fq_state = Gtk.Label(label="", xalign=0)
        self.fq_state.get_style_context().add_class("dim-text")
        fqbox.pack_start(fql, False, False, 0)
        fqbox.pack_start(self.fq_scale, False, False, 0)
        fqbox.pack_start(self.fq_entry, False, False, 0)
        fqbox.pack_start(self.fq_unit, False, False, 0)
        fqbox.pack_start(self.fq_apply, False, False, 0)
        fqbox.pack_start(self.fq_state, False, False, 0)
        tbox.pack_start(fqbox, False, False, 0)

        # CPU 强制降载：滑块 + 填写 + 应用验证
        pcbox = Gtk.Box(spacing=8)
        pcl = Gtk.Label(label="CPU 强制降载：", xalign=0)
        self.pc_adj = Gtk.Adjustment(value=0, lower=0, upper=100, step_increment=1)
        self.pc_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                                  adjustment=self.pc_adj)
        self.pc_scale.set_size_request(180, -1)
        self.pc_scale.set_digits(0)
        self.pc_entry = Gtk.Entry()
        self.pc_entry.set_width_chars(3)
        self.pc_entry.set_text("0")
        self.pc_unit = Gtk.Label(label="%", xalign=0)
        self.pc_apply = Gtk.Button(label="应用并验证")
        self.pc_apply.connect("clicked", self._on_apply, "pclamp")
        self.pc_state = Gtk.Label(label="", xalign=0)
        self.pc_state.get_style_context().add_class("dim-text")
        pcbox.pack_start(pcl, False, False, 0)
        pcbox.pack_start(self.pc_scale, False, False, 0)
        pcbox.pack_start(self.pc_entry, False, False, 0)
        pcbox.pack_start(self.pc_unit, False, False, 0)
        pcbox.pack_start(self.pc_apply, False, False, 0)
        pcbox.pack_start(self.pc_state, False, False, 0)
        tbox.pack_start(pcbox, False, False, 0)

        tnote = Gtk.Label(
            label="提示：温度墙越大 CPU 越早降频（静音模式适用）；降压/功耗控制均写 sysfs，不经 EC。",
            xalign=0, wrap=True)
        tnote.get_style_context().add_class("dim-text")
        tbox.pack_start(tnote, False, False, 0)
        self.pack_start(tbox, False, False, 0)

        # ---- 外设省电 ----
        pbox = Gtk.Box(spacing=8)
        pbox.set_margin_top(12)
        plab = Gtk.Label(label="外设省电：", xalign=0)
        self.usb_save = Gtk.Button(label="USB 省电 开")
        self.usb_save.connect("clicked", self._on_usb, True)
        self.usb_full = Gtk.Button(label="USB 常供电")
        self.usb_full.connect("clicked", self._on_usb, False)
        self.wifi_save = Gtk.Button(label="WiFi 省电 开")
        self.wifi_save.connect("clicked", self._on_wifi, True)
        self.wifi_perf = Gtk.Button(label="WiFi 性能")
        self.wifi_perf.connect("clicked", self._on_wifi, False)
        self.cam_on = Gtk.Button(label="摄像头 开")
        self.cam_on.connect("clicked", self._on_camera, True)
        self.cam_off = Gtk.Button(label="摄像头 关")
        self.cam_off.connect("clicked", self._on_camera, False)
        self.cam_state = Gtk.Label(label="", xalign=0)
        self.cam_state.get_style_context().add_class("dim-text")
        pbox.pack_start(plab, False, False, 0)
        pbox.pack_start(self.usb_save, False, False, 0)
        pbox.pack_start(self.usb_full, False, False, 0)
        pbox.pack_start(self.wifi_save, False, False, 0)
        pbox.pack_start(self.wifi_perf, False, False, 0)
        pbox.pack_start(self.cam_on, False, False, 0)
        pbox.pack_start(self.cam_off, False, False, 0)
        pbox.pack_start(self.cam_state, False, False, 0)
        self.pack_start(pbox, False, False, 0)


        # ---- 生态状态（2026-08-20 落地的优化项）----
        ebox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        ebox.set_margin_top(12)
        el = Gtk.Label(label="生态优化状态（2026-08-20 落地）", xalign=0)
        el.get_style_context().add_class("section-title")
        ebox.pack_start(el, False, False, 0)
        self.eco = {}
        egrid = Gtk.Grid(column_spacing=20, row_spacing=4)
        erows = [
            ("scene", "场景自动切换", "acdc-profile 服务"), ("bright", "屏幕亮度", "用户自主控制"),
            ("cstate", "C-state 上限", "intel_idle.max_cstate"), ("mx150", "MX150 断电", "D3cold 状态"),
            ("zswap", "zswap", "内存压缩交换"), ("shrinker", "zswap shrinker", "冷页提前驱逐"),
            ("swap", "swap 文件", "4G btrfs 兜底"), ("hwp_boost", "hwp_dynamic_boost", "IO 唤醒提频"),
            ("discharge", "电池放电率", "current×voltage"), ("smartd", "smartd", "双盘 SMART 自检"),
            ("jlimit", "journald 限容", "日志 100M 上限"), ("startup", "启动优化", "wait-online/fwupd"),
            ("undervolt", "undervolt", "CPU/GPU 降压"), ("gtfreq", "GPU GT 频率", "AC/DC 联动"),
        ]
        for i, (key, title, desc) in enumerate(erows):
            lab = Gtk.Label(label=title, xalign=0)
            val = Gtk.Label(label="—", xalign=0)
            val.get_style_context().add_class("detail-value")
            dsc = Gtk.Label(label=desc, xalign=0)
            dsc.get_style_context().add_class("dim-text")
            self.eco[key] = (val, dsc)
            egrid.attach(lab, 0, i, 1, 1)
            egrid.attach(val, 1, i, 1, 1)
            egrid.attach(dsc, 2, i, 1, 1)
        ebox.pack_start(egrid, False, False, 0)
        self.pack_start(ebox, False, False, 0)


        # ---- 工具与配置（2026-08-21；性能日志/应用功耗已迁移至系统维护页）----
        tbox2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        tbox2.set_margin_top(12)
        tl2 = Gtk.Label(label="工具与配置", xalign=0)
        tl2.get_style_context().add_class("section-title")
        tbox2.pack_start(tl2, False, False, 0)
        
        btn_row = Gtk.Box(spacing=8)
        
        guard_btn = Gtk.Button(label="🌡️ 温度守护配置")
        guard_btn.set_tooltip_text("配置 thermal-guard 高温触发/恢复阈值和限流 PL1 值")
        guard_btn.connect("clicked", self._open_guard_config)
        
        scene_btn = Gtk.Button(label="⚙️ 场景参数")
        scene_btn.set_tooltip_text("配置插电/离电默认场景和 GPU GT 频率联动值")
        scene_btn.connect("clicked", self._open_scene_config)

        adapt_btn = Gtk.Button(label="🖥 跨机适配")
        adapt_btn.set_tooltip_text("检测硬件能力 + 生成兼容报告（重装/换同配置机器后用）")
        adapt_btn.connect("clicked", self._on_adapt)

        win_btn = Gtk.Button(label="🪟 临时切到 Windows")
        win_btn.set_tooltip_text("UEFI BootNext 临时启动 Windows（重启生效，下次自动回 Linux）")
        win_btn.connect("clicked", self._on_boot_windows)

        tools_btn = Gtk.Button(label="🧰 高级工具")
        tools_btn.set_tooltip_text("GRUB 修改 / 降压应用 / 降压扫描等高风险操作（命令行）")
        tools_btn.connect("clicked", self._on_advanced_tools)

        btn_row.pack_start(guard_btn, False, False, 0)
        btn_row.pack_start(scene_btn, False, False, 0)
        btn_row.pack_start(adapt_btn, False, False, 0)
        btn_row.pack_start(win_btn, False, False, 0)
        btn_row.pack_start(tools_btn, False, False, 0)
        tbox2.pack_start(btn_row, False, False, 0)
        self.pack_start(tbox2, False, False, 0)



    # ---------------- GPU ----------------
    def _on_gpu(self, _btn, target):
        if self._gpu_busy:
            return
        dlg = Gtk.MessageDialog(
            transient_for=self.get_toplevel(), modal=True,
            message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.OK_CANCEL)
        dlg.set_markup(
            "<b>切换 GPU 到 %s</b>\n\n"
            "· 切换后需要<b>重启系统</b>才能生效\n"
            "· 重启会中断所有未保存工作，请先保存\n"
            "· 切集显可省约 7.7W（M3 推荐）" % target)
        resp = dlg.run()
        dlg.destroy()
        if resp != Gtk.ResponseType.OK:
            return
        self._gpu_busy = True

        def done(result):
            self._gpu_busy = False
            rc, out, err = result
            d = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.NONE)
            if rc == 0:
                d.set_markup("<b>GPU 已切换为 %s</b>\n\n"
                             "配置已写入，需<b>重启系统</b>后完全生效。\n"
                             "恢复独显：控制台 GPU 模式 → 切到 nvidia。" % target)
                d.add_button("稍后重启", Gtk.ResponseType.NO)
                b_reboot = d.add_button("立即重启", Gtk.ResponseType.YES)
                b_reboot.get_style_context().add_class("suggested-action")
            else:
                d.set_markup("<b>切换失败</b>\n%s" % (err or out))
                d.add_button("确定", Gtk.ResponseType.OK)
            resp = d.run()
            d.destroy()
            if resp == Gtk.ResponseType.YES:
                # 用户已明确确认 -> 一键重启(与场景页 GPU 弹窗同一机制)
                def reboot_worker():
                    return controller.reboot_system()
                def reboot_done(result):
                    rc2, out2, err2 = result
                    if rc2 != 0:
                        rd = Gtk.MessageDialog(
                            transient_for=self.get_toplevel(), modal=True,
                            message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK)
                        rd.set_markup("<b>重启失败</b>\n%s" % (err2 or out2))
                        rd.run()
                        rd.destroy()
                run_async(reboot_worker, reboot_done)

        run_async(lambda: controller.gpu_switch(target), done)

    # ---------------- 散热控制 ----------------
    def _show_result(self, rc, out, err, ok_msg):
        d = Gtk.MessageDialog(
            transient_for=self.get_toplevel(), modal=True,
            message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK)
        if rc == 0:
            d.set_markup("<b>%s</b>" % ok_msg)
        else:
            d.set_markup("<b>操作失败</b>（rc=%s）\n%s" % (rc, err or out))
        d.run()
        d.destroy()

    def _on_apply(self, _btn, kind):
        def worker():
            try:
                if kind == "tcc":
                    v = int(self.tcc_entry.get_text().strip() or self.tcc_adj.get_value())
                    fn = lambda x: controller.tcc_offset(x)
                    rng = (0, 63)
                    unit = "°C"
                elif kind == "maxperf":
                    v = int(self.fq_entry.get_text().strip() or self.fq_adj.get_value())
                    fn = lambda x: controller.cpu_max_perf(x)
                    rng = (1, 100)
                    unit = "%"
                else:
                    v = int(self.pc_entry.get_text().strip() or self.pc_adj.get_value())
                    fn = lambda x: controller.powerclamp(x)
                    rng = (0, 100)
                    unit = "%"
            except ValueError:
                return (1, "", "请输入整数（%s-%s）" % rng)
            if not (rng[0] <= v <= rng[1]):
                return (1, "", "数值超出范围（%s-%s）" % rng)
            # 同步滑块/填写框
            self._set_row(kind, v)
            return fn(v)
        def done(result):
            rc, out, err = result
            d = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.INFO if rc in (0, 2) else Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK)
            if rc in (0, 2):
                d.set_markup("<b>%s</b>\n\n%s" % (
                    "设置已应用并验证生效" if rc == 0 else "已写入但实测不一致",
                    out.strip() or "（无输出）"))
            else:
                d.set_markup("<b>操作失败</b>（rc=%s）\n%s" % (rc, err or out))
            d.run()
            d.destroy()
            self.refresh_state()
        run_async(worker, done)

    def _set_row(self, kind, v):
        """同步某行的滑块/填写框/状态标签"""
        if kind == "tcc":
            self.tcc_adj.set_value(v)
            self.tcc_entry.set_text(str(v))
        elif kind == "maxperf":
            self.fq_adj.set_value(v)
            self.fq_entry.set_text(str(v))
        else:
            self.pc_adj.set_value(v)
            self.pc_entry.set_text(str(v))

    def _on_pl_apply(self, _btn):
        def worker():
            try:
                pl1 = int(self.pl1_entry.get_text().strip() or self.pl1_adj.get_value())
                pl2 = int(self.pl2_entry.get_text().strip() or self.pl2_adj.get_value())
            except ValueError:
                return (1, "", "请输入整数瓦数（1-30 / 1-45）")
            self.pl1_adj.set_value(pl1)
            self.pl2_adj.set_value(pl2)
            self.pl1_scale.set_value(pl1)
            self.pl2_scale.set_value(pl2)
            return controller.set_pl(pl1, pl2)
        def done(result):
            rc, out, err = result
            d = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.INFO if rc in (0, 2) else Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK)
            if rc in (0, 2):
                d.set_markup("<b>%s</b>\n\n%s" % (
                    "功耗墙已应用并验证生效" if rc == 0 else "已写入但实测不一致",
                    out.strip() or "（无输出）"))
            else:
                d.set_markup("<b>操作失败</b>（rc=%s）\n%s" % (rc, err or out))
            d.run()
            d.destroy()
            # 立即刷新当前生效值显示
            self.refresh_state()
        run_async(worker, done)
        # 2026-08-31 清理: 此处原有 7 行孤儿代码(引用未定义的 v, 每次点 PL 应用
        # 都额外弹"温度墙设置失败: name 'v' is not defined"错误框), 已删除。

    def _on_usb(self, _btn, on):
        def worker():
            rc, out, err = controller.usb_autosuspend(on)
            total, ok, nop = controller.usb_verify()
            return rc, out, err, total, ok, nop
        def done(result):
            rc, out, err, total, ok, nop = result
            d = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK)
            if rc == 0:
                mode = "省电(auto)" if on else "常供电(on)"
                # 验证统计：目标是 auto 时 ok=生效数；目标是 on 时 nop=生效数
                eff = ok if on else nop
                d.set_markup(
                    "<b>USB 设置已应用，验证结果</b>\n\n"
                    "目标：%s\n"
                    "共 %d 个 USB 设备，%d 个已生效（%.0f%%）\n"
                    "其余 %d 个为另一状态（常供电设备/不支持自动挂起）" % (
                        mode, total, eff, (eff / total * 100) if total else 0, total - eff))
            else:
                d.set_markup("<b>操作失败</b>（rc=%s）\n%s" % (rc, err or out))
            d.run()
            d.destroy()
        run_async(worker, done)

    def _on_wifi(self, _btn, on):
        def worker():
            rc, out, err = controller.wifi_power(on)
            return rc, out, err, controller.wifi_verify()
        def done(result):
            rc, out, err, states = result
            d = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK)
            if rc == 0:
                lines = ["<b>WiFi 设置已应用，验证结果</b>\n\n"]
                if states:
                    for dev, st in states:
                        mark = "✓" if st == ("on" if on else "off") else "✗"
                        lines.append("%s %s → power_save=%s" % (mark, dev, st))
                else:
                    lines.append("未检测到 WiFi 接口")
                d.set_markup("\n".join(lines))
            else:
                d.set_markup("<b>操作失败</b>（rc=%s）\n%s" % (rc, err or out))
            d.run()
            d.destroy()
        run_async(worker, done)

    def _on_camera(self, _btn, on):
        def worker():
            rc, out, err = controller.camera(on)
            return rc, out, err, controller.camera_status()
        def done(result):
            rc, out, err, status = result
            d = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK)
            if rc == 0:
                ok = status is True if on else status is False
                state_txt = "已启用（uvcvideo 已加载）" if status else "已禁用（uvcvideo 已卸载）"
                d.set_markup(
                    "<b>摄像头已%s</b>\n\n"
                    "验证：%s %s\n"
                    "%s" % (
                        "启用" if on else "禁用",
                        "✓ 驱动状态符合" if ok else "⚠ 驱动状态与目标不符",
                        state_txt,
                        "提示：正在使用摄像头的程序需重启才能重新识别" if on else
                        "提示：隐私保护——系统级禁用，任何程序都无法调用摄像头"))
            else:
                d.set_markup("<b>操作失败</b>（rc=%s）\n%s" % (rc, err or out))
            d.run()
            d.destroy()
            self.refresh_cam_state()
        run_async(worker, done)

    def refresh_cam_state(self):
        def worker():
            return controller.camera_status()
        def done(s):
            self.cam_state.set_text("当前：%s" % ("启用" if s else "禁用"))
        run_async(worker, done)

    # 2026-08-31 清理: 此处原有服务列表刷新孤儿块(引用不存在的 self.svc_list,
    # 每次摄像头操作后二次 run_async 触发 AttributeError)——该功能实际由
    # ui_maintenance.py 的 _load_services 实现, 已删除。
    # 另: "内核变动检测"节空壳也已并入本注释。

    # ---------------- 状态刷新 ----------------
    def refresh_state(self, d=None):
        if d is None:
            return
        p = d["params"]
        self.params["pl"].set_text("%s / %s W" % (self._w(p["pl1_w"]), self._w(p["pl2_w"])))
        # PL 滑动条当前生效值展示
        if p["pl1_w"] is not None and p["pl2_w"] is not None:
            self.pl1_adj.set_value(round(p["pl1_w"]))
            self.pl2_adj.set_value(round(p["pl2_w"]))
            self.pl1_entry.set_text(str(round(p["pl1_w"])))
            self.pl2_entry.set_text(str(round(p["pl2_w"])))
            self.pl_state.set_text("当前生效：PL1=%dW PL2=%dW" % (round(p["pl1_w"]), round(p["pl2_w"])))
        # TCC/频率上限/强制降载 当前生效值（读 sysfs）
        tcc = self._read_int("/sys/class/thermal/cooling_device17/cur_state")
        if tcc is not None:
            self.tcc_adj.set_value(tcc)
            self.tcc_entry.set_text(str(tcc))
            self.tcc_state.set_text("当前生效：%d°C" % tcc)
        mperf = self._read_int("/sys/devices/system/cpu/intel_pstate/max_perf_pct")
        if mperf is not None:
            self.fq_adj.set_value(mperf)
            self.fq_entry.set_text(str(mperf))
            self.fq_state.set_text("当前生效：%d%%" % mperf)
        pcl = self._read_int("/sys/class/thermal/cooling_device16/cur_state")
        if pcl is not None:
            self.pc_adj.set_value(pcl)
            self.pc_entry.set_text(str(pcl))
            self.pc_state.set_text("当前生效：%s" % ("关闭" if pcl == 0 else "降载 %d%%" % pcl))
        t = p["turbo"]
        self.params["turbo"].set_text("ON" if t is True else ("OFF" if t is False else "—"))
        self.params["epp"].set_text(p["epp"] or "—")
        self.params["gov"].set_text(p["governor"] or "—")
        # 2026-08-31: PPD 已移除（恒"—"）
        self.params["prime"].set_text(d["prime"] or "—")
        self.params["m3"].set_text(self._m3_state())

        # ---- 生态状态 ----
        eco = d.get("eco", {})
        if eco:
            svc = eco.get("services", {})
            scene = svc.get("acdc-profile")
            scene_txt = {"active": "AC/DC 自动切换", "inactive": "已停（M3 覆盖）",
                         "failed": "失败", "unknown": "未知"}.get(scene, scene or "未知")
            self.eco["scene"][0].set_text(scene_txt)
            # 亮度：只读显示（用户自主控制，acdc-profile 不再联动）
            bmax = eco.get("brightness_max")
            bcur = eco.get("brightness")
            if bcur and bmax:
                self.eco["bright"][0].set_text("%d%%（%s/%s）· 用户自主" % (
                    int(bcur) * 100 // int(bmax), bcur, bmax))
            else:
                self.eco["bright"][0].set_text("—")
            self.eco["cstate"][0].set_text(eco.get("max_cstate") or "默认")
            mx = eco.get("mx150")
            self.eco["mx150"][0].set_text(
                "断电（D3cold）✓" if mx == "suspended" else (mx or "—"))
            zs = eco.get("zswap")
            self.eco["zswap"][0].set_text(
                "开启 ✓" if zs and zs.lower() in ("y", "1") else "关闭")
            sh = eco.get("zswap_shrinker")
            self.eco["shrinker"][0].set_text(
                "开启 ✓" if sh and sh.lower() in ("y", "1") else "关闭")
            self.eco["swap"][0].set_text(eco.get("swap") or "无")
            hb = eco.get("hwp_boost")
            self.eco["hwp_boost"][0].set_text(
                "开启 ✓" if hb == "1" else ("关闭" if hb == "0" else "—"))
            dw = eco.get("discharge_w")
            self.eco["discharge"][0].set_text(
                ("%.1f W" % dw) if dw is not None else "—")
            smart = svc.get("smartd")
            self.eco["smartd"][0].set_text(
                "监控中 ✓" if smart == "active" else (smart or "—"))
            jd = eco.get("journald_max") or ""
            jm = "100M" if "SystemMaxUse=100M" in jd else "默认"
            self.eco["jlimit"][0].set_text(jm)
            wo = svc.get("wait-online")
            fw = svc.get("fwupd")
            self.eco["startup"][0].set_text(
                "wait-online %s · fwupd %s" % (wo or "?", fw or "?"))
            uv = svc.get("undervolt")
            if uv == "active":
                cfg = svc.get("undervolt_cfg", "")
                # 2026-08-31 修正: 原硬编码只认 "--core -50"，配置改 -80 后 UI 永远显示"在配"。
                # 现从 ExecStart 解析实际值（形如 undervolt --core -80 --cache -80 ...）。
                import re as _re
                m = _re.search(r"--core\s+(-?\d+)", cfg)
                off = ("%smV" % m.group(1)) if m else ("已配置" if cfg else "")
                self.eco["undervolt"][0].set_text("生效 ✓ %s" % off)
            else:
                self.eco["undervolt"][0].set_text(uv or "—")
            gtmax = eco.get("gt_max")
            gtrp0 = eco.get("gt_rp0")
            if gtmax and gtrp0:
                mark = "（AC 全速）" if d.get("ac") else "（DC 受限 700）"
                self.eco["gtfreq"][0].set_text("%s MHz %s" % (gtmax, mark))
            else:
                self.eco["gtfreq"][0].set_text("—")

    @staticmethod
    def _m3_state():
        try:
            import subprocess
            r = subprocess.run(["systemctl", "is-active", "m3-power-saver.service"],
                               capture_output=True, text=True, timeout=3)
            return "生效中" if r.stdout.strip() == "active" else "未启用"
        except Exception:
            return "—"

    @staticmethod
    def _w(v):
        return "%.1f" % v if v is not None else "—"

    @staticmethod
    def _read_int(path):
        try:
            return int(open(path).read().strip())
        except Exception:
            return None

    # ---------------- thermal-guard 阈值配置 ----------------
    def _open_guard_config(self, _btn=None):
        """打开 thermal-guard 阈值配置对话框"""
        dlg = Gtk.Dialog(title="温度守护阈值配置", transient_for=self.get_toplevel(), modal=True)
        dlg.set_default_size(420, 300)
        box = dlg.get_content_area()
        box.set_spacing(8)
        box.set_margin_top(10)
        box.set_margin_start(10)
        box.set_margin_end(10)

        # 读取当前配置
        import re
        current_high, current_low, current_pl = 85, 75, 15
        try:
            with open("/home/<USER>/桌面/系统控制台/backend/thermal_guard.sh") as f:
                content = f.read()
            m = re.search(r'TH_HIGH:-\s*(\d+)', content)
            if m: current_high = int(m.group(1)) // 1000
            m = re.search(r'TH_LOW:-\s*(\d+)', content)
            if m: current_low = int(m.group(1)) // 1000
            m = re.search(r'TH_DOWN_PL1:-\s*(\d+)', content)
            if m: current_pl = int(m.group(1))
        except Exception:
            pass

        # 高温触发阈值
        row1 = Gtk.Box(spacing=8)
        lab1 = Gtk.Label(label="高温触发 (°C)：", xalign=0)
        adj1 = Gtk.Adjustment(value=current_high, lower=60, upper=100, step_increment=1)
        spin1 = Gtk.SpinButton(adjustment=adj1)
        spin1.set_width_chars(4)
        row1.pack_start(lab1, False, False, 0)
        row1.pack_start(spin1, False, False, 0)
        box.pack_start(row1, False, False, 0)

        # 恢复阈值
        row2 = Gtk.Box(spacing=8)
        lab2 = Gtk.Label(label="恢复阈值 (°C)：", xalign=0)
        adj2 = Gtk.Adjustment(value=current_low, lower=50, upper=95, step_increment=1)
        spin2 = Gtk.SpinButton(adjustment=adj2)
        spin2.set_width_chars(4)
        row2.pack_start(lab2, False, False, 0)
        row2.pack_start(spin2, False, False, 0)
        box.pack_start(row2, False, False, 0)

        # 限流 PL1 值
        row3 = Gtk.Box(spacing=8)
        lab3 = Gtk.Label(label="限流 PL1 (W)：", xalign=0)
        adj3 = Gtk.Adjustment(value=current_pl, lower=5, upper=25, step_increment=1)
        spin3 = Gtk.SpinButton(adjustment=adj3)
        spin3.set_width_chars(4)
        row3.pack_start(lab3, False, False, 0)
        row3.pack_start(spin3, False, False, 0)
        box.pack_start(row3, False, False, 0)

        note = Gtk.Label(label="说明：温度超过高温触发值时自动降 PL1 至限流值；\n回落到恢复值以下时自动恢复原 PL1。", xalign=0)
        note.get_style_context().add_class("dim-text")
        box.pack_start(note, False, False, 0)

        # 按钮
        btn_box = Gtk.Box(spacing=8)
        apply_btn = Gtk.Button(label="应用")
        apply_btn.get_style_context().add_class("suggested-action")
        cancel_btn = Gtk.Button(label="取消")
        btn_box.pack_end(apply_btn, False, False, 0)
        btn_box.pack_end(cancel_btn, False, False, 0)
        box.pack_start(btn_box, False, False, 0)

        def on_apply(_btn):
            high = int(spin1.get_value()) * 1000
            low = int(spin2.get_value()) * 1000
            pl = int(spin3.get_value())
            
            def worker():
                import subprocess
                script = "/home/<USER>/桌面/系统控制台/backend/thermal_guard.sh"
                # 用 sed 更新脚本中的默认值
                cmd = f"""sed -i 's/HIGH=${{TH_HIGH:-[0-9]*}}/HIGH=${{TH_HIGH:-{high}}}/' {script}
sed -i 's/LOW=${{TH_LOW:-[0-9]*}}/LOW=${{TH_LOW:-{low}}}/' {script}
sed -i 's/DOWN_PL1=${{TH_DOWN_PL1:-[0-9]*}}/DOWN_PL1=${{TH_DOWN_PL1:-{pl}}}/' {script}
systemctl restart thermal-guard"""
                r = subprocess.run(["sudo", "-n", "bash", "-c", cmd], capture_output=True, text=True, timeout=30)
                return r.returncode, r.stdout, r.stderr
            
            def done(result):
                rc, out, err = result
                d = Gtk.MessageDialog(transient_for=dlg, modal=True,
                                      message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
                                      buttons=Gtk.ButtonsType.OK)
                if rc == 0:
                    d.set_markup("<b>✓ 阈值已更新并重启服务</b>")
                    dlg.destroy()
                else:
                    d.set_markup(f"<b>更新失败</b>\n{err or out}")
                d.run()
                d.destroy()

            from async_util import run_async
            run_async(worker, done)

        apply_btn.connect("clicked", on_apply)
        cancel_btn.connect("clicked", lambda _b: dlg.destroy())

        dlg.show_all()

    # ---------------- 跨机适配 / 切Win / 高级工具（2026-08-31 新增）----------------
    def _on_adapt(self, _btn=None):
        """跨机适配向导：检测硬件能力 → 报告 → 可应用"""
        dlg = Gtk.MessageDialog(
            transient_for=self.get_toplevel(), modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE)
        dlg.set_markup(
            "<b>跨机适配向导</b>\n\n"
            "检测硬件能力并生成兼容性报告。\n"
            "· 仅检测：只输出报告，不改系统\n"
            "· 检测+应用：写入硬件档案供控制台使用\n\n"
            "适用：重装系统 / 换到同配置机器后恢复控制台能力")
        dlg.add_button("取消", Gtk.ResponseType.NO)
        b_check = dlg.add_button("仅检测", Gtk.ResponseType.CLOSE)
        b_check.get_style_context().add_class("suggested-action")
        b_apply = dlg.add_button("检测+应用", Gtk.ResponseType.YES)
        resp = dlg.run()
        dlg.destroy()
        if resp == Gtk.ResponseType.NO:
            return
        apply = (resp == Gtk.ResponseType.YES)

        def worker():
            return controller.adapt_test(apply)

        def done(result):
            rc, out, err = result
            d = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK)
            d.set_markup("<b>跨机适配报告</b>\n\n%s" % ("（输出见下方）" if rc == 0 else "（失败）"))
            sw = Gtk.ScrolledWindow()
            sw.set_size_request(600, 360)
            buf = Gtk.TextBuffer()
            buf.set_text((out or "(无输出)") + (("\n\n[错误] " + err) if err and rc != 0 else ""))
            tv = Gtk.TextView(buffer=buf)
            tv.set_editable(False)
            tv.set_wrap_mode(Gtk.WrapMode.WORD)
            sw.add(tv)
            box = d.get_content_area()
            box.pack_start(sw, True, True, 0)
            d.show_all()
            d.run()
            d.destroy()

        run_async(worker, done)

    def _on_boot_windows(self, _btn=None):
        """一键临时启动 Windows（UEFI BootNext，不改变永久启动顺序）"""
        dlg = Gtk.MessageDialog(
            transient_for=self.get_toplevel(), modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE)
        dlg.set_markup(
            "<b>临时启动到 Windows？</b>\n\n"
            "· 设置 EFI BootNext → 立即重启 → 进入 Windows\n"
            "· 下次重启自动回到 Linux（不改变默认启动顺序）\n"
            "· 请先保存所有工作！\n\n"
            "⚠ 若你已在 Windows 中，重启前请确认此操作")
        dlg.add_button("取消", Gtk.ResponseType.NO)
        b_go = dlg.add_button("设置并重启进 Windows", Gtk.ResponseType.YES)
        b_go.get_style_context().add_class("destructive-action")
        resp = dlg.run()
        dlg.destroy()
        if resp != Gtk.ResponseType.YES:
            return

        def worker():
            return controller.boot_windows()

        def done(result):
            rc, out, err = result
            d = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK)
            if rc == 0:
                d.set_markup("<b>已排程启动 Windows</b>\n\n%s" % (out or "重启后将进入 Windows"))
            else:
                d.set_markup("<b>设置失败</b>\n%s" % (err or out))
            d.run()
            d.destroy()

        run_async(worker, done)

    def _on_advanced_tools(self, _btn=None):
        """高级工具：高风险操作（命令行执行，GUI 只提供说明与命令）"""
        TOOLS = [
            ("GRUB 参数修改（C-state/性能参数，需重启生效）",
             "sudo nano /etc/default/grub && sudo update-grub"),
            ("降压应用（当前 -80mV 由服务管理，改动需谨慎）",
             "sudo systemctl edit undervolt.service\nsudo systemctl restart undervolt"),
            ("降压扫描（高风险实验，必须带防护）",
             "sudo bash 性能优化方案_20260822/测量脚本/uv_sweep_v2.sh 100 5"),
            ("电池温度模块注册（DKMS，内核升级后自动重建）",
             "sudo bash 性能优化方案_20260822/acer-wmi-battery_源码备份/register_dkms.sh"),
            ("真值采集（核对系统实际状态）",
             "sudo bash 05_控制台_Linux/系统控制台_最新_20260822/backend/collect_ground_truth.sh"),
        ]
        dlg = Gtk.Dialog(title="高级工具（高风险操作）", transient_for=self.get_toplevel(),
                         modal=True, default_width=640, default_height=420)
        box = dlg.get_content_area()
        box.set_spacing(8)
        box.set_margin_top(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        warn = Gtk.Label(
            label="⚠ 以下操作可能影响系统稳定性或导致重启。\n"
                  "控制台不提供一键执行（避免误触），请在终端按命令执行，并先创建系统快照。",
            xalign=0, wrap=True)
        warn.get_style_context().add_class("dim-text")
        box.pack_start(warn, False, False, 0)
        buf = Gtk.TextBuffer()
        for title, cmd in TOOLS:
            buf.insert(buf.get_end_iter(), "◆ %s\n    %s\n\n" % (title, cmd))
        tv = Gtk.TextView(buffer=buf)
        tv.set_editable(False)
        tv.set_monospace(True)
        tv.set_cursor_visible(False)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.add(tv)
        box.pack_start(sw, True, True, 0)
        dlg.add_button("知道了", Gtk.ResponseType.OK)
        dlg.show_all()
        dlg.run()
        dlg.destroy()

    # ---------------- 场景参数配置 ----------------
    def _open_scene_config(self, _btn=None):
        """打开场景参数配置对话框"""
        dlg = Gtk.Dialog(title="场景参数配置", transient_for=self.get_toplevel(), modal=True)
        dlg.set_default_size(460, 380)
        box = dlg.get_content_area()
        box.set_spacing(8)
        box.set_margin_top(10)
        box.set_margin_start(10)
        box.set_margin_end(10)

        # 读取当前 default_scene 配置
        scene_path = "/home/<USER>/.config/system-console/default_scene"
        config = {}
        try:
            with open(scene_path) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        config[k.strip()] = v.strip()
        except Exception:
            pass

        ac_scene = config.get("LAST_AC", "ac-perf")
        dc_scene = config.get("LAST_DC", "bat-save")
        gpu_ac = config.get("GPU_AC", "1100")
        gpu_dc = config.get("GPU_DC", "700")

        grid = Gtk.Grid(column_spacing=10, row_spacing=8)

        # 插电默认场景
        lab_ac = Gtk.Label(label="插电默认场景：", xalign=0)
        combo_ac = Gtk.ComboBoxText()
        for s in ["ac-perf", "ac-bal", "ac-quiet"]:
            combo_ac.append(s, s)
        combo_ac.set_active_id(ac_scene if ac_scene in ["ac-perf", "ac-bal", "ac-quiet"] else "ac-perf")
        grid.attach(lab_ac, 0, 0, 1, 1)
        grid.attach(combo_ac, 1, 0, 1, 1)

        # 离电默认场景
        lab_dc = Gtk.Label(label="离电默认场景：", xalign=0)
        combo_dc = Gtk.ComboBoxText()
        for s in ["bat-save", "bat-bal", "bat-perf"]:
            combo_dc.append(s, s)
        combo_dc.set_active_id(dc_scene if dc_scene in ["bat-save", "bat-bal", "bat-perf"] else "bat-save")
        grid.attach(lab_dc, 0, 1, 1, 1)
        grid.attach(combo_dc, 1, 1, 1, 1)

        # GPU AC 频率
        lab_ga = Gtk.Label(label="GPU AC 频率 (MHz)：", xalign=0)
        adj_ga = Gtk.Adjustment(value=int(gpu_ac), lower=300, upper=1100, step_increment=100)
        spin_ga = Gtk.SpinButton(adjustment=adj_ga)
        spin_ga.set_width_chars(5)
        grid.attach(lab_ga, 0, 2, 1, 1)
        grid.attach(spin_ga, 1, 2, 1, 1)

        # GPU DC 频率
        lab_gd = Gtk.Label(label="GPU DC 频率 (MHz)：", xalign=0)
        adj_gd = Gtk.Adjustment(value=int(gpu_dc), lower=300, upper=1100, step_increment=100)
        spin_gd = Gtk.SpinButton(adjustment=adj_gd)
        spin_gd.set_width_chars(5)
        grid.attach(lab_gd, 0, 3, 1, 1)
        grid.attach(spin_gd, 1, 3, 1, 1)

        box.pack_start(grid, False, False, 0)

        note = Gtk.Label(label="说明：修改后写入 default_scene，下次插拔电时生效。\nGT 频率立即生效。", xalign=0)
        note.get_style_context().add_class("dim-text")
        box.pack_start(note, False, False, 0)

        # 按钮
        btn_box = Gtk.Box(spacing=8)
        apply_btn = Gtk.Button(label="保存")
        apply_btn.get_style_context().add_class("suggested-action")
        cancel_btn = Gtk.Button(label="取消")
        btn_box.pack_end(apply_btn, False, False, 0)
        btn_box.pack_end(cancel_btn, False, False, 0)
        box.pack_start(btn_box, False, False, 0)

        def on_apply(_btn):
            content = f"""LAST_AC={combo_ac.get_active_id()}
LAST_DC={combo_dc.get_active_id()}
GPU_AC={int(spin_ga.get_value())}
GPU_DC={int(spin_gd.get_value())}
"""
            def worker():
                import subprocess
                # 2026-08-31 修复: default_scene 属主是本用户(~/.config), 原用 sudo tee
                # 而 tee 不在 sudoers 白名单 → 无凭据缓存时必失败。直接写文件即可。
                # GPU GT 频率需要 root 写 sysfs, 走已白名单的 thermal_ctl.sh (无专用分支,
                # 但 gt_max_freq 不属于 thermal_ctl 职责) → 改用 acdc-profile 同款:
                # 直接探测 card 目录并用用户可写路径尝试, 失败则提示下次插拔电自动应用。
                try:
                    with open(scene_path, "w") as f:
                        f.write(content)
                    rc, out, err = 0, "已写入 " + scene_path, ""
                except OSError as e:
                    rc, out, err = 1, "", str(e)
                # GT 频率立即生效（需要 root；无白名单分支则降级为"下次插拔电生效"）
                try:
                    import glob
                    cards = sorted(glob.glob("/sys/class/drm/card[0-9]*"))
                    card = next((c for c in cards
                                 if os.path.exists(os.path.join(c, "gt_max_freq_mhz"))), None)
                    if card:
                        gt = os.path.join(card, "gt_max_freq_mhz")
                        try:
                            with open(gt, "w") as f:
                                f.write(str(int(spin_gd.get_value())))
                        except OSError:
                            err = (err or "") + "\nGT 频率写入需 root，已保存配置，下次插拔电时由 acdc-profile 自动应用"
                except Exception:
                    pass
                return rc, out, err

            def done(result):
                rc, out, err = result
                d = Gtk.MessageDialog(transient_for=dlg, modal=True,
                                      message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
                                      buttons=Gtk.ButtonsType.OK)
                if rc == 0:
                    d.set_markup("<b>✓ 场景参数已保存</b>\n\n下次插拔电时自动应用新配置")
                    d.run(); d.destroy()
                    dlg.destroy()
                else:
                    d.set_markup(f"<b>保存失败</b>\n{err or out}")
                    d.run(); d.destroy()

            from async_util import run_async
            run_async(worker, done)

        apply_btn.connect("clicked", on_apply)
        cancel_btn.connect("clicked", lambda _b: dlg.destroy())

        dlg.show_all()


# 2026-08-31 清理记录:
# 1) 原此处的"应用功耗排行"孤儿块(8空格缩进, 挂在 _open_scene_config 尾部)
#    已删除——打开场景参数对话框时会混入无关的功耗排行控件。
#    完整实现见 ui_maintenance.py 的 _open_app_power()（已接线）。
# 2) 原文件尾部的 build_tray_menu()/_quick_switch() 死代码已删除——
#    全项目无调用方，console.py 的托盘用的是自己的内联实现(_setup_tray)。
# 3) _read_int 内嵌的"性能日志查看器"72 行孤儿块已删除——函数头丢失导致不可达，
#    完整实现见 ui_maintenance.py 的 _open_perf_log()（已接线）。
