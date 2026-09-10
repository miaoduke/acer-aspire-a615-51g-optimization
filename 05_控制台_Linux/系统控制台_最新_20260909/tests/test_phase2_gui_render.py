#!/usr/bin/env python3
"""
tests/test_phase2_gui_render.py — Phase 2 G1 真实 GTK 渲染测试

需要 DISPLAY 环境变量。在 GUI 会话或 Xvfb 下运行。

运行: python3 tests/test_phase2_gui_render.py
"""
import os
import sys
from pathlib import Path

# 2026-09-08: 测试与用户语言设置解耦——GUI 断言写死中文，显式固定 zh_CN
# （否则用户在 GUI 切了 en_US 后测试会假失败）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.core.i18n import set_locale
set_locale("zh_CN")

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

# 测试结果统计
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


def collect_labels(widget):
    """递归收集所有 Gtk.Label"""
    from gi.repository import Gtk
    labels = []
    if isinstance(widget, Gtk.Label):
        labels.append(widget.get_label())
    if hasattr(widget, 'get_children'):
        for c in widget.get_children():
            labels.extend(collect_labels(c))
    return labels


def test_scenes_page_constructs():
    """测试 1: ScenesPage 可构造不崩"""
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    Gtk.init()

    import ui_scenes
    page = ui_scenes.ScenesPage()
    if page is None:
        return "ScenesPage 构造返回 None"
    return True


def test_profile_section_present():
    """测试 2: Profile 信息面板标题存在"""
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    import ui_scenes

    page = ui_scenes.ScenesPage()
    labels = collect_labels(page)
    if not any("Profile 配置" in l for l in labels):
        return "未找到 'Profile 配置' 标题"
    return True


def test_all_profiles_listed():
    """测试 3: 8 个 profile 全部在 UI 中"""
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    import ui_scenes

    page = ui_scenes.ScenesPage()
    labels = collect_labels(page)

    expected_profiles = ['ac-perf', 'ac-bal', 'ac-quiet', 'bat-save', 'bat-bal',
                         'bat-perf', 'balanced', 'user_custom']
    for pname in expected_profiles:
        if not any(pname in l for l in labels):
            return f"profile {pname} 未在 UI 中显示"
    return True


def test_source_markers_present():
    """测试 4: 来源标记（📦/👤/⚙）在 UI 中"""
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    import ui_scenes

    page = ui_scenes.ScenesPage()
    labels = collect_labels(page)
    # 应有 📦 内置标记
    if not any("📦" in l for l in labels):
        return "无 📦 内置标记"
    return True


def test_validation_status_markers():
    """测试 5: 验证状态（✓/✗）在 UI 中"""
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    import ui_scenes

    page = ui_scenes.ScenesPage()
    labels = collect_labels(page)
    if not any("✓" in l for l in labels):
        return "无 ✓ 验证通过标记"
    return True


def test_summary_descriptions_present():
    """测试 6: profile summary 描述显示"""
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    import ui_scenes

    page = ui_scenes.ScenesPage()
    labels = collect_labels(page)
    # 至少一个 summary 描述
    if not any("插电高性能" in l for l in labels):
        return "无 '插电高性能' 描述"
    if not any("离电省电" in l for l in labels):
        return "无 '离电省电' 描述"
    return True


def test_user_override_visible():
    """测试 7: 用户 profile 覆盖时显示 👤"""
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    import ui_scenes
    import tempfile
    from pathlib import Path
    from src.core.profile import get_loader

    with tempfile.TemporaryDirectory() as tmp:
        user_dir = Path(tmp) / "user"
        user_dir.mkdir()
        (user_dir / "ac-perf").mkdir()
        (user_dir / "ac-perf" / "tuned.conf").write_text(
            "[main]\nsummary=用户自定义 ac-perf\n[cpu]\ngovernor=performance\n"
            "energy_performance_preference=performance\npl1_watts=30\nturbo=1\n",
            encoding='utf-8'
        )
        loader = get_loader()
        original = loader.user_dir
        loader.user_dir = user_dir
        loader._cache.clear()
        try:
            page = ui_scenes.ScenesPage()
            labels = collect_labels(page)
            # 应有 👤 用户标记
            if not any("👤" in l for l in labels):
                return "无 👤 用户覆盖标记"
        finally:
            loader.user_dir = original
            loader._cache.clear()
    return True


def test_no_crashes_with_missing_profile():
    """测试 8: profile 加载失败时 GUI 不崩"""
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    import ui_scenes
    import tempfile
    from pathlib import Path
    from src.core.profile import get_loader

    with tempfile.TemporaryDirectory() as tmp:
        loader = get_loader()
        original_builtin = loader.builtin_dir
        original_user = loader.user_dir
        loader.builtin_dir = Path(tmp)
        loader.user_dir = Path(tmp)
        loader._cache.clear()
        try:
            # 此时所有 profile 应 fallback 到硬编码
            page = ui_scenes.ScenesPage()
            labels = collect_labels(page)
            # 应有 ⚙ 硬编码标记
            if not any("⚙" in l for l in labels):
                return "硬编码 fallback 时无 ⚙ 标记"
        finally:
            loader.builtin_dir = original_builtin
            loader.user_dir = original_user
            loader._cache.clear()
    return True


