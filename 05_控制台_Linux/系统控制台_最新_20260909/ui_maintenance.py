#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ui_maintenance.py — 系统维护页：服务状态 / 内核守卫 / 硬件诊断 / 日志回看
职责：系统健康监测与诊断维护（自高级页迁移，2026-08-21 科学重排）
"""
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
import os
import time  # 2026-09-11 修复: 498 行 time.strftime 用了但从未 import(被上层类型错误掩盖至今)

from async_util import run_async
import controller
from src.core.i18n import T


class MaintenancePage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)

        head = Gtk.Label(label=T("系统维护与诊断"), xalign=0)
        head.get_style_context().add_class("section-title")
        self.pack_start(head, False, False, 0)

        hint = Gtk.Label(
            label=T("系统健康监测、内核变动防护、硬件错误诊断与性能数据回看。"),
            xalign=0, wrap=True)
        hint.get_style_context().add_class("dim-text")
        self.pack_start(hint, False, False, 0)

        # ---- 授权与安装（重装/换机后一键就位；一次性提权 15 分钟全部功能可用）----
        abox = Gtk.Box(spacing=8)
        abox.set_margin_top(12)
        al = Gtk.Label(label=T("授权与安装"), xalign=0)
        al.get_style_context().add_class("section-title")
        self.auth_btn = Gtk.Button(label=T("🔑 一键提权"))
        self.auth_btn.set_tooltip_text(T("弹窗输入密码授权一次（sudo 缓存 15 分钟），期间所有控制功能免密可用"))
        self.auth_btn.connect("clicked", self._on_elevate)
        self.inst_btn = Gtk.Button(label=T("⚙️ 一键安装/修复"))
        self.inst_btn.set_tooltip_text(T("重装/换机后点击：配置 sudo 白名单 + RAPL 读权限 + acdc/cpu-power-limit 服务 + 桌面启动器（等价 sudo bash install.sh）"))
        self.inst_btn.connect("clicked", self._on_install)
        self.auth_state = Gtk.Label(label="", xalign=0)
        self.auth_state.get_style_context().add_class("dim-text")
        abox.pack_start(al, False, False, 0)
        abox.pack_start(self.auth_state, False, False, 0)
        abox.pack_end(self.inst_btn, False, False, 0)
        abox.pack_end(self.auth_btn, False, False, 0)

        # 2026-09-08 语言切换（维护页入口，托盘不可用时的主入口）
        lang_box = Gtk.Box(spacing=8)
        lang_box.set_margin_top(4)
        self.lang_combo = Gtk.ComboBoxText()
        for code, label in (("auto", T("自动（跟随系统）")), ("zh_CN", "中文"), ("en_US", "English")):
            self.lang_combo.append_text(label)
        cur = self._current_language()
        self.lang_combo.set_active({"auto": 0, "zh_CN": 1, "en_US": 2}.get(cur, 0))
        lang_btn = Gtk.Button(label=T("应用语言（重启控制台生效）"))
        lang_btn.connect("clicked", self._on_apply_language)
        ll = Gtk.Label(label=T("界面语言："), xalign=0)
        lang_box.pack_start(ll, False, False, 0)
        lang_box.pack_start(self.lang_combo, False, False, 0)
        lang_box.pack_start(lang_btn, False, False, 0)
        abox.pack_start(lang_box, False, False, 0)
        self.pack_start(abox, False, False, 0)

        # ---- 服务状态 ----
        sbox = Gtk.Box(spacing=8)
        sl = Gtk.Label(label=T("优化栈服务状态"), xalign=0)
        sl.get_style_context().add_class("section-title")
        sbox.pack_start(sl, False, False, 0)
        # 开机自启开关（2026-09-11 新增：控制 ~/.config/autostart/system-console.desktop）
        self.autostart_switch = Gtk.Switch()
        self.autostart_switch.set_tooltip_text(T("开机自动启动系统控制台"))
        self.autostart_switch.set_state(self._autostart_enabled())
        # state=实际状态, active=用户可见状态; set_state 而非 set_active 避免触发信号
        al = Gtk.Label(label=T("控制台开机自启："), xalign=0)
        sbox.pack_end(self.autostart_switch, False, False, 0)
        sbox.pack_end(al, False, False, 0)
        self.autostart_switch.connect("state-set", self._on_autostart_toggle)
        self.svc_refresh = Gtk.Button(label=T("刷新"))
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
        kl = Gtk.Label(label=T("内核变动检测 / 一键修复"), xalign=0)
        kl.get_style_context().add_class("section-title")
        self.kern_ver = Gtk.Label(label="—", xalign=0)
        self.kern_ver.get_style_context().add_class("mono-text")
        self.kbtn_check = Gtk.Button(label=T("重新检测"))
        self.kbtn_check.connect("clicked", lambda _b: self._kernel_guard("check"))
        self.kbtn_repair = Gtk.Button(label=T("一键修复"))
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
        tl2 = Gtk.Label(label=T("工具与诊断"), xalign=0)
        tl2.get_style_context().add_class("section-title")
        tbox2.pack_start(tl2, False, False, 0)

        btn_row = Gtk.Box(spacing=8)

        perf_btn = Gtk.Button(label=T("📊 性能日志"))
        perf_btn.set_tooltip_text(T("查看 CPU 频率/温度/功耗/限流历史记录"))
        perf_btn.connect("clicked", self._open_perf_log)

        app_pwr_btn = Gtk.Button(label=T("🔋 应用功耗排行"))
        app_pwr_btn.set_tooltip_text(T("查看哪些应用在消耗 CPU 和功耗（cgroup 分析）"))
        app_pwr_btn.connect("clicked", self._open_app_power)

        mce_btn = Gtk.Button(label=T("🩺 MCE 硬件错误"))
        mce_btn.set_tooltip_text(T("查看内存错误 / PCIe AER / 机器检查事件（含权威 CPU MCE 计数）"))
        mce_btn.connect("clicked", self._on_mce)

        # 2026-09-07 审计 A1：完整状态快照（tlp-stat 风格全景诊断，此前仅 syscon-snap CLI 可达）
        snap_btn = Gtk.Button(label=T("📋 一键诊断快照"))
        snap_btn.set_tooltip_text(T("导出 CPU/内存/电池/温度/磁盘/限流全景状态 —— 排障时一键导出全部信息"))
        snap_btn.connect("clicked", self._on_system_snapshot)

        # 2026-09-07 审计 B6：运行期冲突复查（安装新电源工具后一键复查）
        conflict_btn = Gtk.Button(label=T("🔍 冲突复查"))
        conflict_btn.set_tooltip_text(T("复查互斥电源工具冲突 + double-sudo 静态检测（装新工具后建议跑一次）"))
        conflict_btn.connect("clicked", self._on_conflict_recheck)

        btn_row.pack_start(perf_btn, False, False, 0)
        btn_row.pack_start(app_pwr_btn, False, False, 0)
        btn_row.pack_start(mce_btn, False, False, 0)
        btn_row.pack_start(snap_btn, False, False, 0)
        btn_row.pack_start(conflict_btn, False, False, 0)
        tbox2.pack_start(btn_row, False, False, 0)
        self.pack_start(tbox2, False, False, 0)

        # ---- 运维工具区（2026-08-31 新增）----
        # 快照/备份/降权——铁律工具的 GUI 化，此前只能命令行
        otbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        otbox.set_margin_top(12)
        otl = Gtk.Label(label=T("运维工具（铁律 · 一键化）"), xalign=0)
        otl.get_style_context().add_class("section-title")
        otbox.pack_start(otl, False, False, 0)

        orow1 = Gtk.Box(spacing=8)
        self.snap_create = Gtk.Button(label=T("📸 系统快照"))
        self.snap_create.set_tooltip_text(T("Timeshift 快照（铁律 L1/L2：系统/高风险改动前必做）"))
        self.snap_create.connect("clicked", self._on_snapshot_create)
        self.snap_list = Gtk.Button(label=T("🗂 快照列表"))
        self.snap_list.set_tooltip_text(T("查看已有 Timeshift 快照"))
        self.snap_list.connect("clicked", self._on_snapshot_list)
        self.snap_delete = Gtk.Button(label=T("🗑 删除快照"))
        self.snap_delete.set_tooltip_text(T("删除选中的 Timeshift 快照（危险，需确认）"))
        self.snap_delete.connect("clicked", self._on_snapshot_delete)
        orow1.pack_start(self.snap_create, False, False, 0)
        orow1.pack_start(self.snap_list, False, False, 0)
        orow1.pack_start(self.snap_delete, False, False, 0)
        otbox.pack_start(orow1, False, False, 0)

        orow2 = Gtk.Box(spacing=8)
        self.quiet_btn = Gtk.Button(label=T("🔇 后台降权"))
        self.quiet_btn.set_tooltip_text(T("后台进程 renice+15（基准测试前用，数据更干净）"))
        self.quiet_btn.connect("clicked", self._on_quiet, True)
        self.unquiet_btn = Gtk.Button(label=T("🔊 恢复优先级"))
        self.unquiet_btn.set_tooltip_text(T("恢复后台进程优先级"))
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
        tlab = Gtk.Label(label=T("电池温度模块（acer-wmi-battery）："), xalign=0)
        self.temp_load = Gtk.Button(label=T("加载"))
        self.temp_load.connect("clicked", self._on_temp_mod, True)
        self.temp_unload = Gtk.Button(label=T("卸载"))
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
        self.refresh_auth_state()

    # ---------------- 授权与安装 ----------------
    def refresh_auth_state(self):
        def worker():
            return controller.auth_status()

        def done(ok):
            self.auth_state.set_text(
                T("sudo 已授权（15 分钟缓存期）") if ok else T("未授权（先一键提权，或重装后点一键安装）"))
        run_async(worker, done)

    # ---------------- 语言切换（2026-09-08）----------------
    @staticmethod
    def _current_language():
        try:
            from src.core.config import Config
            return Config.get().language
        except Exception:
            return "auto"

    def _on_apply_language(self, _btn):
        """写入 config.yaml，重启控制台后生效"""
        sel = self.lang_combo.get_active()
        code = {0: "auto", 1: "zh_CN", 2: "en_US"}.get(sel, "auto")
        try:
            from src.core.config import Config
            import re
            cfg_path = Config.get().config_dir / "config.yaml"
            text = cfg_path.read_text(encoding="utf-8")
            if re.search(r"^language:.*$", text, re.M):
                text = re.sub(r"^language:.*$", f"language: {code}", text, count=1, flags=re.M)
            else:
                text = text.rstrip() + f"\nlanguage: {code}\n"
            cfg_path.write_text(text, encoding="utf-8")
            d = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK)
            d.set_markup(T("✓ 语言已保存：{}（重启控制台后生效）").format(
                {"auto": T("自动（跟随系统）"), "zh_CN": "中文", "en_US": "English"}.get(code, code)))
            d.run()
            d.destroy()
        except Exception as e:
            d = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK)
            d.set_markup(T("语言保存失败：{}".format(e)))
            d.run()
            d.destroy()

    def _on_elevate(self, _b=None):
        def worker():
            ok, msg = controller.elevate()
            return (0 if ok else 1), msg, ""

        def done(result):
            rc, msg, _ = result
            self.auth_state.set_text(("✓ " if rc == 0 else "✗ ") + msg)
        self.auth_state.set_text(T("正在检查授权…"))
        run_async(worker, done)

    def _on_install(self, _b=None):
        def worker():
            return controller.install_system()

        def done(result):
            rc, out, err = result
            self.auth_state.set_text(T("安装完成 ✓") if rc == 0 else T("安装失败（%s）") % (err or T("未知")))
            self._load_services()   # 服务列表刷新
            self.refresh_auth_state()
            dlg = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK)
            dlg.set_markup("<b>%s</b>" % (T("安装/修复成功") if rc == 0 else T("安装/修复失败")))
            buf = Gtk.TextBuffer()
            buf.set_text(out[-2500:] if out else (err or T("无输出")))
            sw = Gtk.ScrolledWindow()
            sw.set_size_request(600, 280)
            tv = Gtk.TextView(buffer=buf)
            tv.set_editable(False)
            tv.set_monospace(True)
            sw.add(tv)
            box = dlg.get_content_area()
            box.pack_start(sw, True, True, 0)
            dlg.show_all()
            dlg.run()
            dlg.destroy()
        self.auth_state.set_text(T("正在安装/修复…（可能弹出授权窗）"))
        run_async(worker, done)

    # ---------------- 服务 ----------------
    # ---------------- 开机自启开关 ----------------
    AUTOSTART_DESKTOP = os.path.expanduser("~/.config/autostart/system-console.desktop")

    def _autostart_enabled(self):
        return os.path.isfile(self.AUTOSTART_DESKTOP)

    def _on_autostart_toggle(self, _sw, state):
        """开关切换：写/删 ~/.config/autostart/system-console.desktop（与 install.sh [7/7] 同一文件）"""
        try:
            if state:
                os.makedirs(os.path.dirname(self.AUTOSTART_DESKTOP), exist_ok=True)
                # 与 install.sh mk_desktop 保持一致(引号包路径, 空格安全)
                exe = os.path.join(controller.BASE, "启动控制台.sh")
                with open(self.AUTOSTART_DESKTOP, "w") as f:
                    f.write("[Desktop Entry]\nType=Application\nName=系统控制台\n"
                           f'Exec="{exe}"\nPath={controller.BASE}\n'
                           "Icon=utilities-system-monitor\nTerminal=false\n"
                           "X-GNOME-Autostart-enabled=true\n")
            else:
                if os.path.isfile(self.AUTOSTART_DESKTOP):
                    os.remove(self.AUTOSTART_DESKTOP)
            self.autostart_switch.set_state(state)  # 确认状态(失败路径不会走到这)
        except OSError as e:
            self.autostart_switch.set_state(not state)  # 回滚显示
            dlg = Gtk.MessageDialog(transient_for=self.get_toplevel(), modal=True,
                                    message_type=Gtk.MessageType.ERROR,
                                    buttons=Gtk.ButtonsType.OK)
            dlg.set_markup(T("自启开关操作失败：%s") % e)
            dlg.run(); dlg.destroy()
        return True  # 阻止默认 handler 再改一次状态

    def _load_services(self):
        def worker():
            # 2026-09-08 审计 A1：附带 safeguard verdict（降压安全网状态，此前仅终端可查）
            verdict = controller.safeguard_verdict()
            return controller.service_states(), verdict

        def done(result):
            states, verdict = result
            for ch in self.svc_list.get_children():
                self.svc_list.remove(ch)
            # A1: 安全网状态徽标行（置顶）
            if verdict:
                row = Gtk.Box(spacing=8)
                n = Gtk.Label(label="uv-safeguard", xalign=0)
                n.get_style_context().add_class("mono-text")
                v_state, v_detail = verdict
                dd = Gtk.Label(label=v_detail, xalign=0)
                dd.get_style_context().add_class("dim-text")
                if v_state == "CLEAN":
                    st = Gtk.Label(label="✅ " + T("CLEAN 上次正常关机"), xalign=0)
                elif v_state == "WATCH":
                    st = Gtk.Label(label="🟡 " + T("WATCH 观察中（疑似手动重启，未回退）"), xalign=0)
                    st.set_tooltip_text(T("strike 计数：2 次内不回退，7 天后自动清零。确认手动重启后可：sudo rm -f /var/lib/uv-safeguard/watch_strike"))
                elif v_state == "CRASH_REVERT":
                    st = Gtk.Label(label="🔴 " + T("CRASH_REVERT 已回退 -50mV"), xalign=0)
                    st.set_tooltip_text(T("检测到崩溃特征已自动回退。恢复：sudo systemctl restart undervolt"))
                else:
                    st = Gtk.Label(label=v_state or T("未知"), xalign=0)
                st.get_style_context().add_class("svc-active")
                row.pack_start(n, False, False, 0)
                row.pack_start(dd, False, False, 0)
                row.pack_end(st, False, False, 0)
                self.svc_list.pack_start(row, False, False, 0)
            for name, desc, state in states:
                row = Gtk.Box(spacing=8)
                n = Gtk.Label(label=name, xalign=0)
                n.get_style_context().add_class("mono-text")
                dd = Gtk.Label(label=desc, xalign=0)
                dd.get_style_context().add_class("dim-text")
                # 2026-09-01: 已知"停止即正常"的服务标注预期，避免误解
                if state == T("已停止") and name in controller.EXPECTED_IDLE:
                    st = Gtk.Label(label=T("已停止·预期"), xalign=0)
                    st.set_tooltip_text(controller.EXPECTED_IDLE[name])
                else:
                    st = Gtk.Label(label=state or T("未知"), xalign=0)
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
            # 2026-09-01 修复: 原硬编码桌面旧路径(已删) → sudo 白名单不匹配报"需要密码"且不弹窗。
            # 改用 controller._find_script 自动定位 + _run 统一弹窗提权(白名单未配时也能授权执行)。
            # 2026-09-11 修复: 含空格原路径 sudoers 仍不匹配 → 经 _alias_script 走 /usr/local/bin 别名。
            script = controller._alias_script(controller._find_script("backend", "kernel_guard.sh"), "sc-kernel-guard.sh")
            return controller._run([script, mode], timeout=120)

        def done(result):
            rc, out, err = result
            if rc == 0:
                self.kern_buf.set_text(out)
            else:
                self.kern_buf.set_text(T("内核守卫执行失败：%s\n%s") % (err or out, out))
            self.refresh_kern_ver()

        self.kern_buf.set_text(T("内核守卫运行中（%s）…") % (T("修复") if mode == "repair" else T("检测")))
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
                self.kern_ver.set_text(T("内核 %s") % v)

        run_async(worker, done)

    # ---------------- 性能日志 ----------------
    def _open_perf_log(self, _btn=None):
        dlg = Gtk.Dialog(title=T("性能日志回看"), transient_for=self.get_toplevel(), modal=True)
        dlg.set_default_size(720, 480)
        box = dlg.get_content_area()

        hbox = Gtk.Box(spacing=8)
        hbox.set_margin_top(8)
        hbox.set_margin_start(8)
        hbox.set_margin_end(8)
        lab = Gtk.Label(label=T("时间范围："), xalign=0)
        combo = Gtk.ComboBoxText()
        for label, hours in [(T("最近 1 小时"), 1), (T("最近 6 小时"), 6), (T("最近 24 小时"), 24), (T("最近 7 天"), 168)]:
            combo.append(str(hours), label)
        combo.set_active(0)
        hbox.pack_start(lab, False, False, 0)
        hbox.pack_start(combo, False, False, 0)

        refresh_btn = Gtk.Button(label=T("刷新"))
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
            # 2026-09-11 修复: 原同步加载在主线程跑全量 TSV(7 天档几千行遍历+排序),
            # GTK 主循环冻结 → 对话框/主窗都关不掉。改 run_async 后台加载(与维护页
            # 其他按钮同模式), 先显示提示文案。
            hours = float(combo.get_active_id() or 1)
            buf.set_text(T("加载中（{}h）…").format(hours))

            def worker():
                from src.core.perf_logger import get_perf_history, get_perf_stats
                hist = get_perf_history(hours)
                stats = get_perf_stats(hours)

                lines = []
                # 2026-09-07 审计 A4：最新实时采样头部（get_latest_* 是进程内存 buffer，
                # 维护页独立进程下恒空——改从 history 尾行取最新，语义等价且跨进程可用）
                if hist:
                    last = hist[-1]
                    lines.append(T("━━ 最新采样（{} 实时） ━━").format(last.get("datetime", "")))
                    lines.append(T("功耗 {:.1f}W · 频率 {:.0f}MHz · 温度 {:.0f}°C · GPU {:.0f}%").format(
                        last.get("pkg_w") or 0, last.get("cpu_freq_avg") or 0,
                        last.get("cpu_temp") or 0, last.get("gpu_util") or 0))
                    lines.append("")
                lines.append(T("=== 性能数据统计（{}h） ===").format(hours))
                lines.append(T("采样数: {}").format(stats.get('samples', 0)))
                pw = stats.get('pkg_power', {})
                lines.append(T("整机功耗: 平均 {:.1f}W / 最大 {:.1f}W / 最小 {:.1f}W").format(
                    pw.get('avg', 0), pw.get('max', 0), pw.get('min', 0)))
                tp = stats.get('temp', {})
                lines.append(T("CPU 温度: 平均 {:.1f}°C / 最高 {:.1f}°C / 最低 {:.1f}°C").format(
                    tp.get('avg', 0), tp.get('max', 0), tp.get('min', 0)))
                lines.append(T("限流事件: {} 次").format(stats.get('throttle_events', 0)))
                lines.append("")
                lines.append(T("=== 最近 20 条记录 ==="))
                lines.append(T("时间          频率     温度   功耗   状态"))
                lines.append("-" * 55)
                for d in hist[-20:]:
                    ts = time.strftime("%H:%M:%S", time.localtime(d['timestamp']))
                    th = []
                    if d.get('throttle_thermal'):
                        th.append(T("热({})").format(d['throttle_thermal']))
                    if d.get('throttle_power'):
                        th.append(T("功({})").format(d['throttle_power']))
                    status = ",".join(th) if th else T("正常")
                    lines.append(
                        f"{ts}  {d.get('cpu_freq_max', 0):.0f}MHz  {d.get('cpu_temp', 0):.0f}°C  "
                        f"{d.get('pkg_w', 0):.1f}W  {status}"
                    )
                return "\n".join(lines)

            def done(result):
                # run_async 出错时返回 (rc, out, err) 元组
                if isinstance(result, tuple):
                    buf.set_text(T("加载失败: {}\n可能尚未有性能数据记录").format(
                        result[2] if len(result) > 2 else result))
                else:
                    buf.set_text(result)

            run_async(worker, done)

        refresh_btn.connect("clicked", load_data)
        combo.connect("changed", load_data)

        dlg.show_all()
        load_data()
        dlg.run()
        dlg.destroy()

    # ---------------- 应用功耗排行 ----------------
    def _open_app_power(self, _btn=None):
        dlg = Gtk.Dialog(title=T("应用功耗排行（cgroup 分析）"), transient_for=self.get_toplevel(), modal=True)
        dlg.set_default_size(640, 460)
        box = dlg.get_content_area()
        box.set_spacing(8)
        box.set_margin_top(10)
        box.set_margin_start(10)
        box.set_margin_end(10)

        note = Gtk.Label(label=T("基于 cgroup CPU 时间差分估算功耗占比。首次打开为基线，3 秒后点刷新看数据。"), xalign=0)
        note.get_style_context().add_class("dim-text")
        box.pack_start(note, False, False, 0)

        store = Gtk.ListStore(str, float, float, float, float, str)
        tree = Gtk.TreeView(model=store, enable_grid_lines=True)

        for i, (title, xalign) in enumerate([(T("应用"), 0.0), ("CPU %", 1.0), (T("功耗 W"), 1.0), (T("占比 %"), 1.0), (T("内存 MB"), 1.0), (T("类型"), 0.5)]):
            cell = Gtk.CellRendererText()
            cell.set_property("xalign", xalign)
            col = Gtk.TreeViewColumn(title, cell, text=i)
            # 2026-09-11: float 列直接 str() 渲染会露浮点长尾(0.09335814...)
            # → cell_data_func 统一定点格式: CPU%/占比 1 位, 功耗 2 位, 内存整数
            _fmt = ["", "%.1f", "%.2f", "%.1f", "%.0f", ""][i]
            if _fmt:
                def _fmt_cell(_col, _cell, model, it, f=_fmt):
                    _cell.set_property("text", f % model.get_value(it, _col.get_sort_column_id()))
                col.set_cell_data_func(cell, _fmt_cell)
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
        refresh_btn = Gtk.Button(label=T("🔄 刷新"))
        refresh_btn.get_style_context().add_class("suggested-action")
        auto_check = Gtk.CheckButton(label=T("自动刷新 (3s)"))
        pkg_label = Gtk.Label(label="", xalign=0)
        pkg_label.get_style_context().add_class("dim-text")
        btn_row.pack_start(refresh_btn, False, False, 0)
        btn_row.pack_start(auto_check, False, False, 0)
        btn_row.pack_end(pkg_label, False, False, 0)
        box.pack_start(btn_row, False, False, 0)

        auto_id = [0]
        # 2026-09-11 修复: 原每次 refresh 新建 Collector → RAPL 差分永远没有基线,
        # power_w 恒 None → 功耗/占比列永远空。差分必须同一实例前后两次采样,
        # 对话框级复用(与 app_power 模块级单例 monitor 同理)。
        _collector = [None]

        def refresh(_btn=None):
            try:
                pw = None
                try:
                    from collector import Collector
                    if _collector[0] is None:
                        _collector[0] = Collector()
                    d = _collector[0].sample()
                    pw = d.get("power_w")
                except Exception:
                    pass

                from src.core.app_power import get_app_power_ranking
                results = get_app_power_ranking(pw)

                store.clear()
                for r in results:
                    typ = T("图形应用") if r.is_app else T("服务/后台")
                    store.append([r.name, round(r.cpu_pct, 1), round(r.power_w, 2),
                                  round(r.pct_of_total, 1), round(r.mem_mb, 0), typ])

                if pw:
                    pkg_label.set_text(T("整机功耗: {:.1f}W").format(pw))
            except Exception as e:
                store.clear()
                store.append([T("加载失败: {}").format(e), 0, 0, 0, 0, ""])

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
        # 2026-09-11 修复: 缺 dlg.run() 模态循环 → _open_app_power 返回后 dlg 失去
        # 引用被 GC, 对话框闪现即灭/交互异常(性能日志对话框有 run(), 这个漏了)
        dlg.run()
        dlg.destroy()

    # ---------------- MCE ----------------
    def _on_mce(self, _btn):
        def worker():
            # 2026-09-07 审计 A2：同时取权威 CPU MCE 计数（P0-1 修复的 ras-mc-ctl 精确解析）
            # mce_count 返回 int（0=无 MCE）/ None（ras-mc-ctl 不可用，按未知处理不误报）
            try:
                cnt = controller.mce_count()
            except Exception:
                cnt = None
            rc, out, err = controller.ras_errors()
            return rc, out, err, cnt

        def done(result):
            rc, out, err, mce = result
            d = Gtk.MessageDialog(
                transient_for=self.get_toplevel(), modal=True,
                message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK)
            if rc == 0:
                txt = out.strip() or T("无记录")
                # A2: 权威 CPU MCE 计数徽标（区分 CPU MCE vs PCIe AER，旧版易混淆）
                if mce is not None:
                    badge = ("✅ " + T("真实 CPU MCE 计数: {}（零错误）").format(mce)) if mce == 0 \
                            else ("🔴 " + T("真实 CPU MCE 计数: {}（存在硬件错误！）").format(mce))
                else:
                    badge = "⚪ " + T("ras-mc-ctl 不可用，无法区分 CPU MCE 与 PCIe AER")
                txt = badge + "\n\n" + txt
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
                d.set_markup(T("<b>RAS / MCE 事件</b>\n（内存错误 / PCIe AER / 机器检查）"))
            else:
                d.set_markup(T("<b>查询失败</b>\n%s") % (err or out))
            d.show_all()
            d.run()
            d.destroy()

        run_async(worker, done)

    # ---------------- 隐形功能 GUI 化（2026-09-07 审计 A/B 类收编）----------------
    def _on_system_snapshot(self, _btn):
        """A1: 完整系统状态快照（tlp-stat 风格全景）"""
        def worker():
            return controller.system_snapshot()

        def done(result):
            rc, out, err = result
            if rc == 0 and out:
                self._show_ops_result(T("📋 系统诊断快照"), result, scroll=True)
            else:
                self._show_ops_result(T("📋 系统诊断快照（失败）"), result, scroll=True)

        run_async(worker, done)

    def _on_conflict_recheck(self, _btn):
        """B6: 运行期冲突复查（互斥工具 + double-sudo）"""
        def worker():
            return controller.conflict_recheck()

        def done(result):
            self._show_ops_result(T("🔍 冲突与安全复查"), result, scroll=True)

        run_async(worker, done)
    def _show_ops_result(self, title, result, scroll=True):
        """统一结果对话框（长输出滚动显示）"""
        rc, out, err = result
        d = Gtk.MessageDialog(
            transient_for=self.get_toplevel(), modal=True,
            message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK)
        d.set_markup("<b>%s</b>" % title)
        txt = (out or "").strip() or T("(无输出)")
        if err and rc != 0:
            txt += T("\n\n[错误] ") + err.strip()
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
        dlg = Gtk.Dialog(title=T("创建系统快照"), transient_for=self.get_toplevel(),
                         modal=True, default_width=520)
        box = dlg.get_content_area()
        box.set_spacing(6)
        box.set_margin_top(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        lab = Gtk.Label(label=T("快照说明（例如：-100mV 降压前）："), xalign=0)
        entry = Gtk.Entry()
        entry.set_width_chars(40)
        box.pack_start(lab, False, False, 6)
        box.pack_start(entry, False, False, 6)
        # 备份盘选择
        dlab = Gtk.Label(label=T("备份位置（默认系统盘 /dev/sdb2）："), xalign=0)
        combo = Gtk.ComboBoxText()
        combo.append("", T("（默认 - 系统盘）"))
        for dev, size, fstype, label, mount in controller.snapshot_devices():
            desc = "%s (%s %s%s%s)" % (dev, size, fstype or "?",
                   (" " + label) if label else "",
                   (" → " + mount) if mount else "")
            combo.append(dev, desc)
        combo.set_active(0)
        box.pack_start(dlab, False, False, 6)
        box.pack_start(combo, False, False, 6)
        note = Gtk.Label(
            label=T("⚠ 选 NTFS(WS) 等数据盘可能不被 timeshift 支持，建议选未挂载的 ext4/btrfs 分区。"),
            xalign=0, wrap=True)
        note.get_style_context().add_class("dim-text")
        box.pack_start(note, False, False, 4)
        dlg.add_button(T("取消"), Gtk.ResponseType.CANCEL)
        dlg.add_button(T("创建"), Gtk.ResponseType.OK)
        dlg.show_all()
        resp = dlg.run()
        desc = entry.get_text().strip()
        target = combo.get_active_id() or ""
        dlg.destroy()
        if resp != Gtk.ResponseType.OK:
            return
        if not desc:
            desc = T("控制台手动快照")

        def worker():
            return controller.snapshot("create", desc, target)

        def done(result):
            self.ops_state.set_text(T("快照: ") + (T("完成") if result[0] == 0 else T("失败")))
            self._show_ops_result(T("系统快照"), result, scroll=False)

        run_async(worker, done)

    def _on_snapshot_list(self, _btn):
        def worker():
            return controller.snapshot("list")

        def done(result):
            self._show_ops_result(T("Timeshift 快照列表"), result)

        run_async(worker, done)

    def _on_snapshot_delete(self, _btn):
        """删除快照：先列出选择，再危险确认"""
        def worker():
            return controller.snapshot("list")

        def choose(result):
            rc, out, err = result
            if rc != 0:
                self._show_ops_result(T("快照列表"), result, scroll=False)
                return
            # 解析快照编号与标签
            import re
            snaps = []
            for line in (out or "").splitlines():
                m = re.match(r"^(\d+)\s+>\s+(\S+)\s+(\S+)", line.strip())
                if m and m.group(3) not in ("(current)",):
                    snaps.append((m.group(1), m.group(2), line.strip()))
            if not snaps:
                self.ops_state.set_text(T("无快照可删除"))
                return
            # 选择对话框
            dlg = Gtk.Dialog(title=T("选择要删除的快照"), transient_for=self.get_toplevel(),
                             modal=True, default_width=560)
            box = dlg.get_content_area()
            store = Gtk.ListStore(str, str, str)
            for idx, ts, raw in snaps:
                store.append([idx, ts, raw[:70]])
            tree = Gtk.TreeView(model=store)
            for i, title in enumerate([T("编号"), T("时间"), T("详情")]):
                cell = Gtk.CellRendererText()
                col = Gtk.TreeViewColumn(title, cell, text=i)
                tree.append_column(col)
            sw = Gtk.ScrolledWindow()
            sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            sw.add(tree)
            sw.set_size_request(-1, 220)
            box.pack_start(sw, True, True, 0)
            dlg.add_button(T("取消"), Gtk.ResponseType.CANCEL)
            dlg.add_button(T("删除选中"), Gtk.ResponseType.OK)
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
                T('<b>确认删除快照？</b>\n\n快照: %s (%s)\n\n⚠ 删除后无法恢复！') % (idx, ts))
            confirm.add_button(T("取消"), Gtk.ResponseType.NO)
            b_del = confirm.add_button(T("永久删除"), Gtk.ResponseType.YES)
            b_del.get_style_context().add_class("destructive-action")
            r2 = confirm.run()
            confirm.destroy()
            if r2 != Gtk.ResponseType.YES:
                return

            def do_delete():
                return controller.snapshot("delete", idx)

            def deleted(result):
                self.ops_state.set_text(T("快照: ") + (T("已删除") if result[0] == 0 else T("失败")))
                self._show_ops_result(T("删除快照"), result, scroll=False)

            run_async(do_delete, deleted)

        run_async(worker, choose)

    def _on_quiet(self, _btn, quiet):
        def worker():
            return controller.quiet_background(quiet)

        def done(result):
            self.ops_state.set_text(result[1].strip()[:60] if result[0] == 0 else (T("失败: ") + result[2][:60]))
            self._show_ops_result(T("后台降权") if quiet else T("恢复优先级"), result, scroll=False)

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
                d.set_markup("<b>%s</b>" % (T("已加载温度模块") if load else T("已卸载温度模块")))
            else:
                d.set_markup(T("<b>操作失败</b>（rc=%s）\n%s") % (rc, err or out))
            d.run()
            d.destroy()

        run_async(worker, done)

    def refresh_temp_state(self):
        def worker():
            import subprocess
            r = subprocess.run(["lsmod"], capture_output=True, text=True)
            return T("已加载") if "acer_wmi_battery" in r.stdout else T("未加载")

        def done(s):
            self.temp_state.set_text(s)

        run_async(worker, done)

    # ---------------- 状态刷新（console tick 调用）----------------
    def refresh_state(self, d=None):
        pass  # 维护页无实时数据需求，服务状态手动刷新