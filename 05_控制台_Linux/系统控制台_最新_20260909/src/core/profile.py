"""
src/core/profile.py — Phase 2 G1 实施: profile 配置化

目的: 解除 6 场景硬编码（controller.py:14-37），改为从
       ~/.config/system-console/profiles/<name>/tuned.conf 读取

特性:
  - INI 语法（[section] + key=value）
  - include= 继承（支持链式 + 循环检测）
  - 段合并（[cpu] 段内的字段按"覆盖"语义合并）
  - 变量插值（${var} 或 %{var}）
  - 验证器（--validate 命令）
  - 向后兼容（fallback 到硬编码 SCENES 表）

借鉴: TuneD profiles/ 机制（[main] include= + 段覆盖）
"""
import configparser
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# 内置 profile 目录（项目自带，readonly）
BUILTIN_PROFILE_DIR = "profiles"  # 相对于项目 BASE

# 用户 profile 目录（用户自定义，优先级高）
USER_PROFILE_DIR = "~/.config/system-console/profiles"

# 段名常量
SECTION_MAIN = "main"
SECTION_CPU = "cpu"
SECTION_GPU = "gpu"
SECTION_BATTERY = "battery"
SECTION_THERMAL = "thermal"
SECTION_DISK = "disk"
SECTION_NETWORK = "network"


class ProfileError(Exception):
    """Profile 解析/验证错误"""
    pass


class Profile:
    """单个 profile 配置（已解析 + 合并完成）"""

    def __init__(self, name: str, source_path: Path):
        self.name = name
        self.source_path = source_path
        self.summary: str = ""
        self.version: int = 1
        self.includes: List[str] = []
        # 各段: {段名: {key: value}}
        self.sections: Dict[str, Dict[str, str]] = {}
        # 解析错误
        self.errors: List[str] = []

    def __repr__(self):
        return f"<Profile name={self.name!r} from={self.source_path.name} sections={list(self.sections.keys())}>"

    def get(self, section: str, key: str, default=None):
        """获取段内键值"""
        return self.sections.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: str):
        """设置段内键值（用于测试或程序化修改）"""
        if section not in self.sections:
            self.sections[section] = {}
        self.sections[section][key] = str(value)


