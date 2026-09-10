#!/usr/bin/env python3
"""P1-A: i18n 实际应用测试"""
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from src.core.i18n import T, set_locale
from src.core.i18n_messages import M

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


def test_m_dict_loaded():
    """M 翻译字典加载"""
    if len(M) < 30:
        return f"M 字典只有 {len(M)} 项"
    return True


def test_page_names_translate():
    """7 个页面名翻译"""
    set_locale("zh_CN")
    for zh in ["总览", "电源场景", "电池保养", "高级控制", "进程详情", "系统维护", "说明文档"]:
        if zh not in M:
            return f"页面 '{zh}' 未在 M 字典"
    return True


def test_buttons_translate():
    """按钮翻译"""
    for zh in ["一键提权", "一键安装/修复", "保存默认档位"]:
        if zh not in M:
            return f"按钮 '{zh}' 未在 M"
    return True


def test_t_function_zh():
    """T() 在中文环境"""
    set_locale("zh_CN")
    if T("总览") != "总览":
        return f"T('总览') 应为 '总览'，实际 '{T('总览')}'"
    return True


def test_t_function_fallback():
    """T() 对未知消息回退原文"""
    set_locale("zh_CN")
    if T("不存在的消息xyz") != "不存在的消息xyz":
        return "应回退原文"
    return True


def test_messages_dict_coverage():
    """检查 M 字典覆盖关键 UI 字符串"""
    required = [
        "总览", "电源场景", "电池保养", "高级控制",
        "进程详情", "系统维护", "说明文档",
        "一键提权", "保存默认档位", "关闭",
        "内置", "用户", "硬编码",
        "温度", "电池", "限流状态",
    ]
    missing = [k for k in required if k not in M]
    if missing:
        return f"缺关键翻译: {missing[:5]}"
    return True


def main():
    print("=" * 60)
    print("P1-A i18n 实际应用测试")
    print("=" * 60)
    test("M 翻译字典加载", test_m_dict_loaded)
    test("页面名翻译覆盖", test_page_names_translate)
    test("按钮翻译覆盖", test_buttons_translate)
    test("T() 中文环境", test_t_function_zh)
    test("T() 未知消息回退", test_t_function_fallback)
    test("关键 UI 字符串覆盖", test_messages_dict_coverage)
    print()
    print(f"测试结果: {TESTS_PASSED}/{TESTS_RUN} 通过, {TESTS_FAILED} 失败")
    return 0 if TESTS_FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
