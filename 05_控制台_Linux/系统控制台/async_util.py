#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""async_util.py — 后台线程执行控制操作，完成回主线程（避免阻塞 GUI）"""
import threading

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import GLib


def run_async(fn, on_done):
    """fn 在后台线程执行；on_done(result) 在主线程回调"""
    def worker():
        try:
            result = fn()
        except Exception as e:
            result = (-1, "", str(e))
        GLib.idle_add(on_done, result)

    threading.Thread(target=worker, daemon=True).start()