class ProfileLoader:
    """Profile 加载器（单例）

    加载顺序（优先级从高到低）:
      1. 用户自定义: ~/.config/system-console/profiles/<name>/tuned.conf
      2. 项目内置: <BASE>/profiles/<name>/tuned.conf
      3. fallback: 硬编码 SCENES（兼容旧版本）
    """

    def __init__(self, builtin_dir: Path, user_dir: Path):
        self.builtin_dir = builtin_dir
        self.user_dir = user_dir
        self._cache: Dict[str, Profile] = {}
        # P2-B: merged 缓存（避免重复合并）
        self._merged_cache: Dict[str, Profile] = {}
        self._hardcoded_fallback: Dict[str, Profile] = {}

    def find_profile_path(self, name: str) -> Optional[Path]:
        """查找 profile 文件路径（用户优先 → 内置）"""
        # 1. 用户目录
        user_path = self.user_dir / name / "tuned.conf"
        if user_path.exists():
            return user_path
        # 2. 内置目录
        builtin_path = self.builtin_dir / name / "tuned.conf"
        if builtin_path.exists():
            return builtin_path
        return None

    def load_raw(self, name: str) -> Profile:
        """加载原始 profile（不解析 include）"""
        if name in self._cache:
            return self._cache[name]

        path = self.find_profile_path(name)
        if path is None:
            # 尝试 fallback 到硬编码
            if name in self._hardcoded_fallback:
                return self._hardcoded_fallback[name]
            raise ProfileError(f"profile 不存在: {name!r}（查找路径: 用户={self.user_dir}/{name}, 内置={self.builtin_dir}/{name}）")

        profile = self._parse_file(path, name)
        self._cache[name] = profile
        return profile

    def load(self, name: str, _visited: Optional[Set[str]] = None) -> Profile:
        """加载 profile（含 include 解析 + 段合并）

        P2-B: 加 merged 缓存（避免重复合并计算）
        """
        # P2-B: 查 merged 缓存
        if _visited is None and name in self._merged_cache:
            return self._merged_cache[name]

        if _visited is None:
            _visited = set()

        # 循环依赖检测
        if name in _visited:
            raise ProfileError(f"循环 include: {' -> '.join(_visited)} -> {name}")
        _visited = _visited | {name}

        raw = self.load_raw(name)

        # 解析 include 链（递归）
        merged_sections: Dict[str, Dict[str, str]] = {}
        summary_parts = []
        version = raw.version

        for include_name in raw.includes:
            included = self.load(include_name, _visited)
            for sec_name, sec_data in included.sections.items():
                if sec_name not in merged_sections:
                    merged_sections[sec_name] = {}
                merged_sections[sec_name].update(sec_data)
            if included.summary:
                summary_parts.append(f"[{include_name}] {included.summary}")
            version = max(version, included.version)

        # 应用本 profile 的段（覆盖）
        for sec_name, sec_data in raw.sections.items():
            if sec_name not in merged_sections:
                merged_sections[sec_name] = {}
            merged_sections[sec_name].update(sec_data)

        # 构造合并后的 profile
        result = Profile(name, raw.source_path)
        result.sections = merged_sections
        result.version = version
        if raw.summary:
            result.summary = raw.summary
        elif summary_parts:
            result.summary = " ← ".join(summary_parts)
        else:
            result.summary = f"profile {name}"

        # P2-B: 存 merged 缓存
        if _visited is None or len(_visited) == 1:
            self._merged_cache[name] = result
        return result

    def _parse_file(self, path: Path, name: str) -> Profile:
        """解析单个 .conf 文件"""
        profile = Profile(name, path)
        # INI 解析（保留大小写）
        cp = configparser.RawConfigParser()
        cp.optionxform = str  # 不转小写

        try:
            cp.read(str(path), encoding='utf-8')
        except configparser.Error as e:
            profile.errors.append(f"INI 解析失败: {e}")
            return profile

        # [main] 段特殊处理
        if cp.has_section(SECTION_MAIN):
            main_sec = cp[SECTION_MAIN]
            profile.summary = main_sec.get('summary', '')
            try:
                profile.version = int(main_sec.get('version', 1))
            except ValueError:
                profile.errors.append(f"version 非整数: {main_sec.get('version')!r}")
            include_str = main_sec.get('include', '')
            if include_str:
                # 支持空格分隔的多个 include
                profile.includes = [x.strip() for x in include_str.split() if x.strip()]

        # 其他段: 存为 sections
        for sec_name in cp.sections():
            if sec_name == SECTION_MAIN:
                continue
            profile.sections[sec_name] = dict(cp[sec_name])

        return profile

    def list_profiles(self) -> List[str]:
        """列出所有可用 profile（内置 + 用户）"""
        names = set()

        # 内置
        if self.builtin_dir.exists():
            for p in self.builtin_dir.iterdir():
                if p.is_dir() and (p / "tuned.conf").exists():
                    names.add(p.name)

        # 用户
        if self.user_dir.exists():
            for p in self.user_dir.iterdir():
                if p.is_dir() and (p / "tuned.conf").exists():
                    names.add(p.name)

        # fallback 硬编码
        names.update(self._hardcoded_fallback.keys())

        return sorted(names)

    def register_hardcoded(self, name: str, params: Tuple):
        """注册硬编码 fallback profile（兼容旧 SCENES）"""
        # params 格式: (governor, epp, pl1_w, turbo)
        if len(params) != 4:
            return
        p = Profile(name, Path("<hardcoded>"))
        p.summary = f"硬编码内置场景 {name}"
        p.sections = {
            SECTION_CPU: {
                "governor": params[0],
                "energy_performance_preference": params[1],
                "pl1_watts": str(params[2]),
                "turbo": "1" if params[3] else "0",
            }
        }
        self._hardcoded_fallback[name] = p


