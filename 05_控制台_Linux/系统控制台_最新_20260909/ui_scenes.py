#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ui_scenes.py — 电源场景页：6 场景切换 + 状态快照 + M3 入口"""
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

import controller
from pathlib import Path
from async_util import run_async
from src.core.i18n import T


class ScenesPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)

        head = Gtk.Label(label=T("电源场景一键切换"), xalign=0)
        head.get_style_context().add_class("section-title")
        self.pack_start(head, False, False, 0)

        hint = Gtk.Label(
            label=T("按供电状态选择场景，点击立即生效。绿色高亮 = 当前实际生效的场景（按系统参数自动检测）。"),
            xalign=0, wrap=True)
        hint.get_style_context().add_class("dim-text")
        self.pack_start(hint, False, False, 0)

        # ---- 场景按钮区 ----
        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        self.scene_buttons = {}
        for i, (key, (name, desc)) in enumerate(((k, (T(n), T(d))) for k, (n, d) in controller.SCENES.items())):
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

        # ---- Profile 信息面板（Phase 2 G1 集成）----
        from src.core.profile import get_loader as _get_profile_loader
        _profile_loader = _get_profile_loader()
        all_profiles = _profile_loader.list_profiles()

        pbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        pbox.set_margin_top(8)
        pl = Gtk.Label(label=T("Profile 配置（来源：<span foreground='#4a9' style='italic'>内置</span> · <span foreground='#a4f' style='italic'>用户</span> · <span foreground='#a88' style='italic'>硬编码</span>）"),
                       xalign=0, use_markup=True)
        pl.get_style_context().add_class("section-title")
        pbox.pack_start(pl, False, False, 0)

        # profile 行：每个 profile 一行，按来源着色
        for pname in all_profiles:
            row = Gtk.Box(spacing=6)
            # 来源标记
            if _profile_loader.find_profile_path(pname):
                user_path = _profile_loader.user_dir / pname / "tuned.conf"
                if user_path.exists():
                    src_mark = "<span foreground='#a4f'>👤</span>"
                else:
                    src_mark = "<span foreground='#4a9'>📦</span>"
            else:
                src_mark = "<span foreground='#a88'>⚙</span>"

            # 名称
            try:
                p = _profile_loader.load(pname)
                name_label = Gtk.Label(
                    label=f"{src_mark} <b>{pname}</b>  {T(p.summary)[:60]}",
                    xalign=0, use_markup=True
                )
            except Exception as e:
                name_label = Gtk.Label(
                    label=f"{src_mark} <b>{pname}</b>  <span foreground='red'>{e}</span>",
                    xalign=0, use_markup=True
                )
            row.pack_start(name_label, True, True, 0)

            # 验证状态
            from src.core.profile import validate_profile as _validate
            ok, errs = _validate(pname)
            if ok:
                state_label = Gtk.Label(label="<span foreground='#4a9'>✓</span>",
                                        xalign=1, use_markup=True)
            else:
                state_label = Gtk.Label(label=f"<span foreground='red'>✗ {len(errs)}</span>",
                                        xalign=1, use_markup=True)
            row.pack_start(state_label, False, False, 0)

            # P1-4: 加编辑按钮（用户可双击/点击打开文件）
            edit_btn = Gtk.Button(label="✎")
            edit_btn.set_tooltip_text(T("用编辑器打开 ~/.config/system-console/profiles/{}").format(pname + "/tuned.conf"))
            edit_btn.set_size_request(30, -1)
            edit_btn.connect("clicked", self._on_edit_profile, pname)
            row.pack_end(edit_btn, False, False, 0)

            # 2026-09-07 审计 B5：继承链查看（每个 profile 可看从基类继承了哪些值）
            tree_btn = Gtk.Button(label="🌲")
            tree_btn.set_tooltip_text(T("查看该 profile 的继承链（从基类继承了哪些值）"))
            tree_btn.set_size_request(30, -1)
            tree_btn.connect("clicked", self._on_profile_tree, pname)
            row.pack_end(tree_btn, False, False, 0)

            pbox.pack_start(row, False, False, 0)

        # 2026-09-07 审计 A2：创建自定义方案入口（此前仅 CLI 的 try_user_profile 可达）
        try_row = Gtk.Box(spacing=8)
        try_row.set_margin_top(4)
        try_btn = Gtk.Button(label=T("➕ 创建自定义方案（沙箱试用）"))
        try_btn.set_tooltip_text(T("引导创建自己的电源方案：在 /tmp 沙箱体验 profile 创建→验证→合并全流程，零破坏。实际写入位置见提示"))
        try_btn.connect("clicked", self._on_try_user_profile)
        try_row.pack_start(try_btn, False, False, 0)

        hint = Gtk.Label(
            label=T("实际创建：把 tuned.conf 放到 ~/.config/system-console/profiles/<方案名>/ 即可，本页自动显示（👤）"),
            xalign=0)
        hint.get_style_context().add_class("dim-text")
        try_row.pack_start(hint, True, True, 0)
        pbox.pack_start(try_row, False, False, 0)

        self.pack_start(pbox, False, False, 0)
        # ---- Profile 信息面板结束 ----

        # ---- M3 区 ----
        m3box = Gtk.Box(spacing=10)
        m3box.set_margin_top(14)
        m3lab = Gtk.Label(label=T("M3 离电效能模式："), xalign=0)
        m3box.pack_start(m3lab, False, False, 0)
        self.m3_on = Gtk.Button(label=T("进入 M3（省电持久化）"))
        self.m3_on.connect("clicked", self._on_m3, True)
        self.m3_off = Gtk.Button(label=T("退出 M3（恢复自动）"))
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
        bl = Gtk.Label(label=T("性能基准测试（场景对比）"), xalign=0)
        bl.get_style_context().add_class("section-title")
        bbox.pack_start(bl, False, False, 0)
        brow = Gtk.Box(spacing=8)
        self.bench_btn = Gtk.Button(label=T("运行基准测试（插电，约 2 分钟）"))
        self.bench_btn.connect("clicked", self._on_bench)
        brow.pack_start(self.bench_btn, False, False, 0)
        self.bench_state = Gtk.Label(label="", xalign=0)
        self.bench_state.get_style_context().add_class("dim-text")
        brow.pack_start(self.bench_state, False, False, 0)
        bbox.pack_start(brow, False, False, 0)
        bnote = Gtk.Label(
            label=T('协议（EMP）：热身 1 次丢弃 + 正式 5 次 + ±2σ 剔离群 + 中位数。需插电运行（电池供电受功耗墙限制不可比）；单次约 20 秒满载。'),
            xalign=0, wrap=True)
        bnote.get_style_context().add_class("dim-text")
        bbox.pack_start(bnote, False, False, 0)
        self.pack_start(bbox, False, False, 0)

        # ---- 自动切换默认档位设置 ----
        abox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        abox.set_margin_top(10)
        al = Gtk.Label(label=T("自动切换默认档位（插拔电时自动应用）"), xalign=0)
        al.get_style_context().add_class("section-title")
        abox.pack_start(al, False, False, 0)
        row1 = Gtk.Box(spacing=8)
        lab_ac = Gtk.Label(label=T("插电默认："), xalign=0)
        self.combo_ac = Gtk.ComboBoxText()
        for key in controller.AC_SCENES:
            self.combo_ac.append(key, T(controller.SCENES[key][0]))
        row1.pack_start(lab_ac, False, False, 0)
        row1.pack_start(self.combo_ac, False, False, 0)
        row2 = Gtk.Box(spacing=8)
        lab_dc = Gtk.Label(label=T("离电默认："), xalign=0)
        self.combo_dc = Gtk.ComboBoxText()
        for key in controller.DC_SCENES:
            self.combo_dc.append(key, T(controller.SCENES[key][0]))
        row2.pack_start(lab_dc, False, False, 0)
        row2.pack_start(self.combo_dc, False, False, 0)
        self.btn_save_defaults = Gtk.Button(label=T("保存默认档位"))
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
                        dlg.set_markup("<b>%s</b>\n\n%s" % (ok_msg, out.strip() or T("（无输出）")))
                    else:
                        dlg.set_markup(T("<b>%s</b>\n\n切换后实测参数：\n%s") % (ok_msg, verify))
                except Exception:
                    dlg.set_markup("<b>%s</b>" % ok_msg)
            else:
                dlg.set_markup(T("<b>操作失败</b>（rc=%s）\n%s") % (rc, err or out))
            dlg.run()
            dlg.destroy()
            if rc == 0 and after is not None:
                after()
            self.refresh_state()

        run_async(fn, done)

    # ---------------- 隐形功能 GUI 化（2026-09-07 审计 A2/B5）----------------
    def _on_try_user_profile(self, _btn):
        """A2: 自定义 profile 沙箱试用向导（/tmp 零破坏体验全流程）"""
        def worker():
            return controller.try_user_profile()

        def done(result):
            rc, out, err = result
            d = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK)
            d.set_markup(T("<b>➕ 自定义方案试用向导（沙箱）</b>"))
            txt = (out or "").strip()
            if err and rc != 0:
                txt += "\n" + err
            sw = Gtk.ScrolledWindow()
            sw.set_size_request(600, 400)
            buf = Gtk.TextBuffer()
            buf.set_text(txt or T("(无输出)"))
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

    def _on_profile_tree(self, _btn, pname):
        """B5: 单个 profile 继承链查看（从基类继承了哪些值）"""
        def worker():
            return controller.profile_inheritance(pname)

        def done(result):
            rc, out, err = result
            d = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK)
            d.set_markup(T("<b>🌲 继承链 — {}</b>").format(pname))
            txt = (out or "").strip() or (err or T("(无输出)"))
            sw = Gtk.ScrolledWindow()
            sw.set_size_request(600, 350)
            buf = Gtk.TextBuffer()
            buf.set_text(txt)
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

    def _on_edit_profile(self, btn, pname):
        """P1-4: 用 xdg-open 打开 profile 配置文件"""
        import subprocess
        from pathlib import Path
        from src.core.profile import get_loader
        loader = get_loader()
        path = loader.find_profile_path(pname)
        if path is None:
            # fallback: 跳用户目录
            user_path = Path.home() / ".config" / "system-console" / "profiles" / pname / "tuned.conf"
            user_path.parent.mkdir(parents=True, exist_ok=True)
            user_path.touch()
            path = user_path
        # 优先用 xdg-open（图形化），否则用默认编辑器
        try:
            subprocess.Popen(["xdg-open", str(path)])
        except FileNotFoundError:
            for editor in ["gedit", "kate", "mousepad", "nano"]:
                if subprocess.run(["which", editor], capture_output=True).returncode == 0:
                    subprocess.Popen([editor, str(path)])
                    return
            subprocess.Popen(["xdg-open", str(path)])

    def _on_scene(self, _btn, key):
        name = T(controller.SCENES[key][0])
        # 2026-09-01 修复: M3 生效时点击其他场景 → 先自动退出 M3 再切换。
        # 原逻辑直接 set_scene，M3 的 acdc-profile(disabled) 与 m3 服务文件不会恢复，
        # 导致 UI 仍显示 M3 生效、AC/DC 自动切换不工作。
        if controller.m3_active():
            self.snap.set_text(T("检测到 M3 生效，先退出 M3…"))
            rc, out, err = controller.m3_mode(False)
            if rc != 0:
                self.snap.set_text(T("退出 M3 失败: ") + (err or out)[:40])
                return
        self._run(lambda: controller.set_scene(key), T("已切换场景：%s") % name)

    def _on_m3(self, _btn, on):
        # after 必须传闭包(带 on 参数)，直接传方法对象会 TypeError 静默失败(2026-08-20)
        self._run(lambda: controller.m3_mode(on),
                  T("已进入 M3 离电效能模式") if on else T("已退出 M3，恢复自动模式"),
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
                    T('<b>基准测试完成</b>\n\n样本：%s\n保留：%s（±2σ 剔除）\n中位数：%d 次迭代\n吞吐量：<b>%.1f 万次/s</b>\n\n当前场景下测得（对比其他场景请切换后重跑）') % (
                        ", ".join(str(x) for x in data["samples"]),
                        ", ".join(str(x) for x in data["kept"]),
                        data["median"], data["kps"]))
            else:
                d.set_markup(T("<b>基准测试失败</b>\n%s") % (err or T("未知错误")))
            d.run()
            d.destroy()
        if not controller.is_ac():
            d = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.OK)
            d.set_markup(T("<b>需插电运行</b>\n\n电池供电受功耗墙限制，结果不可比。\n请连接电源后再运行。"))
            d.run()
            d.destroy()
            return
        self.bench_btn.set_sensitive(False)
        self.bench_state.set_text(T("运行中（热身 + 5 次 × 20 秒，约 2 分钟）…"))
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
                d.set_markup(T("<b>GPU 已是%s模式</b>\n\n无需切换。") % (T("集显") if on else T("独显")))
                d.run()
                d.destroy()
                return
            d = Gtk.MessageDialog(transient_for=self.get_toplevel(), modal=True,
                                  message_type=Gtk.MessageType.QUESTION,
                                  buttons=Gtk.ButtonsType.NONE)
            d.set_markup(
                T('<b>%s</b>\n\n当前 GPU：%s\n%s\n注意：切换需<b>重启</b>后生效\n切换完成后可选择「立即重启」或「稍后重启」') % (
                    T("切换到集显？") if on else T("恢复独显？"),
                    cur or T("未知"),
                    T("集显模式可再省 ~7.7W（M3 省电更彻底）") if on
                    else T("独显模式提供完整图形性能")))
            d.add_button(T("保持当前"), Gtk.ResponseType.NO)
            d.add_button(T("切到%s") % (T("集显") if on else T("独显")), Gtk.ResponseType.YES)
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
                        T('<b>GPU 已切换到%s</b>\n\n配置已写入，需<b>重启系统</b>后完全生效。\n重启后可在高级控制页确认 GPU 模式。') % (T("集显") if on else T("独显")))
                    gd.add_button(T("稍后重启"), Gtk.ResponseType.NO)
                    b_reboot = gd.add_button(T("立即重启"), Gtk.ResponseType.YES)
                    b_reboot.get_style_context().add_class("suggested-action")
                else:
                    gd.set_markup(T("<b>GPU 切换失败</b>（rc=%s）\n%s") % (rc, err or out))
                    gd.add_button(T("确定"), Gtk.ResponseType.OK)
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
                            rd.set_markup(T("<b>重启失败</b>\n%s") % (err2 or out2))
                            rd.run()
                            rd.destroy()
                    run_async(reboot_worker, reboot_done)
            run_async(gpu_worker, gpu_done)
        run_async(worker, done)

    def _on_save_defaults(self, _btn):
        ac = self.combo_ac.get_active_id()
        dc = self.combo_dc.get_active_id()
        if ac is None or dc is None:
            self.defaults_state.set_text(T("请先选择插电/离电默认档位"))
            return
        if controller.set_default_scenes(ac, dc):
            self.defaults_state.set_text(
                T("已保存：插电 → %s，离电 → %s（插拔电自动应用）") % (
                    T(controller.SCENES[ac][0]), T(controller.SCENES[dc][0])))
        else:
            self.defaults_state.set_text(T("保存失败（无权限写 /var/lib/battery-care）"))

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
            self.m3_state.set_text(T("● M3 生效中（PPD=power-saver 持久化，acdc 自动切换已停）"))
        else:
            self.m3_state.set_text(T("○ M3 未启用"))

        # 默认档位下拉回显（只在初次或变化时设置）
        defs = controller.get_default_scenes()
        cur_ac = self.combo_ac.get_active_id()
        cur_dc = self.combo_dc.get_active_id()
        if cur_ac != defs["LAST_AC"]:
            self.combo_ac.set_active_id(defs["LAST_AC"])
        if cur_dc != defs["LAST_DC"]:
            self.combo_dc.set_active_id(defs["LAST_DC"])
        self.defaults_state.set_text(
            T("当前默认：插电 → %s，离电 → %s（插拔电自动应用，也可手动切换任意场景）") % (
                T(controller.SCENES[defs["LAST_AC"]][0]),
                T(controller.SCENES[defs["LAST_DC"]][0])))

        # 场景高亮：按当前系统参数匹配"实际生效的场景"（不再整排高亮）
        if d is None:
            return
        ac = d["ac"]
        p = d["params"]
        snap = []
        # 2026-08-31: 移除 PPD（PPD masked 后恒"—"）
        snap.append(T("供电：%s  |  Governor：%s") % (
            T("AC 插电") if ac else T("DC 电池"), p["governor"] or "—"))
        snap.append("PL1/PL2：%s / %s W  |  Turbo：%s  |  EPP：%s" % (
            self._w(p["pl1_w"]), self._w(p["pl2_w"]),
            "ON" if p["turbo"] is True else ("OFF" if p["turbo"] is False else "—"),
            p["epp"] or "—"))
        snap.append(T("温度：%s°C  |  电池：%s%%") % (
            ("%.0f" % d["temp"]) if d["temp"] is not None else "—",
            d["bat"]["capacity"] if d["bat"]["capacity"] is not None else "—"))

        # 场景高亮：按当前系统参数匹配"实际生效的场景"（与 controller 共享匹配逻辑）
        active = controller.get_active_scene(p)
        for key, btn in self.scene_buttons.items():
            ctx = btn.get_style_context()
            ctx.remove_class("scene-active")
        if active:
            self.scene_buttons[active].get_style_context().add_class("scene-active")
            snap.append(T("当前场景：%s（自动检测匹配）") % T(controller.SCENES[active][0]))
        else:
            snap.append(T("⚠ 当前场景：自定义参数（与 6 个标准场景均不匹配）"))
        self.snap.set_text("\n".join(snap))
        # 电池详情已迁移至【电池保养】页（避免重复，2026-08-21）

    @staticmethod
    def _w(v):
        return "%.1f" % v if v is not None else "—"