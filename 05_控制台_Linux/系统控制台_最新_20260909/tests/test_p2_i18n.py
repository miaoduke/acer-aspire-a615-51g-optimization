#!/usr/bin/env python3
"""P2-1: i18n 单元测试"""
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from src.core.i18n import T as _, set_locale, translate, I18n

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


def test_default_zh():
    """默认中文"""
    set_locale("zh_CN")
    if _("总览") != "总览":
        return f"应为 '总览'，实际 '{_('总览')}'"
    return True


def test_switch_to_en():
    """切到英文"""
    set_locale("en_US")
    if _("总览") != "Overview":
        return f"应为 'Overview'，实际 '{_('总览')}'"
    return True


def test_translate_dict():
    """直接用 translate 函数"""
    if translate("总览", "en_US") != "Overview":
        return f"translate 失败"
    return True


def test_switch_back_zh():
    """切回中文"""
    set_locale("zh_CN")
    if _("总览") != "总览":
        return f"应为 '总览'，实际 '{_('总览')}'"
    return True


def test_unknown_msg():
    """未翻译消息回退原文"""
    set_locale("en_US")
    if _("不存在的消息") != "不存在的消息":
        return "应回退原文"
    return True


def test_i18n_singleton():
    """I18n 是单例"""
    i1 = I18n.get()
    i2 = I18n.get()
    if i1 is not i2:
        return "I18n 不是单例"
    return True


def main():
    print("=" * 60)
    print("P2-1 i18n 框架测试")
    print("=" * 60)
    test("默认中文", test_default_zh)
    test("切到英文", test_switch_to_en)
    test("translate() 直接调用", test_translate_dict)
    test("切回中文", test_switch_back_zh)
    test("未知消息回退", test_unknown_msg)
    test("I18n 单例", test_i18n_singleton)
    print()
    print(f"测试结果: {TESTS_PASSED}/{TESTS_RUN} 通过, {TESTS_FAILED} 失败")
    return 0 if TESTS_FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