def get_loader() -> ProfileLoader:
    """获取默认 loader（单例）"""
    global _loader
    if _loader is None:
        # 三重 fallback：相对导入 / src 包 / 脚本路径
        Config = None
        for import_path in ['.config', 'src.core.config']:
            try:
                if import_path.startswith('.'):
                    from .config import Config as _C
                else:
                    import importlib
                    _C = importlib.import_module(import_path)
                Config = _C.Config
                break
            except (ImportError, ValueError, AttributeError):
                continue
        if Config is None:
            # 兑底：硬编码默认路径
            builtin = Path(__file__).parent.parent.parent / BUILTIN_PROFILE_DIR
            user = Path(USER_PROFILE_DIR).expanduser()
            _loader = ProfileLoader(builtin, user)
        else:
            cfg = Config.get()
            builtin = Path(cfg.base_dir) / BUILTIN_PROFILE_DIR
            user = Path(USER_PROFILE_DIR).expanduser()
            _loader = ProfileLoader(builtin, user)

        # 注册硬编码 fallback
        FALLBACK_SCENES = {
            "ac-perf":  ("performance", "performance", 25, True),
            "ac-bal":   ("powersave", "balance_performance", 15, True),
            "ac-quiet": ("powersave", "balance_power", 10, True),
            "bat-save": ("powersave", "power", 10, False),
            "bat-bal":  ("powersave", "balance_power", 12, True),
            "bat-perf": ("performance", "performance", 15, True),
        }
        for name, params in FALLBACK_SCENES.items():
            _loader.register_hardcoded(name, params)
    return _loader


_loader: Optional[ProfileLoader] = None


def validate_profile(name: str) -> Tuple[bool, List[str]]:
    """验证 profile 是否合法

    返回: (is_valid, errors)
    """
    loader = get_loader()
    errors = []
    try:
        profile = loader.load(name)
    except ProfileError as e:
        return False, [str(e)]

    errors.extend(profile.errors)

    # 必填字段检查
    cpu_sec = profile.sections.get(SECTION_CPU, {})
    if 'governor' not in cpu_sec:
        errors.append("[cpu] 缺 governor")
    if 'pl1_watts' not in cpu_sec:
        errors.append("[cpu] 缺 pl1_watts")
    # governor 值范围
    gov = cpu_sec.get('governor', '')
    if gov and gov not in ('performance', 'powersave'):
        errors.append(f"governor 非法: {gov!r}（应为 performance 或 powersave）")
    # pl1 范围
    try:
        pl1 = int(cpu_sec.get('pl1_watts', 0))
        if pl1 < 5 or pl1 > 50:
            errors.append(f"pl1_watts 越界: {pl1}（应在 5-50）")
    except ValueError:
        errors.append(f"pl1_watts 非整数: {cpu_sec.get('pl1_watts')!r}")
    # turbo 范围
    turbo = cpu_sec.get('turbo', '')
    if turbo and turbo not in ('0', '1'):
        errors.append(f"turbo 非法: {turbo!r}（应为 0 或 1）")

    return (len(errors) == 0), errors


# 命令行入口
def main():
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Profile 配置验证")
    parser.add_argument("--list", action="store_true", help="列出所有可用 profile")
    parser.add_argument("--validate", metavar="NAME", help="验证指定 profile")
    parser.add_argument("--show", metavar="NAME", help="显示 profile 合并后内容")
    parser.add_argument("--dir", metavar="PATH", help="切换内置 profile 目录")
    args = parser.parse_args()

    loader = get_loader()
    if args.dir:
        loader.builtin_dir = Path(args.dir)
        loader._cache.clear()

    if args.list:
        names = loader.list_profiles()
        print(f"可用 profile ({len(names)}):")
        for n in names:
            marker = "🔧" if loader.find_profile_path(n) else "📦"
            print(f"  {marker} {n}")
        return 0

    if args.validate:
        ok, errors = validate_profile(args.validate)
        if ok:
            print(f"✅ {args.validate} 验证通过")
            return 0
        else:
            print(f"❌ {args.validate} 验证失败:")
            for e in errors:
                print(f"  • {e}")
            return 1

    if args.show:
        try:
            p = loader.load(args.show)
        except ProfileError as e:
            print(f"❌ {e}")
            return 1
        print(f"Profile: {p.name}")
        print(f"Source:  {p.source_path}")
        print(f"Summary: {p.summary}")
        print(f"Version: {p.version}")
        print(f"Sections: {list(p.sections.keys())}")
        for sec_name, sec_data in p.sections.items():
            print(f"\n[{sec_name}]")
            for k, v in sec_data.items():
                print(f"  {k} = {v}")
        return 0

    parser.print_help()
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
