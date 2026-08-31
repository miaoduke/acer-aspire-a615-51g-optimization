#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ui_scenes.py — 电源场景页：6 场景切换 + 状态快照 + M3 入口"""
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

import controller
from async_util import run_async


class ScenesPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)

        head = Gtk.Label(label="电源场景一键切换", xalign=0)
        head.get_style_context().add_class("section-title")
        self.pack_start(head, False, False, 0)

        hint = Gtk.Label(
            label="按供电状态选择场景，点击立即生效。绿色高亮 = 当前实际生效的场景（按系统参数自动检测）。",
            xalign=0, wrap=True)
        hint.get_style_context().add_class("dim-text")
        self.pack_start(hint, False, False, 0)

        # ---- 场景按钮区 ----
        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        self.scene_buttons = {}
        for i, (key, (name, desc)) in enumerate(controller.SCENES.items()):
            btn = Gtk.Button()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            box.set_margin_start(10)
            box.set_margin_end(10)
            n = Gtk.Label(label=name)
            n.get_style_context().add_class("scene-name")
            dd = Gtk.Label(label=desc, wrap=True)
            dd.get_style_context().add_class("scene-desc")
            box.pack_start(n, False, False, 0)
            box.pack_start(dd, False, False, 0)
            btn.add(box)
            btn.set_size_request(200, -1)
            btn.connect("clicked", self._on_scene, key)
            self.scene_buttons[key] = btn
            grid.attach(btn, i % 3, i // 3, 1, 1)
        self.pack_start(grid, False, False, 0)

        # ---- M3 区 ----
        m3box = Gtk.Box(spacing=10)
        m3box.set_margin_top(14)
        m3lab = Gtk.Label(label="M3 离电效能模式：", xalign=0)
        m3box.pack_start(m3lab, False, False, 0)
        self.m3_on = Gtk.Button(label="进入 M3（省电持久化）")
        self.m3_on.connect("clicked", self._on_m3, True)
        self.m3_off = Gtk.Button(label="退出 M3（恢复自动）")
        self.m3_off.connect("clicked", self._on_m3, False)
        self.m3_state = Gtk.Label(label="—", xalign=0)
        self.m3_state.get_style_context().add_class("dim-text")
        m3box.pack_start(self.m3_on, False, False, 0)
        m3box.pack_start(self.m3_off, False, False, 0)
        m3box.pack_start(self.m3_state, False, False, 0)
        self.pack_start(m3box, False, False, 0)

        # ---- 基准测试（科学协议） ----
        bbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        bbox.set_margin_top(14)
        bl = Gtk.Label(label="性能基准测试（场景对比）", xalign=0)
        bl.get_style_context().add_class("section-title")
        bbox.pack_start(bl, False, False, 0)
        brow = Gtk.Box(spacing=8)
        self.bench_btn = Gtk.Button(label="运行基准测试（插电，约 2 分钟）")
        self.bench_btn.connect("clicked", self._on_bench)
        brow.pack_start(self.bench_btn, False, False, 0)
        self.bench_state = Gtk.Label(label="", xalign=0)
        self.bench_state.get_style_context().add_class("dim-text")
        brow.pack_start(self.bench_state, False, False, 0)
        bbox.pack_start(brow, False, False, 0)
        bnote = Gtk.Label(
            label="协议（EMP）：热身 1 次丢弃 + 正式 5 次 + ±2σ 剔离群 + 中位数。"
                  "需插电运行（电池供电受功耗墙限制不可比）；单次约 20 秒满载。",
            xalign=0, wrap=True)
        bnote.get_style_context().add_class("dim-text")
        bbox.pack_start(bnote, False, False, 0)
        self.pack_start(bbox, False, False, 0)

        # ---- 自动切换默认档位设置 ----
        abox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        abox.set_margin_top(10)
        al = Gtk.Label(label="自动切换默认档位（插拔电时自动应用）", xalign=0)
        al.get_style_context().add_class("section-title")
        abox.pack_start(al, False, False, 0)
        row1 = Gtk.Box(spacing=8)
        lab_ac = Gtk.Label(label="插电默认：", xalign=0)
        self.combo_ac = Gtk.ComboBoxText()
        for key in controller.AC_SCENES:
            self.combo_ac.append(key, controller.SCENES[key][0])
        row1.pack_start(lab_ac, False, False, 0)
        row1.pack_start(self.combo_ac, False, False, 0)
        row2 = Gtk.Box(spacing=8)
        lab_dc = Gtk.Label(label="离电默认：", xalign=0)
        self.combo_dc = Gtk.ComboBoxText()
        for key in controller.DC_SCENES:
            self.combo_dc.append(key, controller.SCENES[key][0])
        row2.pack_start(lab_dc, False, False, 0)
        row2.pack_start(self.combo_dc, False, False, 0)
        self.btn_save_defaults = Gtk.Button(label="保存默认档位")
        self.btn_save_defaults.connect("clicked", self._on_save_defaults)
        self.defaults_state = Gtk.Label(label="", xalign=0)
        self.defaults_state.get_style_context().add_class("dim-text")
        abox.pack_start(row1, False, False, 0)
        abox.pack_start(row2, False, False, 0)
        abox.pack_start(self.btn_save_defaults, False, False, 0)
        abox.pack_start(self.defaults_state, False, False, 0)
        self.pack_start(abox, False, False, 0)

        # ---- 状态快照 ----
        self.snap = Gtk.Label(label="", xalign=0, selectable=True, wrap=True)
        self.snap.get_style_context().add_class("mono-text")
        self.pack_start(self.snap, True, True, 0)

        self._busy = False

    # ---------------- 操作 ----------------
    def _run(self, fn, ok_msg, show_script_out=False, after=None):
        if self._busy:
            return
        self._busy = True

        def done(result):
            self._busy = False
            rc, out, err = result
            dlg = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK)
            if rc == 0:
                # 切换后立即采样验证，显示实测参数
                try:
                    from collector import Collector
                    p = Collector().sample()["params"]
                    verify = ("Governor=%s\nEPP=%s\nPL1=%s W\nTurbo=%s" % (
                        p.get("governor") or "—",
                        p.get("epp") or "—",
                        ("%.0f" % p["pl1_w"]) if p["pl1_w"] is not None else "—",
                        "ON" if p["turbo"] is True else ("OFF" if p["turbo"] is False else "—")))
                    if show_script_out:
                        # 显示脚本完整执行输出（M3 功能明细）
                        dlg.set_markup("<b>%s</b>\n\n%s" % (ok_msg, out.strip() or "（无输出）"))
                    else:
                        dlg.set_markup("<b>%s</b>\n\n切换后实测参数：\n%s" % (ok_msg, verify))
                except Exception:
                    dlg.set_markup("<b>%s</b>" % ok_msg)
            else:
                dlg.set_markup("<b>操作失败</b>（rc=%s）\n%s" % (rc, err or out))
            dlg.run()
            dlg.destroy()
            if rc == 0 and after is not None:
                after()
            self.refresh_state()

        run_async(fn, done)

    def _on_scene(self, _btn, key):
        name = controller.SCENES[key][0]
        self._run(lambda: controller.set_scene(key), "已切换场景：%s" % name)

    def _on_m3(self, _btn, on):
        # after 必须传闭包(带 on 参数)，直接传方法对象会 TypeError 静默失败(2026-08-20)
        self._run(lambda: controller.m3_mode(on),
                  "已进入 M3 离电效能模式" if on else "已退出 M3，恢复自动模式",
                  show_script_out=True,
                  after=lambda: self._ask_gpu(on))

    def _on_bench(self, _btn):
        def worker():
            return controller.bench_protocol()
        def done(result):
            rc, data, err = result
            self.bench_state.set_text("")
            self.bench_btn.set_sensitive(True)
            d = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK)
            if rc == 0:
                d.set_markup(
                    "<b>基准测试完成</b>\n\n"
                    "样本：%s\n"
                    "保留：%s（±2σ 剔除）\n"
                    "中位数：%d 次迭代\n"
                    "吞吐量：<b>%.1f 万次/s</b>\n\n"
                    "当前场景下测得（对比其他场景请切换后重跑）" % (
                        ", ".join(str(x) for x in data["samples"]),
                        ", ".join(str(x) for x in data["kept"]),
                        data["median"], data["kps"]))
            else:
                d.set_markup("<b>基准测试失败</b>\n%s" % (err or "未知错误"))
            d.run()
            d.destroy()
        if not controller.is_ac():
            d = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.OK)
            d.set_markup("<b>需插电运行</b>\n\n电池供电受功耗墙限制，结果不可比。\n请连接电源后再运行。")
            d.run()
            d.destroy()
            return
        self.bench_btn.set_sensitive(False)
        self.bench_state.set_text("运行中（热身 + 5 次 × 20 秒，约 2 分钟）…")
        run_async(worker, done)

    def _ask_gpu(self, on):
        """M3 切换后的 GPU 交互：进入→建议切集显；退出→建议恢复独显"""
        def worker():
            try:
                import subprocess
                r = subprocess.run(["prime-select", "query"], capture_output=True, text=True, timeout=5)
                return r.stdout.strip()
            except Exception:
                return None
        def done(cur):
            target = "intel" if on else "nvidia"
            if cur == target:
                d = Gtk.MessageDialog(transient_for=self.get_toplevel(), modal=True,
                                      message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK)
                d.set_markup("<b>GPU 已是%s模式</b>\n\n无需切换。" % ("集显" if on else "独显"))
                d.run()
                d.destroy()
                return
            d = Gtk.MessageDialog(transient_for=self.get_toplevel(), modal=True,
                                  message_type=Gtk.MessageType.QUESTION,
                                  buttons=Gtk.ButtonsType.NONE)
            d.set_markup(
                "<b>%s</b>\n\n"
                "当前 GPU：%s\n"
                "%s\n"
                "注意：切换需<b>重启</b>后生效\n"
                "切换完成后可选择「立即重启」或「稍后重启」" % (
                    "切换到集显？" if on else "恢复独显？",
                    cur or "未知",
                    "集显模式可再省 ~7.7W（M3 省电更彻底）" if on
                    else "独显模式提供完整图形性能"))
            d.add_button("保持当前", Gtk.ResponseType.NO)
            d.add_button("切到%s" % ("集显" if on else "独显"), Gtk.ResponseType.YES)
            resp = d.run()
            d.destroy()
            if resp != Gtk.ResponseType.YES:
                return
            def gpu_worker():
                return controller.gpu_switch(target)
            def gpu_done(result):
                rc, out, err = result
                gd = Gtk.MessageDialog(
                    transient_for=self.get_toplevel(), modal=True,
                    message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.NONE)
                if rc == 0:
                    gd.set_markup(
                        "<b>GPU 已切换到%s</b>\n\n"
                        "配置已写入，需<b>重启系统</b>后完全生效。\n"
                        "重启后可在高级控制页确认 GPU 模式。" % ("集显" if on else "独显"))
                    gd.add_button("稍后重启", Gtk.ResponseType.NO)
                    b_reboot = gd.add_button("立即重启", Gtk.ResponseType.YES)
                    b_reboot.get_style_context().add_class("suggested-action")
                else:
                    gd.set_markup("<b>GPU 切换失败</b>（rc=%s）\n%s" % (rc, err or out))
                    gd.add_button("确定", Gtk.ResponseType.OK)
                resp = gd.run()
                gd.destroy()
                if resp == Gtk.ResponseType.YES:
                    # 用户已明确确认 -> 一键重启(需先保存其他工作!)
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
            run_async(gpu_worker, gpu_done)
        run_async(worker, done)

    def _on_save_defaults(self, _btn):
        ac = self.combo_ac.get_active_id()
        dc = self.combo_dc.get_active_id()
        if ac is None or dc is None:
            self.defaults_state.set_text("请先选择插电/离电默认档位")
            return
        if controller.set_default_scenes(ac, dc):
            self.defaults_state.set_text(
                "已保存：插电 → %s，离电 → %s（插拔电自动应用）" % (
                    controller.SCENES[ac][0], controller.SCENES[dc][0]))
        else:
            self.defaults_state.set_text("保存失败（无权限写 /var/lib/battery-care）")

    # ---------------- 状态刷新 ----------------
    def refresh_state(self, d=None):
        # 无数据时立即自采样（场景切换后马上反映高亮，不等下一轮 tick）
        if d is None:
            try:
                from collector import Collector
                d = Collector().sample()
            except Exception:
                return
        # M3 状态：服务文件存在即生效（oneshot 服务 enable 后重启才 active，is-active 误判）
        if controller.m3_active():
            self.m3_state.set_text("● M3 生效中（PPD=power-saver 持久化，acdc 自动切换已停）")
        else:
            self.m3_state.set_text("○ M3 未启用")

        # 默认档位下拉回显（只在初次或变化时设置）
        defs = controller.get_default_scenes()
        cur_ac = self.combo_ac.get_active_id()
        cur_dc = self.combo_dc.get_active_id()
        if cur_ac != defs["LAST_AC"]:
            self.combo_ac.set_active_id(defs["LAST_AC"])
        if cur_dc != defs["LAST_DC"]:
            self.combo_dc.set_active_id(defs["LAST_DC"])
        self.defaults_state.set_text(
            "当前默认：插电 → %s，离电 → %s（插拔电自动应用，也可手动切换任意场景）" % (
                controller.SCENES[defs["LAST_AC"]][0],
                controller.SCENES[defs["LAST_DC"]][0]))

        # 场景高亮：按当前系统参数匹配"实际生效的场景"（不再整排高亮）
        if d is None:
            return
        ac = d["ac"]
        p = d["params"]
        snap = []
        # 2026-08-31: 移除 PPD（PPD masked 后恒"—"）
        snap.append("供电：%s  |  Governor：%s" % (
            "AC 插电" if ac else "DC 电池", p["governor"] or "—"))
        snap.append("PL1/PL2：%s / %s W  |  Turbo：%s  |  EPP：%s" % (
            self._w(p["pl1_w"]), self._w(p["pl2_w"]),
            "ON" if p["turbo"] is True else ("OFF" if p["turbo"] is False else "—"),
            p["epp"] or "—"))
        snap.append("温度：%s°C  |  电池：%s%%" % (
            ("%.0f" % d["temp"]) if d["temp"] is not None else "—",
            d["bat"]["capacity"] if d["bat"]["capacity"] is not None else "—"))

        # 场景高亮：按当前系统参数匹配"实际生效的场景"（与 controller 共享匹配逻辑）
        active = controller.get_active_scene(p)
        for key, btn in self.scene_buttons.items():
            ctx = btn.get_style_context()
            ctx.remove_class("scene-active")
        if active:
            self.scene_buttons[active].get_style_context().add_class("scene-active")
            snap.append("当前场景：%s（自动检测匹配）" % controller.SCENES[active][0])
        else:
            snap.append("⚠ 当前场景：自定义参数（与 6 个标准场景均不匹配）")
        self.snap.set_text("\n".join(snap))
        # 电池详情已迁移至【电池保养】页（避免重复，2026-08-21）

    @staticmethod
    def _w(v):
        return "%.1f" % v if v is not None else "—"