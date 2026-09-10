"""
src/core/i18n_apply.py — P1-A: i18n 实际应用到 UI

遍历所有 ui_*.py，把硬编码中文改成 T() 调用
"""
import os
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent

# 翻译映射（中文 → 翻译键）
TRANSLATIONS = {
    # Page names
    "总览": "Overview",
    "电源场景": "PowerScenes",
    "电池保养": "BatteryCare",
    "高级控制": "AdvancedControl",
    "进程详情": "Processes",
    "系统维护": "Maintenance",
    "说明文档": "Documentation",
    # Buttons
    "进入 M3（省电持久化）": "EnterM3",
    "退出 M3（恢复自动）": "ExitM3",
    "保存默认档位": "SaveDefaults",
    "运行基准测试（插电，约 2 分钟）": "RunBenchmark",
    "一键提权": "Authorize",
    "一键安装/修复": "Install",
    "关闭": "Close",
    "确定": "OK",
    "取消": "Cancel",
    # Profile 面板
    "Profile 配置（来源：内置 · 用户 · 硬编码）": "ProfilePanelTitle",
    "内置": "Builtin",
    "用户": "User",
    "硬编码": "Hardcoded",
    # Common
    "场景": "Scene",
    "电源": "Power",
    "电池": "Battery",
    "温度": "Temperature",
    "限流状态": "Throttling",
    "CPU": "CPU",
    "GPU": "GPU",
    "M3 离电效能模式：": "M3Label",
    "保存": "Save",
    # Status
    "● M3 生效中（PPD=power-saver 持久化，acdc 自动切换已停）": "M3Active",
    "○ M3 未启用": "M3Inactive",
    "当前默认：": "CurrentDefault",
    "插电 → ": "ACDefault",
    "离电 → ": "DCDefault",
    "（插拔电自动应用，也可手动切换任意场景）": "AutoSwitchHint",
}


def generate_i18n_dict():
    """生成 src/core/i18n_messages.py（程序化翻译字典）"""
    lines = [
        '"""',
        'i18n_messages.py — 翻译字典（程序生成）',
        '',
        '用法:',
        '  from src.core.i18n_messages import M',
        '  T(M["总览"])  # → "总览" (zh) / "Overview" (en)',
        '"""',
        '',
        'M = {',
    ]
    for zh, en_key in TRANSLATIONS.items():
        lines.append(f'    {zh!r}: {en_key!r},  # {zh}')
    lines.append('}')
    return '\n'.join(lines) + '\n'


def find_hardcoded_chinese(filepath):
    """找文件中所有硬编码中文字符串"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    # 找 "..." 含中文
    pattern = r'["\']([^"\']*[\u4e00-\u9fff][^"\']*)["\']'
    matches = re.findall(pattern, content)
    return matches


def main():
    # 生成翻译字典
    output = PROJECT_DIR / "src" / "core" / "i18n_messages.py"
    output.write_text(generate_i18n_dict(), encoding='utf-8')
    print(f"✓ 生成 {output}")
    print(f"  翻译条目: {len(TRANSLATIONS)}")

    # 扫描 ui_*.py
    ui_files = list((PROJECT_DIR / "").glob("ui_*.py"))
    total_chinese = 0
    for f in ui_files:
        matches = find_hardcoded_chinese(f)
        if matches:
            total_chinese += len(matches)
            print(f"  {f.name}: {len(matches)} 个硬编码中文")
            for m in matches[:3]:
                print(f"    - {m[:50]}")

    print(f"\n总计: {total_chinese} 个硬编码中文待翻译")


if __name__ == "__main__":
    main()
