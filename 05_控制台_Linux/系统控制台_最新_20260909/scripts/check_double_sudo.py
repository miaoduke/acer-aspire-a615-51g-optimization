#!/usr/bin/env python3
"""
scripts/check_double_sudo.py — A-S1 实施: Python AST 静态分析检测 double sudo

目的: 防止 _run(["sudo", "..."]) 被错误地传成 _run([..., "sudo", ...])
       或 args 里含 "sudo" 字符串（如 ["bash", "sudo_cmd.sh"]）的子命令

用法:
  python3 scripts/check_double_sudo.py [files_or_dirs...]
  默认扫描: src/ ui_*.py console.py controller.py collector.py
"""
import ast
import os
import sys
from pathlib import Path
from typing import List, Tuple


def find_double_sudo(filepath: str) -> List[Tuple[int, str, str]]:
    """扫描一个 .py 文件，返回所有可疑的 'double sudo' 调用位置

    返回: [(line_no, pattern_type, detail), ...]
    """
    findings = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
    except (OSError, UnicodeDecodeError) as e:
        return [(0, "READ_ERROR", str(e))]

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as e:
        return [(e.lineno or 0, "SYNTAX_ERROR", str(e))]

    # 模式 1: subprocess.run / subprocess.Popen / _run 等的可疑子命令列表
    #   含 "sudo" 字符串参数
    SUSPICIOUS_FUNCS = {
        'subprocess.run', 'subprocess.Popen', 'subprocess.call',
        'subprocess.check_call', 'subprocess.check_output',
        '_run', 'controller._run', 'os.system', 'os.popen',
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node.func)
            if func_name not in SUSPICIOUS_FUNCS:
                continue
            # 检查第一个参数（list 形式）含 "sudo" 字符串
            if node.args and isinstance(node.args[0], (ast.List, ast.Tuple)):
                elts = node.args[0].elts
                for i, elt in enumerate(elts):
                    if isinstance(elt, ast.Constant) and elt.value == "sudo":
                        # 找外层调用以判定是否已含 sudo
                        if i == 0:
                            # OK: subprocess.run(["sudo", "-n", ...])
                            continue
                        else:
                            findings.append((
                                node.lineno,
                                "DOUBLE_SUDO",
                                f"{func_name}([..., 'sudo', ...]) — 第 {i+1} 个位置出现 'sudo'"
                            ))
                    elif isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        if "sudo" in elt.value and "sudoers" not in elt.value:
                            # 字符串里嵌 'sudo'（如路径、命令名）
                            findings.append((
                                node.lineno,
                                "SUDO_IN_STRING",
                                f"字符串含 'sudo': {elt.value!r}"
                            ))

        # 模式 2: shell=True 且字符串含 "sudo"（更危险）
        if isinstance(node, ast.Call) and getattr(node, 'keywords', None):
            shell_true = False
            has_sudo = False
            for kw in node.keywords:
                if kw.arg == 'shell' and isinstance(kw.value, ast.Constant) and kw.value.value:
                    shell_true = True
            if shell_true and node.args:
                # 找 shell 命令字符串
                if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    if 'sudo' in node.args[0].value:
                        findings.append((
                            node.lineno,
                            "SHELL_SUDO",
                            f"shell=True + 含 'sudo' 的命令: {node.args[0].value[:80]!r}"
                        ))

    return findings


def _get_func_name(func_node) -> str:
    """获取函数调用的全名（如 'subprocess.run'）"""
    if isinstance(func_node, ast.Name):
        return func_node.id
    elif isinstance(func_node, ast.Attribute):
        parts = []
        cur = func_node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return '.'.join(reversed(parts))
    return ''


def scan_paths(paths: List[str]) -> dict:
    """扫描给定的路径列表，返回 {file: findings}"""
    results = {}
    for p in paths:
        path = Path(p)
        if path.is_file() and path.suffix == '.py':
            findings = find_double_sudo(str(path))
            if findings:
                results[str(path)] = findings
        elif path.is_dir():
            for py_file in path.rglob('*.py'):
                if '__pycache__' in str(py_file):
                    continue
                findings = find_double_sudo(str(py_file))
                if findings:
                    results[str(py_file)] = findings
    return results


def main():
    if len(sys.argv) > 1:
        targets = sys.argv[1:]
    else:
        # 默认扫描
        targets = ['src/', 'console.py', 'controller.py', 'collector.py',
                  'ui_advanced.py', 'ui_battery.py', 'ui_dashboard.py',
                  'ui_docs.py', 'ui_maintenance.py', 'ui_scenes.py',
                  'async_util.py', 'console_full_test.py']

    results = scan_paths(targets)

    if not results:
        print("✅ 未发现 double-sudo 风险")
        return 0

    print(f"⚠️  发现 {sum(len(v) for v in results.values())} 处可疑调用（{len(results)} 个文件）:\n")
    for filepath, findings in sorted(results.items()):
        print(f"📄 {filepath}")
        for line_no, pattern, detail in findings:
            icon = "🔴" if pattern == "DOUBLE_SUDO" else "🟡"
            print(f"  {icon} L{line_no}: [{pattern}] {detail}")
        print()

    # 返回 1 表示有发现（非阻塞）；返回 0 表示干净
    has_double = any(p == "DOUBLE_SUDO" for findings in results.values() for _, p, _ in findings)
    return 1 if has_double else 0


if __name__ == '__main__':
    sys.exit(main())
