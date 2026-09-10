#!/usr/bin/env python3
"""tests/test_phase2_plugin.py — Phase 2 G2 plugin 单元测试"""
import os
import sys
import tempfile
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


def test_registry_import():
    from src.core.plugin import get_registry
    return True


def test_discover_builtin():
    from src.core.plugin import get_registry
    reg = get_registry()
    names = reg.discover()
    if len(names) < 2:
        return f"内置 plugin 数量不足: {names}"
    return True


def test_load_thermal_ctl():
    from src.core.plugin import get_registry
    reg = get_registry()
    p = reg.load("thermal_ctl")
    if p is None:
        return "thermal_ctl 加载失败"
    if p.name != "thermal_ctl":
        return f"name 不符: {p.name}"
    return True


def test_load_example():
    from src.core.plugin import get_registry
    reg = get_registry()
    p = reg.load("example")
    if p is None:
        return "example 加载失败"
    return True


def test_load_nonexistent():
    from src.core.plugin import get_registry
    reg = get_registry()
    p = reg.load("nonexistent_xyz")
    if p is not None:
        return f"不存在的 plugin 应返回 None，实际: {p}"
    return True


def test_user_overrides_builtin():
    from src.core.plugin import PluginRegistry, get_registry
    with tempfile.TemporaryDirectory() as tmp:
        builtin = Path(tmp) / "builtin"
        user = Path(tmp) / "user"
        builtin.mkdir()
        user.mkdir()
        (builtin / "test_plugin.py").write_text(
            "import sys; sys.path.insert(0, '..'); from src.core.plugin import Plugin\n"
            "class TestPlugin(Plugin):\n"
            "    name='test_plugin'; version='1.0'\n"
            "    def _init(self, ctx): pass\n"
            "    def _apply(self, ctx): pass\n",
            encoding='utf-8'
        )
        (user / "test_plugin.py").write_text(
            "import sys; sys.path.insert(0, '..'); from src.core.plugin import Plugin\n"
            "class TestPlugin(Plugin):\n"
            "    name='test_plugin'; version='9.9'\n"  # 不同 version
            "    def _init(self, ctx): pass\n"
            "    def _apply(self, ctx): pass\n",
            encoding='utf-8'
        )
        reg = PluginRegistry(builtin, user)
        p = reg.load("test_plugin")
        if p.version != "9.9":
            return f"用户版本应优先，实际: {p.version}"
    return True


def test_apply_with_dry_run():
    from src.core.plugin import get_registry, PluginContext
    reg = get_registry()
    ctx = PluginContext(dry_run=True)
    # 不真跑系统命令，dry-run
    ok = reg.apply_plugin("example", ctx)
    if not ok:
        return "example apply 失败"
    if not ctx.results.get('example_applied'):
        return "example 未设置 result"
    return True


def test_error_isolation():
    from src.core.plugin import PluginRegistry, PluginContext
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "broken.py").write_text(
            "raise ImportError('intentional')\n",
            encoding='utf-8'
        )
        reg = PluginRegistry(d, d)
        p = reg.load("broken")
        if p is not None:
            return f"broken plugin 应加载失败（返回 None），实际: {p}"
    return True


def test_cli_list():
    import subprocess
    r = subprocess.run(
        ["python3", str(PROJECT_DIR / "src/core/plugin.py"), "--list"],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        return f"CLI 失败: {r.stderr}"
    if "thermal_ctl" not in r.stdout:
        return f"CLI 列表缺 thermal_ctl: {r.stdout[:200]}"
    return True


def main():
    print("=" * 60)
    print("Phase 2 G2 (plugin 抽象) 单元测试")
    print("=" * 60)
    print()
    test("plugin registry 导入", test_registry_import)
    test("发现内置 plugin (≥2)", test_discover_builtin)
    test("加载 thermal_ctl", test_load_thermal_ctl)
    test("加载 example", test_load_example)
    test("不存在的 plugin 返回 None", test_load_nonexistent)
    test("用户覆盖内置", test_user_overrides_builtin)
    test("dry-run apply", test_apply_with_dry_run)
    test("错误隔离（broken 不影响）", test_error_isolation)
    test("CLI --list", test_cli_list)
    print()
    print("=" * 60)
    print(f"测试结果: {TESTS_PASSED}/{TESTS_RUN} 通过, {TESTS_FAILED} 失败")
    print("=" * 60)
    return 0 if TESTS_FAILED == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