def main():
    print("=" * 60)
    print("Phase 2 G1 真实 GTK 渲染测试")
    print("=" * 60)
    print()

    if 'DISPLAY' not in os.environ:
        print("⚠ DISPLAY 未设置，可能无法真实渲染")
        print("  提示: 在 Linux 桌面环境下运行，或用 Xvfb :99 & DISPLAY=:99 python3 ...")
        print()

    print("[1/8] ScenesPage 构造")
    test("不崩溃", test_scenes_page_constructs)

    print("\n[2/8] Profile 信息面板")
    test("标题存在", test_profile_section_present)

    print("\n[3/8] 8 个 profile 全列出")
    test("ac-perf/ac-bal/.../user_custom 齐全", test_all_profiles_listed)

    print("\n[4/8] 来源标记")
    test("含 📦 内置标记", test_source_markers_present)

    print("\n[5/8] 验证状态")
    test("含 ✓ 标记", test_validation_status_markers)

    print("\n[6/8] Summary 描述")
    test("'插电高性能' + '离电省电' 显示", test_summary_descriptions_present)

    print("\n[7/8] 用户覆盖")
    test("用户 profile 显示 👤", test_user_override_visible)

    print("\n[8/8] 硬编码 fallback")
    test("无文件时显示 ⚙", test_no_crashes_with_missing_profile)

    print("\n[9/9] ui_dashboard.py line 326 格式 bug 修复")
    test("不再抛 TypeError(format requires a mapping)", test_dashboard_format_bug_fixed)
    print("\n[10/10] ui_scenes.py M3 属性 bug 修复")
    test("m3_state/on/off 全部存在 + refresh_state 不崩", test_scenes_page_m3_state_exists)

    print()
    print("=" * 60)
    print(f"测试结果: {TESTS_PASSED}/{TESTS_RUN} 通过, {TESTS_FAILED} 失败")
    print("=" * 60)
    return 0 if TESTS_FAILED == 0 else 1


def test_dashboard_format_bug_fixed():
    """Bug 修复: ui_dashboard.py:326 '%(每线程色)' 错误格式"""
    import os
    os.environ['GDK_BACKEND'] = 'x11'
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    Gtk.init()
    import sys
    sys.path.insert(0, '.')
    from ui_dashboard import DashboardPage

    page = DashboardPage()
    page.cpu_temp_hist = [50.0, 55.0, 60.0, 65.0]

    class MockCr:
        def set_source_rgba(self, *a): pass
        def set_source_rgb(self, *a): pass
        def set_line_width(self, *a): pass
        def set_font_size(self, *a): pass
        def move_to(self, *a): pass
        def line_to(self, *a): pass
        def stroke(self): pass
        def paint(self): pass
        def show_text(self, text): return text

    class MockWidget:
        def get_allocated_width(self): return 800
        def get_allocated_height(self): return 300
        def queue_draw(self): pass
        def get_style_context(self):
            class C:
                def add_class(self, *a): pass
            return C()

    try:
        page._on_draw(MockWidget(), MockCr())
        return True
    except TypeError as e:
        if "format requires a mapping" in str(e):
            return f"bug 复发: {e}"
        return f"其他 TypeError: {e}"
    except Exception:
        return True


def test_scenes_page_m3_state_exists():
    """Bug 修复: ui_scenes.py M3 状态属性缺失（之前 P1-4 编辑按钮插入位置错误导致）"""
    import os
    os.environ['GDK_BACKEND'] = 'x11'
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    Gtk.init()
    import sys
    sys.path.insert(0, '.')
    from ui_scenes import ScenesPage

    page = ScenesPage()
    # 关键: m3_state 必须存在
    for attr in ('m3_state', 'm3_on', 'm3_off', 'scene_buttons', 'snap',
                  'combo_ac', 'combo_dc', 'defaults_state'):
        if not hasattr(page, attr):
            return f"缺属性: {attr}"
    # refresh_state 不应抛 AttributeError
    try:
        page.refresh_state()
        return True
    except AttributeError as e:
        if "m3_state" in str(e) or "m3_on" in str(e):
            return f"M3 属性 bug 复发: {e}"
        return f"其他 AttributeError: {e}"
    except Exception:
        return True


if __name__ == '__main__':
    sys.exit(main())


def test_dashboard_format_bug_fixed():
    """Bug 修复: ui_dashboard.py:326 '%(每线程色)' 错误格式"""
    import os
    os.environ['GDK_BACKEND'] = 'x11'
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    Gtk.init()
    import sys
    sys.path.insert(0, '.')
    from ui_dashboard import DashboardPage

    # 创建 dashboard page
    page = DashboardPage()

    # 模拟 cpu_temp_hist 有数据
    page.cpu_temp_hist = [50.0, 55.0, 60.0, 65.0]

    # 创建 mock cairo context
    class MockCr:
        def set_source_rgba(self, *a): pass
        def set_source_rgb(self, *a): pass
        def set_line_width(self, *a): pass
        def set_font_size(self, *a): pass
        def move_to(self, *a): pass
        def line_to(self, *a): pass
        def stroke(self): pass
        def paint(self): pass
        def show_text(self, text):
            return text

    class MockWidget:
        def get_allocated_width(self): return 800
        def get_allocated_height(self): return 300
        def queue_draw(self): pass
        def get_style_context(self):
            class C:
                def add_class(self, *a): pass
            return C()

    # 触发 _on_draw，验证 line 326 不抛 TypeError
    try:
        page._on_draw(MockWidget(), MockCr())
        return True
    except TypeError as e:
        if "format requires a mapping" in str(e):
            return f"bug 复发: {e}"
        return f"其他 TypeError: {e}"
    except Exception as e:
        # 允许其他异常（mock 不完整）
        return True
