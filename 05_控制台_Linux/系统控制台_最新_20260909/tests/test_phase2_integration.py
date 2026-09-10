#!/usr/bin/env python3
"""
tests/test_phase2_integration.py — Phase 2 G1 集成测试

测试目标: 验证 controller.py 集成 profile 后行为完全一致

运行: python3 tests/test_phase2_integration.py
"""
import os
import sys
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


def test_load_from_profile():
    """测试 1: controller 从 profile 加载（_LOADED_FROM_PROFILE=True）"""
    import controller
    if not controller._LOADED_FROM_PROFILE:
        return f"_LOADED_FROM_PROFILE 应为 True，实际 {controller._LOADED_FROM_PROFILE}"
    return True


def test_scenes_count():
    """测试 2: SCENES 数量 = 6"""
    import controller
    if len(controller.SCENES) != 6:
        return f"SCENES 数量应为 6，实际 {len(controller.SCENES)}"
    return True


def test_scene_params_count():
    """测试 3: SCENE_PARAMS 数量 = 6"""
    import controller
    if len(controller.SCENE_PARAMS) != 6:
        return f"SCENE_PARAMS 数量应为 6，实际 {len(controller.SCENE_PARAMS)}"
    return True


def test_scenes_keys():
    """测试 4: SCENES 含所有 6 个原场景"""
    import controller
    required = {'ac-perf', 'ac-bal', 'ac-quiet', 'bat-save', 'bat-bal', 'bat-perf'}
    actual = set(controller.SCENES.keys())
    if actual != required:
        return f"SCENES keys 不匹配，缺 {required - actual}, 多 {actual - required}"
    return True


def test_scene_params_match_hardcoded():
    """测试 5: SCENE_PARAMS 内容与原硬编码完全一致"""
    import controller
    expected = {
        "ac-perf":  ("performance", "performance",         25, True),
        "ac-bal":   ("powersave",    "balance_performance", 15, True),
        "ac-quiet": ("powersave",    "balance_power",       10, True),
        "bat-save": ("powersave",    "power",               10, False),
        "bat-bal":  ("powersave",    "balance_power",       12, True),
        "bat-perf": ("performance",  "performance",         15, True),
    }
    for name, exp_params in expected.items():
        if controller.SCENE_PARAMS.get(name) != exp_params:
            return f"{name} 参数不符: 期望 {exp_params}, 实际 {controller.SCENE_PARAMS.get(name)}"
    return True


def test_get_active_scene_ac_perf():
    """测试 6: get_active_scene 匹配 ac-perf"""
    import controller
    params = {"governor": "performance", "epp": "performance", "pl1_w": 25, "turbo": True}
    result = controller.get_active_scene(params)
    if result != "ac-perf":
        return f"应为 ac-perf，实际 {result}"
    return True


def test_get_active_scene_bat_save():
    """测试 7: get_active_scene 匹配 bat-save（turbo 关闭）"""
    import controller
    params = {"governor": "powersave", "epp": "power", "pl1_w": 10, "turbo": False}
    result = controller.get_active_scene(params)
    if result != "bat-save":
        return f"应为 bat-save，实际 {result}"
    return True


def test_get_active_scene_no_match():
    """测试 8: 不匹配参数返回 None"""
    import controller
    params = {"governor": "schedutil", "epp": "balance_performance", "pl1_w": 25, "turbo": True}
    result = controller.get_active_scene(params)
    if result is not None:
        return f"不匹配应返回 None，实际 {result}"
    return True


def test_ac_dc_scenes():
    """测试 9: AC_SCENES / DC_SCENES 保留"""
    import controller
    if controller.AC_SCENES != ("ac-perf", "ac-bal", "ac-quiet"):
        return f"AC_SCENES 不符: {controller.AC_SCENES}"
    if controller.DC_SCENES != ("bat-save", "bat-bal", "bat-perf"):
        return f"DC_SCENES 不符: {controller.DC_SCENES}"
    return True


def test_fallback_when_profile_missing():
    """测试 10: profile 不可用时 fallback 到硬编码"""
    # 临时屏蔽 profile 目录
    import controller
    from unittest.mock import patch

    # 模拟 profile 加载失败
    with patch('src.core.profile.get_loader', side_effect=ImportError("simulated")):
        # 重新执行加载逻辑
        profile_scenes = controller._load_scenes_from_profiles()
        if profile_scenes is not None:
            return f"应返回 None（fallback），实际 {profile_scenes}"
    return True


def test_user_profile_override():
    """测试 11: 用户 profile 可覆盖内置"""
    import controller
    import tempfile
    from pathlib import Path
    from src.core.profile import ProfileLoader, get_loader

    with tempfile.TemporaryDirectory() as tmp:
        user_dir = Path(tmp) / "user"
        user_dir.mkdir()
        # 用户自定义 ac-perf
        (user_dir / "ac-perf").mkdir()
        (user_dir / "ac-perf" / "tuned.conf").write_text(
            "[main]\nsummary=用户自定义 ac-perf\n"
            "[cpu]\ngovernor=performance\nenergy_performance_preference=performance\npl1_watts=30\nturbo=1\n",
            encoding='utf-8'
        )

        # 用真实 loader，临时改 user_dir
        loader = get_loader()
        original_user_dir = loader.user_dir
        loader.user_dir = user_dir
        loader._cache.clear()
        if hasattr(loader, "_merged_cache"):
            loader._merged_cache.clear()
        try:
            p = loader.load("ac-perf")
            if p.summary != "用户自定义 ac-perf":
                return f"用户未覆盖: {p.summary}"
            if p.get("cpu", "pl1_watts") != "30":
                return f"用户未覆盖 pl1: {p.get('cpu', 'pl1_watts')}"
        finally:
            loader.user_dir = original_user_dir
            loader._cache.clear()
        if hasattr(loader, "_merged_cache"):
            loader._merged_cache.clear()
    return True


def main():
    print("=" * 60)
    print("Phase 2 G1 集成测试 (controller.py 集成 profile)")
    print("=" * 60)
    print()

    print("[1/11] 从 profile 加载标志")
    test("_LOADED_FROM_PROFILE = True", test_load_from_profile)

    print("\n[2/11] SCENES 数量")
    test("6 个场景", test_scenes_count)

    print("\n[3/11] SCENE_PARAMS 数量")
    test("6 个场景", test_scene_params_count)

    print("\n[4/11] SCENES keys")
    test("6 场景齐全", test_scenes_keys)

    print("\n[5/11] SCENE_PARAMS 行为一致性")
    test("与原硬编码完全一致", test_scene_params_match_hardcoded)

    print("\n[6/11] get_active_scene 匹配 ac-perf")
    test("performance 场景", test_get_active_scene_ac_perf)

    print("\n[7/11] get_active_scene 匹配 bat-save")
    test("turbo=0 场景", test_get_active_scene_bat_save)

    print("\n[8/11] get_active_scene 不匹配")
    test("返回 None", test_get_active_scene_no_match)

    print("\n[9/11] AC/DC 场景列表")
    test("保留", test_ac_dc_scenes)

    print("\n[10/11] Profile 不可用时 fallback")
    test("ImportError 时回退", test_fallback_when_profile_missing)

    print("\n[11/11] 用户 profile 覆盖")
    test("用户目录优先", test_user_profile_override)

    print()
    print("=" * 60)
    print(f"测试结果: {TESTS_PASSED}/{TESTS_RUN} 通过, {TESTS_FAILED} 失败")
    print("=" * 60)
    return 0 if TESTS_FAILED == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
