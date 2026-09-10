"""
src/core/profile_debug.py — P3-1: profile 嵌套调试工具

目的: 可视化 profile 继承链
  - 显示每个 profile 来自哪
  - 段覆盖追踪
  - 值来源标注
"""
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import os
import sys
# 三重 fallback
try:
    from .profile import ProfileLoader, get_loader, ProfileError
except (ImportError, ValueError):
    try:
        from src.core.profile import ProfileLoader, get_loader, ProfileError
    except ImportError:
        # 兑底：手动加路径
        _this = os.path.dirname(os.path.abspath(__file__))
        _project = os.path.dirname(os.path.dirname(_this))
        if _project not in sys.path:
            sys.path.insert(0, _project)
        from src.core.profile import ProfileLoader, get_loader, ProfileError


def trace_inheritance(name: str, _visited: Optional[Set[str]] = None, _depth: int = 0) -> List[str]:
    """追踪继承链（深度优先）

    Returns:
        list of "→ parent" lines
    """
    if _visited is None:
        _visited = set()
    if name in _visited:
        return [f"{'  ' * _depth}→ {name} (循环依赖)"]
    _visited = _visited | {name}

    loader = get_loader()
    try:
        raw = loader.load_raw(name)
    except ProfileError as e:
        return [f"{'  ' * _depth}→ {name} (错误: {e})"]

    lines = [f"{'  ' * _depth}📁 {name}"]
    for inc in raw.includes:
        lines.extend(trace_inheritance(inc, _visited, _depth + 1))

    return lines


def trace_value_origin(profile_name: str, section: str, key: str) -> str:
    """追踪一个具体值的来源

    Returns:
        "来自 profile_name (section.key)" 或 "未设置"
    """
    loader = get_loader()
    try:
        merged = loader.load(profile_name)
        if key in merged.sections.get(section, {}):
            return f"✅ {profile_name} 包含 [{section}].{key} = {merged.sections[section][key]}"
        else:
            return f"❌ {profile_name} 链上都没有 [{section}].{key}"
    except ProfileError as e:
        return f"❌ 错误: {e}"


def dump_inheritance_tree(name: str = None) -> str:
    """完整继承树（人类可读）

    Args:
        name: profile 名（None=所有）
    """
    loader = get_loader()
    lines = ["=" * 60, "Profile 继承树", "=" * 60]

    if name:
        lines.extend(trace_inheritance(name))
    else:
        for n in loader.list_profiles():
            if n in ("balanced", "user_custom"):
                continue
            lines.append("")
            lines.extend(trace_inheritance(n))

    return "\n".join(lines)


def verify_no_circular() -> List[str]:
    """检查所有 profile 是否有循环依赖

    Returns:
        错误列表（空=无循环）
    """
    loader = get_loader()
    errors = []

    for name in loader.list_profiles():
        visited = set()
        path = []
        current = name
        while current:
            if current in visited:
                cycle = " → ".join(path + [current])
                errors.append(f"循环依赖: {cycle}")
                break
            visited.add(current)
            path.append(current)
            try:
                raw = loader.load_raw(current)
                current = raw.includes[0] if raw.includes else None
            except ProfileError as e:
                errors.append(f"{current}: {e}")
                break

    return errors


# CLI
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Profile 嵌套调试工具")
    parser.add_argument("profile", nargs="?", help="指定 profile（默认所有）")
    parser.add_argument("--tree", action="store_true", help="显示完整继承树")
    parser.add_argument("--trace", nargs=3, metavar=("PROFILE", "SECTION", "KEY"),
                        help="追踪具体值的来源")
    parser.add_argument("--check-circular", action="store_true", help="检查循环依赖")
    args = parser.parse_args()

    if args.trace:
        profile, section, key = args.trace
        print(trace_value_origin(profile, section, key))
        return 0

    if args.check_circular:
        errors = verify_no_circular()
        if errors:
            print("❌ 发现循环:")
            for e in errors:
                print(f"  {e}")
            return 1
        else:
            print("✅ 无循环依赖")
            return 0

    print(dump_inheritance_tree(args.profile))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
