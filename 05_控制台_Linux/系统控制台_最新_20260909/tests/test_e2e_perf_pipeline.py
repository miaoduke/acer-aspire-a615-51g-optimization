#!/usr/bin/env python3
"""
tests/test_e2e_perf_pipeline.py — P0-A 回归测试：perf 采样落盘端到端断言

背景（2026-09-07 全面审计发现）：console.py 的 log_sample 曾因 PerfSample
构造传无效 kwarg（_throttle_data）抛 TypeError，被 tick 处的静默 except 吞掉，
导致 09-02 14:00 起 5 天零采样而无人察觉。本套件堵住该盲区：

  W1: log_sample 可执行（构造 PerfSample 不抛错）→ 数据真实落盘
  W2: tick 集成路径（_tick → _perf_log_fn(d)）异常不再被静默吞——
      注入必抛异常的采集函数，断言异常被捕获且打印告警（不 crash）
  W3: PerfSample 字段契约——console 传的每个 kwarg 都是 dataclass 真实字段
      （用 dataclasses.fields 静态对账，抓编码期 kwarg 拼写错误）
  W4: 落盘文件当日行数增长（record → flush 后 TSV 行数 +1）

需要 DISPLAY。运行: python3 tests/test_e2e_perf_pipeline.py
"""
import os
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

TESTS_RUN = 0
TESTS_PASSED = 0
TESTS_FAILED = 0


def test(name, func):
    global TESTS_RUN, TESTS_PASSED, TESTS_FAILED
    TESTS_RUN += 1
    try:
        result = func()
        if result is True or result is None:
            TESTS_PASSED += 1
            print(f"  ✅ {name}")
            return True
        else:
            TESTS_FAILED += 1
            print(f"  ❌ {name}: {result}")
            return False
    except Exception as e:
        TESTS_FAILED += 1
        print(f"  ❌ {name}: {e}")
        import traceback
        traceback.print_exc()
        return False


def _make_app():
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    Gtk.init()
    from console import ConsoleApp
    return ConsoleApp()


def test_perf_sample_contract():
    """W3: PerfSample dataclass 字段契约——防 kwarg 拼写错（P0-A 根因）"""
    import dataclasses
    from src.core.perf_logger import PerfSample, BatterySample
    valid_perf = {f.name for f in dataclasses.fields(PerfSample)}
    valid_batt = {f.name for f in dataclasses.fields(BatterySample)}

    # 从 console.py 源码提取 PerfSample(...)/BatterySample(...) 调用的 kwarg 名
    src = (PROJECT_DIR / "console.py").read_text(encoding="utf-8")

    import re
    issues = []
    for cls_name, valid in (("PerfSample", valid_perf), ("BatterySample", valid_batt)):
        for m in re.finditer(cls_name + r"\(", src):
            # 找到匹配的右括号（简单括号配平）
            start = m.end()
            depth = 1
            i = start
            while i < len(src) and depth > 0:
                if src[i] == "(":
                    depth += 1
                elif src[i] == ")":
                    depth -= 1
                i += 1
            call = src[start:i - 1]
            for kw in re.findall(r"(?:^|[,(]\s*)(\w+)=", call):
                if kw not in valid:
                    issues.append(f"{cls_name} 传入无效字段: {kw}")
    if issues:
        return "; ".join(issues[:5])
    return True


def test_log_sample_writes_disk():
    """W1+W4: log_sample 执行成功且数据真实落盘（TSV 行数增长）"""
    app = _make_app()
    if not getattr(app, "_perf_log_fn", None):
        return "console 未初始化 _perf_log_fn（perf 管道未建立）"

    from src.core.perf_logger import get_perf_manager

    # 用真实 collector 采样 + 强制落盘
    d = app.collector.sample()
    app._last_perf_log = 0  # 绕过 30s 节流（测试环境）
    before = _today_perf_lines()
    try:
        app._perf_log_fn(d)
    except Exception as e:
        return f"log_sample 抛异常（P0-A 复发！）: {e}"
    get_perf_manager().flush()
    time.sleep(0.2)
    after = _today_perf_lines()
    if after <= before:
        return f"落盘未增长（前 {before} 后 {after}）——采样被静默丢弃"
    return True


def _today_perf_lines():
    """当日 perf TSV 行数"""
    from src.core.perf_logger import get_perf_manager
    m = get_perf_manager()
    f = m._get_date_file("perf")  # 日期翻转安全（不依赖 _ensure_files 已跑）
    if not f.exists():
        return 0
    return sum(1 for _ in f.open(encoding="utf-8"))


def test_tick_swallows_but_reports():
    """W2: tick 对 perf 异常不再静默——注入必抛异常的 fn，验证 console._tick 捕获并告警"""
    app = _make_app()
    orig = getattr(app, "_perf_log_fn", None)
    if orig is None:
        return "console 未初始化 _perf_log_fn"

    import io
    import contextlib
    buf = io.StringIO()

    def boom(_d):
        raise RuntimeError("injected-failure")

    app._perf_log_fn = boom
    app._last_perf_err = 0  # 绕过告警限频，确保告警打印
    try:
        # 直接调用真实 _tick（collector 采样 + 页面刷新 + perf 记录）
        with contextlib.redirect_stdout(buf):
            app._tick()
        out = buf.getvalue()
        if "injected-failure" in out:
            return True  # 异常被捕获且告警打印（不再静默 pass）
        # 未打印也不 crash：可能限频条件未满足——重试一次
        with contextlib.redirect_stdout(buf):
            app._tick()
        out = buf.getvalue()
        if "injected-failure" in out:
            return True
        return "异常被静默吞掉（无告警输出）——except-pass 复发风险"
    finally:
        app._perf_log_fn = orig
        app._last_perf_err = 0


def main():
    global TESTS_RUN, TESTS_PASSED, TESTS_FAILED
    print("=" * 60)
    print("E2E perf 采样管道回归（P0-A 盲区补丁）")
    print("=" * 60)
    test("W3 PerfSample 字段契约（静态对账）", test_perf_sample_contract)
    test("W1+W4 log_sample 执行且落盘", test_log_sample_writes_disk)
    test("W2 tick 异常保护与注入", test_tick_swallows_but_reports)
    print()
    print(f"测试结果: {TESTS_PASSED}/{TESTS_RUN} 通过, {TESTS_FAILED} 失败")
    return 0 if TESTS_FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
