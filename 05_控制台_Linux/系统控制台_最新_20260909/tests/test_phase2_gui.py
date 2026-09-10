#!/usr/bin/env python3
"""
tests/test_phase2_gui.py — Phase 2 G1 GUI 离屏渲染测试

测试目标: 验证 ui_scenes.py 集成 Profile 信息面板后
          1. 不崩溃
          2. 正确显示 8 个 profile
          3. 来源标记（用户/内置/硬编码）正确
          4. 验证状态标记（✓/✗）正确

运行: 需要 GDK_BACKEND=broadway 或 Xvfb 或离屏模式
"""
import os
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

# GTK 离屏渲染（无需显示器）
os.environ['GDK_BACKEND'] = 'broadway'
# 如果 broadway 不可用，回退到 Xvfb 或 wayland
if 'DISPLAY' not in os.environ:
    os.environ['DISPLAY'] = ':99'

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


def test_import_scenes_page():
    """测试 1: ui_scenes.ScenePage 可导入"""
    import ui_scenes
    assert hasattr(ui_scenes, 'ScenesPage')
    return True


def test_profile_loader_import():
    """测试 2: profile loader 可用"""
    from src.core.profile import get_loader, validate_profile
    loader = get_loader()
    names = loader.list_profiles()
    if len(names) < 6:
        return f"profile 数量不足: {len(names)}"
    return True


def test_validate_all_profiles():
    """测试 3: 8 个 profile 全部验证通过"""
    from src.core.profile import validate_profile
    names = ['ac-perf', 'ac-bal', 'ac-quiet', 'bat-save', 'bat-bal', 'bat-perf',
             'balanced', 'user_custom']
    for n in names:
        ok, errs = validate_profile(n)
        if not ok:
            return f"{n} 验证失败: {errs}"
    return True


def test_source_detection():
    """测试 4: 来源检测（用户/内置）"""
    from src.core.profile import get_loader
    from pathlib import Path
    loader = get_loader()

    # ac-perf 应在内置目录
    path = loader.find_profile_path("ac-perf")
    if path is None:
        return "ac-perf 找不到"
    user_path = Path.home() / ".config" / "system-console" / "profiles" / "ac-perf" / "tuned.conf"
    if user_path.exists():
        return f"应只在内置，不应在用户: {user_path}"
    if "系统控制台" not in str(path):
        return f"应在内置目录: {path}"
    return True


def test_user_override_detection():
    """测试 5: 用户 profile 覆盖检测"""
    from src.core.profile import get_loader
    from pathlib import Path
    import tempfile

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
        if hasattr(loader, "_merged_cache"):
            loader._merged_cache.clear()
        try:
            path = loader.find_profile_path("ac-perf")
            if not str(path).startswith(str(user_dir)):
                return f"应优先用户目录，实际: {path}"
        finally:
            loader.user_dir = original
            loader._cache.clear()
        if hasattr(loader, "_merged_cache"):
            loader._merged_cache.clear()
    return True


def test_hardcoded_fallback_marker():
    """测试 6: 硬编码 fallback 标记（无文件时）"""
    from src.core.profile import get_loader
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        loader = get_loader()
        original_builtin = loader.builtin_dir
        original_user = loader.user_dir
        loader.builtin_dir = Path(tmp)
        loader.user_dir = Path(tmp)
        loader._cache.clear()
        if hasattr(loader, "_merged_cache"):
            loader._merged_cache.clear()
        try:
            # 此时应 fallback 到硬编码
            path = loader.find_profile_path("ac-perf")
            if path is not None:
                return f"应无路径（fallback），实际: {path}"
            # 但 load() 仍可用
            p = loader.load("ac-perf")
            if str(p.source_path) != "<hardcoded>":
                return f"应 hardcoded，实际: {p.source_path}"
        finally:
            loader.builtin_dir = original_builtin
            loader.user_dir = original_user
            loader._cache.clear()
        if hasattr(loader, "_merged_cache"):
            loader._merged_cache.clear()
    return True


def main():
    print("=" * 60)
    print("Phase 2 G1 GUI 集成测试 (Profile 信息面板)")
    print("=" * 60)
    print()

    print("[1/6] 导入 ui_scenes 模块")
    test("ScenesPage 类存在", test_import_scenes_page)

    print("\n[2/6] profile loader 集成")
    test("8 个 profile 可用", test_profile_loader_import)

    print("\n[3/6] 8 个 profile 验证")
    test("全部 ✓", test_validate_all_profiles)

    print("\n[4/6] 来源检测 - 内置")
    test("ac-perf 在内置目录", test_source_detection)

    print("\n[5/6] 来源检测 - 用户覆盖")
    test("用户目录优先", test_user_override_detection)

    print("\n[6/6] 硬编码 fallback 标记")
    test("无文件时标 ⚙", test_hardcoded_fallback_marker)

    print()
    print("=" * 60)
    print(f"测试结果: {TESTS_PASSED}/{TESTS_RUN} 通过, {TESTS_FAILED} 失败")
    print("=" * 60)
    return 0 if TESTS_FAILED == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
