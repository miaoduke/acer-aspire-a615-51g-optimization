#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""console.py — 系统控制台主程序（Python3 + GTK3）
启动: python3 console.py   安装: sudo bash install.sh
"""
import os
import sys
import time

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collector import Collector
from ui_dashboard import DashboardPage
from ui_scenes import ScenesPage
from ui_advanced import AdvancedPage
from ui_maintenance import MaintenancePage
from ui_battery import BatteryPage
from ui_docs import DocumentationPage
import controller

CSS = """
#stat-card {
  background: @theme_base_color;
  border: 1px solid @borders;
  border-radius: 8px;
  padding: 10px;
}
.card-title { font-size: 12px; opacity: 0.7; }
.card-value { font-weight: bold; }
.card-unit { font-size: 10px; opacity: 0.6; }
.section-title { font-weight: bold; font-size: 14px; }
.dim-text { color: @insensitive_fg_color; }
.mono-text { font-family: monospace; font-size: 12px; }
.detail-value { font-family: monospace; }
.scene-name { font-weight: bold; font-size: 13px; }
.scene-desc { font-size: 10px; color: @insensitive_fg_color; }
.scene-active {
  background: #2e7d32;
  color: white;
  border-radius: 8px;
}
.scene-active .scene-name { color: white; }
.scene-active .scene-desc { color: rgba(255,255,255,0.8); }
.svc-active { color: #2e7d32; }
.svc-inactive { color: #e65100; }
.svc-failed { color: #c62828; }
.svc-unknown { color: #757575; }
.badge { font-weight: bold; padding: 2px 8px; border-radius: 10px; }
.badge-ac { background: #2e7d32; color: white; }
.badge-dc { background: #e65100; color: white; }
"""


class ConsoleApp:
    def __init__(self):
        self.collector = Collector()
        self._timer = None
        self._interval = 1000  # ms
        self._iconified = False

        # CSS
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # 窗口
        self.win = Gtk.Window(title="系统控制台")
        self.win.set_default_size(960, 640)
        self.win.set_size_request(800, 480)
        self.win.set_position(Gtk.WindowPosition.CENTER)
        self.win.connect("destroy", Gtk.main_quit)
        self.win.connect("window-state-event", self._on_state)
        self.win.connect("focus-in-event", lambda *_: self._reschedule())
        self.win.connect("focus-out-event", lambda *_: self._reschedule())

        # HeaderBar
        hb = Gtk.HeaderBar()
        hb.set_show_close_button(True)
        hb.set_title("系统控制台")
        hb.set_subtitle("Acer A615-51G · i5-8250U · MX150")
        # 电源场景下拉快捷切换（最右，按钮文字动态显示当前场景）
        self.scene_menu = Gtk.Menu()
        for key, (name, desc) in controller.SCENES.items():
            item = Gtk.MenuItem(label="%s（%s）" % (name, desc))
            item.connect("activate", self._on_menu_scene, key)
            self.scene_menu.append(item)
        # M3 菜单项（联动：进入/退出互斥显示，M3 生效时进入项置灰）
        self.scene_menu.append(Gtk.SeparatorMenuItem())
        self.m3_menu_on = Gtk.MenuItem(label="M3 离电效能（进入）")
        self.m3_menu_on.connect("activate", self._on_menu_m3, True)
        self.scene_menu.append(self.m3_menu_on)
        self.m3_menu_off = Gtk.MenuItem(label="M3 离电效能（退出）")
        self.m3_menu_off.connect("activate", self._on_menu_m3, False)
        self.scene_menu.append(self.m3_menu_off)
        self.scene_menu.show_all()
        self.scene_btn = Gtk.MenuButton(label="场景")
        self.scene_btn.set_popup(self.scene_menu)
        self.scene_btn.set_tooltip_text("快速切换电源场景（等效电源场景页）")
        # AC/DC 徽标：独立检测当前供电状态，放在场景按钮之前（左侧）
        self.badge_ac = Gtk.Label(label="AC")
        self.badge_ac.get_style_context().add_class("badge")
        self.badge_ac.get_style_context().add_class("badge-ac")
        hb.pack_end(self.scene_btn)
        hb.pack_end(self.badge_ac)
        self.win.set_titlebar(hb)

        # 主体：左侧导航 + Stack
        main = Gtk.Box(spacing=0)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.pages = {}
        for name, cls in (("总览", DashboardPage), ("电源场景", ScenesPage),
                          ("电池保养", BatteryPage), ("高级控制", AdvancedPage),
                          ("系统维护", MaintenancePage), ("说明文档", DocumentationPage)):
            page = cls()
            sw = Gtk.ScrolledWindow()
            sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            sw.add(page)
            self.stack.add_named(sw, name)
            self.pages[name] = page

        nav = Gtk.ListBox()
        nav.set_selection_mode(Gtk.SelectionMode.SINGLE)
        nav.set_size_request(150, -1)
        # 2026-08-31 修复: 原导航列表漏"说明文档"——该页(591行)注册进了 stack
        # 却无任何入口，成为不可达页面。
        for name in ("总览", "电源场景", "电池保养", "高级控制", "系统维护", "说明文档"):
            row = Gtk.ListBoxRow()
            lab = Gtk.Label(label=name, xalign=0)
            lab.set_margin_start(14)
            lab.set_margin_end(14)
            lab.set_margin_top(10)
            lab.set_margin_bottom(10)
            row.add(lab)
            nav.add(row)
        nav.connect("row-selected", self._on_nav)

        main.pack_start(nav, False, False, 0)
        main.pack_start(self.stack, True, True, 0)
        self.win.add(main)
        nav.select_row(nav.get_row_at_index(0))

        self.win.show_all()
        self._reschedule()
        self._setup_tray()
        
        # ---- 新功能集成（2026-08-21）----
        self._setup_notifications()
        self._setup_perf_logging()
        self._setup_load_advisor()

    def _setup_notifications(self):
        """初始化通知系统"""
        try:
            from src.core.notification import get_notification_manager
            self.notifier = get_notification_manager()
        except Exception as e:
            print(f"通知系统初始化失败: {e}")
            self.notifier = None

    def _setup_perf_logging(self):
        """初始化性能日志（每 30s 记录一次）"""
        try:
            from src.core.perf_logger import get_perf_manager, PerfSample, BatterySample
            from datetime import datetime
            self._perf_mgr = get_perf_manager()
            self._perf_count = [0]
            
            def log_sample(d):
                """每 30 秒记录一次（时间驱动，不受 tick 间隔影响）"""
                now = time.time()
                if now - getattr(self, '_last_perf_log', 0) < 30:
                    return
                self._last_perf_log = now
                
                try:
                    cpu = d.get("cpu", [])
                    freqs = [f for _, f in cpu if f]
                    pd = d.get("power_dc") or {}
                    eco = d.get("eco", {})
                    
                    sample = PerfSample(
                        timestamp=time.time(),
                        datetime_str=datetime.now().strftime("%H:%M:%S"),
                        cpu_freq_max=max(freqs) if freqs else 0,
                        cpu_freq_avg=sum(freqs)/len(freqs) if freqs else 0,
                        cpu_temp=d.get("temp") or 0,
                        cpu_usage_pct=sum(c[0] or 0 for c in cpu) / max(1, len(cpu)),
                        pkg_power_w=d.get("power_w") or 0,
                        core_power_w=pd.get("core", 0),
                        uncore_power_w=pd.get("uncore", 0),
                        dram_power_w=pd.get("dram", 0),
                        throttle_thermal=0,  # MSR 读取太慢，日志里暂记 0
                        throttle_power=0,
                        throttle_current=0,
                        throttle_vr_thermal=0,
                        throttle_vr_current=0,
                        pl1_active=False,
                        pl2_active=False,
                        bd_prochot=False,
                        gpu_util=(d.get("gpu") or {}).get("util") or 0,
                        gpu_temp=(d.get("gpu") or {}).get("temp") or 0,
                        gpu_power=(d.get("gpu") or {}).get("power") or 0,
                        mem_used_mb=(d.get("mem") or {}).get("used_mb") or 0,
                        mem_total_mb=(d.get("mem") or {}).get("total_mb") or 0,
                        mem_pct=(d.get("mem") or {}).get("pct") or 0,
                        net_rx_kbps=0, net_tx_kbps=0,
                        disk_read_kbps=0, disk_write_kbps=0,
                    )
                    self._perf_mgr.record_perf(sample)
                    
                    # 电池采样
                    b = d.get("bat", {})
                    cur_ma = vol_mv = 0
                    try:
                        cur_ma = int(open("/sys/class/power_supply/BAT1/current_now").read().strip()) // 1000
                        vol_mv = int(open("/sys/class/power_supply/BAT1/voltage_now").read().strip()) // 1000
                    except Exception:
                        pass
                    bsample = BatterySample(
                        timestamp=time.time(),
                        datetime_str=datetime.now().strftime("%H:%M:%S"),
                        capacity_pct=b.get("capacity") or 0,
                        status=b.get("status") or "Unknown",
                        power_w=b.get("power_w") or 0,
                        current_ma=cur_ma,
                        voltage_mv=vol_mv,
                        charge_full_uwh=0,
                        charge_full_design_uwh=0,
                        health_pct=b.get("health") or 0,
                        cycle_count=0,
                        phase=b.get("phase") or "unknown",
                        temp_c=b.get("temp_c") or 0,
                    )
                    self._perf_mgr.record_battery(bsample)
                except Exception:
                    pass
            
            self._perf_log_fn = log_sample
        except Exception as e:
            print(f"性能日志初始化失败: {e}")
            self._perf_log_fn = None

    def _setup_load_advisor(self):
        """初始化负载建议器"""
        try:
            from src.core.load_advisor import start_load_advisor
            start_load_advisor(scene_provider=lambda: controller.get_active_scene(
                self.collector.sample()["params"]) or "")
        except Exception as e:
            print(f"负载建议器初始化失败: {e}")

    def _setup_tray(self):
        """系统托盘（Gtk.StatusIcon，Cinnamon/X11 原生支持；GNOME/Wayland 需 appindicator 扩展）"""
        try:
            self.tray = Gtk.StatusIcon()
            self.tray.set_from_icon_name("battery")
            self.tray.set_title("系统控制台")
            self.tray.set_tooltip_text("系统控制台")
            menu = Gtk.Menu()
            item_show = Gtk.MenuItem(label="显示 / 隐藏")
            item_show.connect("activate", lambda *_: self._toggle_win())
            menu.append(item_show)
            menu.append(Gtk.SeparatorMenuItem())
            for key, (name, desc) in controller.SCENES.items():
                item = Gtk.MenuItem(label="场景：%s" % name)
                item.connect("activate", self._on_menu_scene, key)
                menu.append(item)
            menu.append(Gtk.SeparatorMenuItem())
            item_quit = Gtk.MenuItem(label="退出")
            item_quit.connect("activate", lambda *_: self.win.destroy())
            menu.append(item_quit)
            menu.show_all()
            self.tray.connect("popup-menu", lambda icon, btn, time: menu.popup(
                None, None, Gtk.StatusIcon.position_menu, icon, btn, time))
            self.tray.connect("activate", lambda *_: self._toggle_win())
        except Exception:
            self.tray = None  # 环境不支持则静默降级

    def _toggle_win(self):
        if self.win.get_visible():
            self.win.hide()
        else:
            self.win.present()
            self._reschedule()

    def _on_nav(self, box, row):
        if row is not None:
            child = row.get_child()
            self.stack.set_visible_child_name(child.get_text())

    def _on_menu_scene(self, _item, key):
        """HeaderBar 下拉快速切换场景"""
        name = controller.SCENES[key][0]

        def done(result):
            GLib.idle_add(self._menu_scene_done, result, name)

        from async_util import run_async
        run_async(lambda: controller.set_scene(key), done)

    def _on_menu_m3(self, _item, on):
        """HeaderBar 下拉 M3 进入/退出（联动 GPU 交互）"""
        def done(result):
            GLib.idle_add(self._menu_m3_done, result, on)

        from async_util import run_async
        run_async(lambda: controller.m3_mode(on), done)

    def _menu_m3_done(self, result, on):
        rc, out, err = result
        dlg = Gtk.MessageDialog(
            transient_for=self.win, modal=True,
            message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK)
        if rc == 0:
            dlg.set_markup("<b>%s</b>\n\n%s" % (
                "已进入 M3 离电效能模式" if on else "已退出 M3，恢复自动模式",
                out.strip() or "（无输出）"))
        else:
            dlg.set_markup("<b>操作失败</b>（rc=%s）\n%s" % (rc, err or out))
        dlg.run()
        dlg.destroy()
        if rc == 0:
            # GPU 切换交互（复用场景页逻辑）
            self.pages["电源场景"]._ask_gpu(on)
            self.pages["电源场景"].refresh_state()

    def _menu_scene_done(self, result, name):
        rc, out, err = result
        dlg = Gtk.MessageDialog(
            transient_for=self.win, modal=True,
            message_type=Gtk.MessageType.INFO if rc == 0 else Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK)
        if rc == 0:
            try:
                from collector import Collector
                p = Collector().sample()["params"]
                verify = ("Governor=%s\nEPP=%s\nPL1=%s W\nTurbo=%s" % (
                    p.get("governor") or "—", p.get("epp") or "—",
                    ("%.0f" % p["pl1_w"]) if p["pl1_w"] is not None else "—",
                    "ON" if p["turbo"] is True else ("OFF" if p["turbo"] is False else "—")))
                dlg.set_markup("<b>已切换场景：%s</b>\n\n切换后实测参数：\n%s" % (name, verify))
            except Exception:
                dlg.set_markup("<b>已切换场景：%s</b>" % name)
        else:
            dlg.set_markup("<b>切换失败</b>（rc=%s）\n%s" % (rc, err or out))
        dlg.run()
        dlg.destroy()
        self.pages["电源场景"].refresh_state()

    def _on_state(self, _win, event):
        self._iconified = bool(event.new_window_state & Gdk.WindowState.ICONIFIED)
        self._reschedule()
        return False

    def _reschedule(self):
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None
        if self._iconified or not self.win.get_visible():
            # 窗口最小化/托盘隐藏：暂停数据刷新 tick（省电，托盘菜单仍可操作）
            return
        focused = self.win.is_active()
        self._interval = 1000 if focused else 5000
        self._timer = GLib.timeout_add(self._interval, self._tick)

    def _tick(self):
        d = self.collector.sample()
        
        # 电池使用统计（离电时长 + 循环计数）——先更新再刷新页面
        usage_snap = None
        try:
            from src.core.battery_stats import get_tracker
            if not hasattr(self, '_batt_tracker'):
                self._batt_tracker = get_tracker()
            usage_snap = self._batt_tracker.update()
        except Exception:
            pass
        
        self.pages["总览"].update(d)
        self.pages["电源场景"].refresh_state(d)
        self.pages["电池保养"].refresh_state(d, usage_snap)
        self.pages["高级控制"].refresh_state(d)
        
        # 性能日志记录（内部有 30 次节流）
        if hasattr(self, '_perf_log_fn') and self._perf_log_fn:
            try:
                self._perf_log_fn(d)
            except Exception:
                pass
        
        # 温度告警检查
        if hasattr(self, 'notifier') and self.notifier:
            try:
                temp = d.get("temp")
                if temp is not None and temp >= 78:
                    self.notifier.notify_temp_warning(temp, "CPU")
                # 电池低电量告警
                b = d.get("bat", {})
                if b.get("status") == "Discharging" and b.get("capacity") is not None:
                    if b["capacity"] <= 15:
                        self.notifier.notify_battery_low(b["capacity"], b.get("status", ""))
            except Exception:
                pass
        
        # 状态徽标（AC/DC 独立检测）
        if d["ac"] is True:
            self.badge_ac.get_style_context().remove_class("badge-dc")
            self.badge_ac.get_style_context().add_class("badge-ac")
            self.badge_ac.set_text("AC")
        elif d["ac"] is False:
            self.badge_ac.get_style_context().remove_class("badge-ac")
            self.badge_ac.get_style_context().add_class("badge-dc")
            self.badge_ac.set_text("DC")
        # 场景按钮文字：M3 生效时显示 M3 状态，否则显示当前生效场景
        m3 = controller.m3_active()
        if m3:
            self.scene_btn.set_label("M3 省电")
        else:
            active = controller.get_active_scene(d["params"])
            if active:
                self.scene_btn.set_label(controller.SCENES[active][0])
        # 场景菜单 M3 项联动：进入/退出互斥
        self.m3_menu_on.set_sensitive(not m3)
        self.m3_menu_off.set_sensitive(m3)
        return True  # 持续调度

    def run(self):
        if not controller.sudo_ok():
            dlg = Gtk.MessageDialog(
                transient_for=self.win, modal=True,
                message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.OK)
            dlg.set_markup(
                "<b>sudo 免密白名单未配置</b>\n\n"
                "控制功能（场景切换/GPU 切换/M3）将不可用。\n"
                "请执行:  sudo bash install.sh\n"
                "（监控功能不受影响）")
            dlg.run()
            dlg.destroy()
        Gtk.main()


if __name__ == "__main__":
    ConsoleApp().run()