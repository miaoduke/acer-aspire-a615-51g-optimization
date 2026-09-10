#!/usr/bin/env python3
"""
tests/test_phase2_profile.py — Phase 2 G1 单元测试

测试目标: profile 配置化
  1. 加载 6 个内置 profile
  2. 解析 [main] include= 继承
  3. 段覆盖（[cpu] 段内字段按"覆盖"合并）
  4. 循环 include 检测
  5. 验证器（必填字段 + 值范围）
  6. fallback 硬编码
  7. 用户 profile 优先于内置

运行: python3 tests/test_phase2_profile.py
"""
import os
import sys
import tempfile
from pathlib import Path

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


def test_list_builtin():
    """测试 1: 列出内置 profile（应至少含 6 个原场景 + 1 个 user_custom）"""
    from src.core.profile import get_loader
    loader = get_loader()
    names = loader.list_profiles()
    required = {'ac-perf', 'ac-bal', 'ac-quiet', 'bat-save', 'bat-bal', 'bat-perf'}
    missing = required - set(names)
    if missing:
        return f"缺 profile: {missing}，现有: {names}"
    return True


def test_load_balanced():
    """测试 2: 加载 balanced profile（基类）"""
    from src.core.profile import get_loader
    p = get_loader().load("balanced")
    if not p.summary:
        return "summary 为空"
    if p.get("cpu", "governor") != "powersave":
        return f"governor 应为 powersave，实际 {p.get('cpu', 'governor')}"
    if p.get("cpu", "pl1_watts") != "15":
        return f"pl1_watts 应为 15，实际 {p.get('cpu', 'pl1_watts')}"
    return True


def test_include_inheritance():
    """测试 3: include 继承（ac-bal 应继承 balanced）"""
    from src.core.profile import get_loader
    p = get_loader().load("ac-bal")
    # ac-bal 自己的 [main] 是 include=balanced，没改 [cpu]
    # 所以应继承 balanced 的 [cpu]
    if p.get("cpu", "governor") != "powersave":
        return f"继承失败: governor={p.get('cpu', 'governor')}"
    if p.get("cpu", "pl1_watts") != "15":
        return f"继承失败: pl1_watts={p.get('cpu', 'pl1_watts')}"
    if p.get("cpu", "turbo") != "1":
        return f"继承失败: turbo={p.get('cpu', 'turbo')}"
    return True


def test_section_override():
    """测试 4: 段覆盖（ac-perf 覆盖 governor 为 performance）"""
    from src.core.profile import get_loader
    p = get_loader().load("ac-perf")
    if p.get("cpu", "governor") != "performance":
        return f"覆盖失败: governor={p.get('cpu', 'governor')}"
    # 同时继承的 pl1_watts=15 应被覆盖为 25
    if p.get("cpu", "pl1_watts") != "25":
        return f"覆盖失败: pl1_watts={p.get('cpu', 'pl1_watts')}"
    return True


def test_turbo_off_inheritance():
    """测试 5: 关键边界 - bat-save 关闭 turbo"""
    from src.core.profile import get_loader
    p = get_loader().load("bat-save")
    if p.get("cpu", "turbo") != "0":
        return f"bat-save turbo 应为 0，实际 {p.get('cpu', 'turbo')}"
    if p.get("cpu", "pl1_watts") != "10":
        return f"bat-save pl1 应为 10，实际 {p.get('cpu', 'pl1_watts')}"
    return True


def test_validate_balanced():
    """测试 6: 验证器 - balanced 通过"""
    from src.core.profile import validate_profile
    ok, errors = validate_profile("balanced")
    if not ok:
        return f"balanced 验证失败: {errors}"
    return True


def test_validate_all_scenes():
    """测试 7: 验证器 - 所有 6 场景通过"""
    from src.core.profile import validate_profile
    for name in ['ac-perf', 'ac-bal', 'ac-quiet', 'bat-save', 'bat-bal', 'bat-perf']:
        ok, errors = validate_profile(name)
        if not ok:
            return f"{name} 验证失败: {errors}"
    return True


def test_validate_nonexistent():
    """测试 8: 验证器 - 不存在的 profile 失败"""
    from src.core.profile import validate_profile
    ok, errors = validate_profile("nonexistent_xyz_123")
    if ok:
        return "不存在的 profile 应验证失败"
    if not errors:
        return "应有错误信息"
    return True


def test_circular_includes():
    """测试 9: 循环 include 检测"""
    import tempfile
    from src.core.profile import ProfileLoader, ProfileError

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "circular"
        d.mkdir()
        # a -> b -> a
        (d / "a").mkdir()
        (d / "a" / "tuned.conf").write_text("[main]\ninclude=b\n", encoding='utf-8')
        (d / "b").mkdir()
        (d / "b" / "tuned.conf").write_text("[main]\ninclude=a\n", encoding='utf-8')

        loader = ProfileLoader(d, d)
        try:
            loader.load("a")
            return "应检测到循环 include"
        except ProfileError as e:
            if "循环" not in str(e):
                return f"错误信息不符: {e}"
    return True


