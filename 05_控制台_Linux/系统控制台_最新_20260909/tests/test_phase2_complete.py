#!/usr/bin/env python3
"""
tests/test_phase2_complete.py — Phase 2 完整测试（G1 + G2 + G3 + G6）

运行: python3 tests/test_phase2_complete.py
"""
import os
import sys
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


# ============== G1 profile ==============
def g1():
    from src.core.profile import get_loader, validate_profile
    loader = get_loader()
    names = loader.list_profiles()
    assert len(names) >= 6
    for n in names:
        ok, _ = validate_profile(n)
        assert ok, f"{n} 验证失败"


# ============== G2 plugin ==============
def g2():
    from src.core.plugin import get_registry
    reg = get_registry()
    plugins = reg.list_plugins()
    assert len(plugins) >= 2
    assert "thermal_ctl" in plugins


# ============== G3 process ==============
def g3():
    from src.core.process_utils import list_processes, read_process
    procs = list_processes(limit=10)
    assert len(procs) > 0
    p = read_process(1)
    assert p is not None
    assert p.name == "systemd"


# ============== G6 throttle history ==============
def g6():
    from src.core.throttle_history import read_perf_log, compute_timeline
    from src.core.config import Config
    cfg = Config.get()
    rows = read_perf_log(Path(cfg.perf_log_dir))
    timeline = compute_timeline(rows)
    assert len(timeline) == 24  # 24 小时


# ============== 集成 ==============
def integration():
    import controller
    assert controller._LOADED_FROM_PROFILE
    assert len(controller.SCENES) == 6
    # 验证 get_active_scene
    params = {"governor": "performance", "epp": "performance", "pl1_w": 25, "turbo": True}
    assert controller.get_active_scene(params) == "ac-perf"


# ============== 端到端 ==============
def end_to_end():
    """完整路径：profile → controller → MSR → throttle history"""
    # 测试与用户语言设置解耦（历史文案断言写死中文）
    from src.core.i18n import set_locale
    set_locale("zh_CN")
    # 1. 加载 profile
    from src.core.profile import get_loader
    p = get_loader().load("ac-perf")
    assert p.get("cpu", "pl1_watts") == "25"

    # 2. controller 用 profile
    import controller
    assert controller.SCENE_PARAMS["ac-perf"] == ("performance", "performance", 25, True)

    # 3. plugin 注册表
    from src.core.plugin import get_registry
    reg = get_registry()
    assert reg.load("thermal_ctl") is not None

    # 4. 进程工具可用
    from src.core.process_utils import read_process
    assert read_process(1) is not None

    # 5. throttle history 可用
    from src.core.throttle_history import get_throttle_history
    _, hist = get_throttle_history(hours=24)
    assert "限流时间轴" in hist


def main():
    print("=" * 60)
    print("Phase 2 完整测试 (G1 + G2 + G3 + G6)")
    print("=" * 60)
    print()
    test("G1 profile 系统", g1)
    test("G2 plugin 系统", g2)
    test("G3 进程工具", g3)
    test("G6 限流时间轴", g6)
    test("集成 (controller)", integration)
    test("端到端", end_to_end)
    print()
    print("=" * 60)
    print(f"测试结果: {TESTS_PASSED}/{TESTS_RUN} 通过, {TESTS_FAILED} 失败")
    print("=" * 60)
    return 0 if TESTS_FAILED == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
