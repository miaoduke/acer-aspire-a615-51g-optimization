"""
ui_processes.py — W1 实施: G3 进程工具 GUI 集成

把 src/core/process_utils.py 集成到控制台 GUI
新增"进程详情"页（在左侧导航加一项）
"""
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.process_utils import list_processes, read_process, kill_process, renice_process
from src.core.i18n import T


class ProcessesPage(Gtk.Box):
    """进程详情页（左侧导航第 7 项）"""

    REFRESH_INTERVAL = 3000  # 3s

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_top(10)
        self.set_margin_start(10)
        self.set_margin_end(10)

        # ---- 标题 + 工具栏 ----
        header = Gtk.Box(spacing=10)
        title = Gtk.Label(label=T("<b>进程详情</b>（Top 50 by PSS 内存）"), use_markup=True, xalign=0)
        title.get_style_context().add_class("section-title")
        header.pack_start(title, True, True, 0)

        self.refresh_btn = Gtk.Button(label=T("🔄 刷新"))
        self.refresh_btn.connect("clicked", lambda *_: self._refresh())
        header.pack_end(self.refresh_btn, False, False, 0)

        # 搜索框
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(T("按名称或命令行过滤"))
        self.search_entry.connect("search-changed", lambda *_: self._refresh())
        header.pack_end(self.search_entry, False, False, 0)
        self.pack_start(header, False, False, 0)

        # 2026-09-07 审计 S1/S2：可发现性提示（右键/双击功能无提示是用户不知道的主因）
        hint = Gtk.Label(
            label=T("💡 双击行看进程详情 · 右键行可 kill / 调优先级"),
            xalign=0)
        hint.get_style_context().add_class("dim-text")
        self.pack_start(hint, False, False, 2)

        # ---- 进程列表（TreeView）----
        self.liststore = Gtk.ListStore(int, str, str, int, float, int, int)  # pid, user, name, pss_kb, cpu_pct, threads, rss_kb
        self.treeview = Gtk.TreeView(model=self.liststore)
        self.treeview.set_headers_clickable(True)
        self.treeview.connect("row-activated", self._on_row_activated)
        self.treeview.connect("button-press-event", self._on_button_press)

        # 列
        cols = [
            ("PID", 0, 70),
            ("USER", 1, 90),
            ("NAME", 2, 180),
            ("PSS(KB)", 3, 100),
            ("CPU%", 4, 70),
            (T("线程"), 5, 60),
            ("RSS(KB)", 6, 100),
        ]
        for title, col_id, width in cols:
            renderer = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, renderer, text=col_id)
            col.set_resizable(True)
            col.set_min_width(width)
            col.set_sort_column_id(col_id)
            self.treeview.append_column(col)

        # 让数字列右对齐
        for col_id in (0, 3, 4, 5, 6):
            self.treeview.get_column(cols.index(next(c for c in cols if c[1] == col_id))).set_alignment(1.0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(self.treeview)
        scrolled.set_vexpand(True)
        self.pack_start(scrolled, True, True, 0)

        # ---- 状态栏 ----
        self.status_label = Gtk.Label(label="", xalign=0)
        self.status_label.get_style_context().add_class("dim-text")
        self.pack_start(self.status_label, False, False, 0)

        # 首次加载
        self._refresh()

        # 定时刷新
        self._timer = GLib.timeout_add(self.REFRESH_INTERVAL, self._auto_refresh)

    def _auto_refresh(self):
        self._refresh()
        return True

    def _refresh(self):
        filter_text = self.search_entry.get_text().strip() if hasattr(self, 'search_entry') else ""
        procs = list_processes(filter_text if filter_text else None, limit=50)

        self.liststore.clear()
        for p in procs:
            self.liststore.append([
                p.pid, p.user, p.name, p.pss_kb, p.cpu_pct, p.threads, p.rss_kb,
            ])

        # 更新状态栏
        total_pss = sum(p.pss_kb for p in procs)
        self.status_label.set_markup(
            T("<small>显示 {} 个进程 · 总 PSS: {} MB · 按 PSS 降序 · 自动刷新 {}s</small>").format(
                len(procs), total_pss // 1024, self.REFRESH_INTERVAL // 1000)
        )

    def _on_row_activated(self, treeview, path, column):
        """双击行：显示进程详情"""
        model = treeview.get_model()
        iter_ = model.get_iter(path)
        pid = model.get_value(iter_, 0)
        self._show_details(pid)

    def _on_button_press(self, widget, event):
        """右键弹出菜单"""
        if event.button != 3:  # 3 = 右键
            return False
        # 找点击的行
        result = self.treeview.get_path_at_pos(int(event.x), int(event.y))
        if result is None:
            return False
        path, col, x, y = result
        self.treeview.set_cursor(path, col, 0)
        model = self.treeview.get_model()
        iter_ = model.get_iter(path)
        pid = model.get_value(iter_, 0)
        self._show_context_menu(pid, event)
        return True

    def _show_context_menu(self, pid, event):
        """右键菜单：kill / renice / 详情"""
        menu = Gtk.Menu()
        menu.attach_to_widget(self.treeview, lambda *_: None)

        item_details = Gtk.MenuItem(label=T("查看 PID {} 详情").format(pid))
        item_details.connect("activate", lambda *_: self._show_details(pid))
        menu.append(item_details)

        menu.append(Gtk.SeparatorMenuItem())

        # Kill 子菜单
        kill_menu = Gtk.Menu()
        for sig, label in [(15, T("TERM (默认)")), (9, T("KILL (强杀)")), (1, "HUP")]:
            item = Gtk.MenuItem(label=f"  kill -{sig}  ({label})")
            item.connect("activate", lambda *_, s=sig: self._do_kill(pid, s))
            kill_menu.append(item)
        kill_item = Gtk.MenuItem(label=T("杀进程 (kill)"))
        kill_item.set_submenu(kill_menu)
        menu.append(kill_item)

        # Renice 子菜单
        renice_menu = Gtk.Menu()
        for prio in [-20, -10, 0, 10, 19]:
            item = Gtk.MenuItem(label=T("  renice {}  (优先级)").format(prio))
            item.connect("activate", lambda *_, p=prio: self._do_renice(pid, p))
            renice_menu.append(item)
        renice_item = Gtk.MenuItem(label=T("调整优先级 (renice)"))
        renice_item.set_submenu(renice_menu)
        menu.append(renice_item)

        menu.show_all()
        menu.popup(None, None, None, None, event.button, event.time)

    def _show_details(self, pid):
        """显示进程详情对话框"""
        p = read_process(pid)
        if p is None:
            self._show_error(T("PID {} 不存在或无权限").format(pid))
            return

        dialog = Gtk.Dialog(title=T("进程详情 - PID {}").format(p.pid), parent=None, flags=0)
        dialog.set_default_size(600, 400)
        dialog.add_button(T("关闭"), Gtk.ResponseType.CLOSE)

        text = Gtk.TextView()
        text.set_editable(False)
        text.set_monospace(True)
        text.get_style_context().add_class("dim-text")
        buffer = text.get_buffer()
        buffer.set_text(
            T("PID:      {}\nName:     {}\nPPID:     {}\nUser:     {}\n"
              "State:    {}\nThreads:  {}\n"
              "RSS:      {} KB ({:.1f} MB)\n"
              "PSS:      {} KB ({:.1f} MB) ← 精确共享内存\n"
              "CPU:      {:.1f}%\nCmdline:  {}\n").format(
                p.pid, p.name, p.ppid, p.user, p.state, p.threads,
                p.rss_kb, p.rss_kb / 1024,
                p.pss_kb, p.pss_kb / 1024,
                p.cpu_pct, p.cmdline)
        )
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(text)
        content = dialog.get_content_area()
        content.pack_start(scrolled, True, True, 0)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def _do_kill(self, pid, sig):
        rc, err = kill_process(pid, sig)
        sig_name = {15: "TERM", 9: "KILL", 1: "HUP"}.get(sig, str(sig))
        if rc == 0:
            self._show_info(T("✅ 已发 kill -{} 给 PID {}").format(sig_name, pid))
            self._refresh()
        else:
            self._show_error(T("❌ kill 失败: {}").format(err))

    def _do_renice(self, pid, prio):
        rc, err = renice_process(pid, prio)
        if rc == 0:
            self._show_info(T("✅ PID {} 优先级已设为 {}").format(pid, prio))
        else:
            self._show_error(T("❌ renice 失败: {}").format(err))

    def _show_info(self, msg):
        dialog = Gtk.MessageDialog(parent=None, flags=0, type=Gtk.MessageType.INFO,
                                    buttons=Gtk.ButtonsType.OK, message_format=msg)
        dialog.run()
        dialog.destroy()

    def _show_error(self, msg):
        dialog = Gtk.MessageDialog(parent=None, flags=0, type=Gtk.MessageType.ERROR,
                                    buttons=Gtk.ButtonsType.OK, message_format=msg)
        dialog.run()
        dialog.destroy()