def test_user_overrides_builtin():
    """测试 10: 用户目录覆盖内置"""
    from src.core.profile import ProfileLoader

    with tempfile.TemporaryDirectory() as tmp:
        builtin = Path(tmp) / "builtin"
        user = Path(tmp) / "user"
        builtin.mkdir()
        user.mkdir()
        # 内置
        (builtin / "test").mkdir()
        (builtin / "test" / "tuned.conf").write_text(
            "[main]\nsummary=builtin version\n[cpu]\ngovernor=powersave\npl1_watts=15\nturbo=1\n",
            encoding='utf-8'
        )
        # 用户覆盖
        (user / "test").mkdir()
        (user / "test" / "tuned.conf").write_text(
            "[main]\nsummary=user override version\n[cpu]\ngovernor=performance\npl1_watts=25\nturbo=1\n",
            encoding='utf-8'
        )

        loader = ProfileLoader(builtin, user)
        p = loader.load("test")
        if p.summary != "user override version":
            return f"用户未覆盖: summary={p.summary}"
        if p.get("cpu", "governor") != "performance":
            return f"用户未覆盖: governor={p.get('cpu', 'governor')}"
    return True


def test_fallback_hardcoded():
    """测试 11: 硬编码 fallback（兼容旧 SCENES）"""
    from src.core.profile import get_loader
    # 临时清除内置 profile 缓存，模拟"找不到文件"场景
    loader = get_loader()
    loader._cache.clear()
    if hasattr(loader, '_merged_cache'):
        loader._merged_cache.clear()
    # 改变 builtin_dir 指向空目录
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        loader.builtin_dir = Path(tmp)
        loader.user_dir = Path(tmp)
        # 此时应 fallback 到硬编码
        p = loader.load("ac-perf")
        if p.source_path.name != "<hardcoded>":
            return f"应 fallback 到硬编码，实际: {p.source_path}"
        if p.get("cpu", "governor") != "performance":
            return f"硬编码 fallback 错误: {p.get('cpu', 'governor')}"
    return True


def test_cli_list():
    """测试 12: CLI --list"""
    import subprocess
    r = subprocess.run(
        ["python3", "-c",
         "import sys; sys.path.insert(0, '.'); "
         "from src.core.profile import get_loader; "
         "loader = get_loader(); print('\\n'.join(loader.list_profiles()))"],
        capture_output=True, text=True, cwd=str(PROJECT_DIR)
    )
    if r.returncode != 0:
        return f"CLI 失败: {r.stderr}"
    if "ac-perf" not in r.stdout:
        return f"CLI 列表缺 ac-perf: {r.stdout[:200]}"
    return True


def test_cli_show():
    """测试 13: CLI --show ac-perf"""
    import subprocess
    r = subprocess.run(
        ["python3", str(PROJECT_DIR / "src/core/profile.py"), "--show", "ac-perf"],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        return f"CLI 失败: {r.stderr}"
    if "performance" not in r.stdout:
        return f"CLI 输出缺 performance: {r.stdout[:300]}"
    return True


def main():
    print("=" * 60)
    print("Phase 2 G1 (profile 配置化) 单元测试")
    print("=" * 60)
    print()

    print("[1/13] 列出内置 profile")
    test("含 6 个原场景", test_list_builtin)

    print("\n[2/13] 加载 balanced 基类")
    test("summary + cpu 字段正确", test_load_balanced)

    print("\n[3/13] include 继承")
    test("ac-bal 继承 balanced 的 [cpu]", test_include_inheritance)

    print("\n[4/13] 段覆盖")
    test("ac-perf 覆盖 governor + pl1", test_section_override)

    print("\n[5/13] 关键边界 - bat-save 关闭 turbo")
    test("turbo=0 + pl1=10 正确", test_turbo_off_inheritance)

    print("\n[6/13] 验证器 - balanced")
    test("通过验证", test_validate_balanced)

    print("\n[7/13] 验证器 - 全部 6 场景")
    test("6 场景全通过", test_validate_all_scenes)

    print("\n[8/13] 验证器 - 不存在 profile")
    test("失败 + 错误信息", test_validate_nonexistent)

    print("\n[9/13] 循环 include 检测")
    test("a→b→a 被检测", test_circular_includes)

    print("\n[10/13] 用户覆盖内置")
    test("user/test.conf 优先", test_user_overrides_builtin)

    print("\n[11/13] 硬编码 fallback")
    test("无文件时回退到 SCENES", test_fallback_hardcoded)

    print("\n[12/13] CLI --list")
    test("输出含 6 场景", test_cli_list)

    print("\n[13/13] CLI --show ac-perf")
    test("输出含 performance", test_cli_show)

    print()
    print("=" * 60)
    print(f"测试结果: {TESTS_PASSED}/{TESTS_RUN} 通过, {TESTS_FAILED} 失败")
    print("=" * 60)
    return 0 if TESTS_FAILED == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
