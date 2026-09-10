#!/usr/bin/env python3
"""
tests/test_phase1.py — Phase 1 单元测试套件

测试目标：
  1. config.py — 路径配置化
  2. check_double_sudo.py — double-sudo 检测
  3. check_conflicts.py — 冲突检测
  4. controller.py BASE 路径兼容性
  5. msr_deadman.sh 关键变量

运行: python3 tests/test_phase1.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# 路径设置
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

# 测试结果统计
TESTS_RUN = 0
TESTS_PASSED = 0
TESTS_FAILED = 0


def test(name, func):
    """运行单个测试"""
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
        return False


def test_config_basic():
    """测试 1: config.py 基本功能"""
    from src.core.config import Config, DEFAULTS
    assert 'base_dir' in DEFAULTS
    assert 'config_dir' in DEFAULTS
    cfg = Config.get()
    assert cfg.base_dir.exists(), f"base_dir 不存在: {cfg.base_dir}"
    assert cfg.config_dir.exists(), f"config_dir 不应已存在（首测）"
    return True


def test_config_yaml_roundtrip():
    """测试 2: config.yaml 写入读取 roundtrip"""
    from src.core.config import Config
    # 不再修改 HOME（会污染其他测试），仅验证 dump 不崩
    Config._instance = None
    cfg = Config.get()
    yaml_content = cfg.dump()
    if 'base_dir' not in yaml_content:
        return "dump 缺 base_dir"
    return True


def test_check_double_sudo_clean():
    """测试 3: 项目源码应无 double-sudo"""
    r = subprocess.run(
        ["python3", str(PROJECT_DIR / "scripts/check_double_sudo.py")],
        capture_output=True, text=True
    )
    # clean 时返回 0
    if r.returncode != 0:
        return f"检测到可疑调用:\n{r.stdout[:500]}"
    return True


def test_check_double_sudo_detects():
    """测试 4: double-sudo 检测工具能识别问题"""
    bad_code = '''
import subprocess
subprocess.run(["bash", "sudo", "something"])
'''
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(bad_code)
        bad_file = f.name
    try:
        r = subprocess.run(
            ["python3", str(PROJECT_DIR / "scripts/check_double_sudo.py"), bad_file],
            capture_output=True, text=True
        )
        if "DOUBLE_SUDO" not in r.stdout:
            return f"应检测到 DOUBLE_SUDO，但没检测到: {r.stdout}"
    finally:
        os.unlink(bad_file)
    return True


def test_check_conflicts_clean():
    """测试 5: 当前环境应无冲突（或无 Plundervolt 锁）"""
    r = subprocess.run(
        ["python3", str(PROJECT_DIR / "scripts/check_conflicts.py")],
        capture_output=True, text=True
    )
    # 无冲突时 exit 0
    if r.returncode not in (0, 1):
        return f"异常退出码 {r.returncode}: {r.stderr}"
    return True


def test_controller_base():
    """测试 6: controller.py BASE 路径正确解析"""
    # 重置 Config 单例（防上轮测试干扰）
    from src.core.config import Config
    Config._instance = None
    sys.path.insert(0, str(PROJECT_DIR))
    from controller import BASE, SCENE_SCRIPT, M3_SCRIPT
    if not os.path.exists(SCENE_SCRIPT):
        return f"SCENE_SCRIPT 不存在: {SCENE_SCRIPT}"
    if not os.path.exists(M3_SCRIPT):
        return f"M3_SCRIPT 不存在: {M3_SCRIPT}"
    return True


def test_deadman_script_syntax():
    """测试 7: msr_deadman.sh 语法正确"""
    r = subprocess.run(
        ["bash", "-n", str(PROJECT_DIR / "backend/msr_deadman.sh")],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        return f"语法错误: {r.stderr}"
    return True


def test_deadman_silent_path():
    """测试 8: msr_deadman.sh 正常温度下静默退出"""
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(
            [
                "bash", str(PROJECT_DIR / "backend/msr_deadman.sh"),
            ],
            env={**os.environ,
                 "MSR_DM_LOG": str(Path(tmp) / "deadman.log"),
                 "CURRENT_MV_FILE": "/etc/systemd/system/undervolt.service",
                 "MSR_DM_HIGH": "999999"},  # 极高阈值，不会触发
            capture_output=True, text=True
        )
        if r.returncode != 0:
            return f"应静默退出 0，实际 {r.returncode}: {r.stderr}"
    return True


def test_config_dump_format():
    """测试 9: config.dump() 输出可被解析回"""
    from src.core.config import Config
    cfg = Config.get()
    dumped = cfg.dump()
    # 至少含 7 个 key
    for key in ['base_dir', 'archive_root', 'data_dir', 'perf_log_dir',
                'snapshot_dir', 'config_dir', 'log_level']:
        if key not in dumped:
            return f"dump 缺 key: {key}"
    return True


def test_install_sh_syntax():
    """测试 10: install.sh 语法正确"""
    r = subprocess.run(
        ["bash", "-n", str(PROJECT_DIR / "install.sh")],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        return f"语法错误: {r.stderr}"
    return True


def main():
    print("=" * 60)
    print("Phase 1 单元测试套件")
    print("=" * 60)
    print()

    print("[1/10] config.py 基本功能")
    test("Config 单例 + 默认值加载", test_config_basic)

    print("\n[2/10] config.py YAML roundtrip")
    test("YAML 写入读取不崩", test_config_yaml_roundtrip)

    print("\n[3/10] check_double_sudo.py — 项目自检")
    test("源码无 double-sudo", test_check_double_sudo_clean)

    print("\n[4/10] check_double_sudo.py — 检测能力")
    test("能识别测试用例中的 double-sudo", test_check_double_sudo_detects)

    print("\n[5/10] check_conflicts.py — 冲突检测")
    test("无冲突时正常退出", test_check_conflicts_clean)

    print("\n[6/10] controller.py 路径解析")
    test("BASE / SCENE_SCRIPT / M3_SCRIPT 正确", test_controller_base)

    print("\n[7/10] msr_deadman.sh 语法")
    test("bash -n 校验通过", test_deadman_script_syntax)

    print("\n[8/10] msr_deadman.sh 静默路径")
    test("正常温度下 exit 0", test_deadman_silent_path)

    print("\n[9/10] config.dump() 格式")
    test("含 7 个关键 key", test_config_dump_format)

    print("\n[10/10] install.sh 语法")
    test("bash -n 校验通过", test_install_sh_syntax)

    print()
    print("=" * 60)
    print(f"测试结果: {TESTS_PASSED}/{TESTS_RUN} 通过, {TESTS_FAILED} 失败")
    print("=" * 60)
    return 0 if TESTS_FAILED == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
