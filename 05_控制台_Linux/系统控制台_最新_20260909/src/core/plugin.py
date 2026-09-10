"""
src/core/plugin.py — Phase 2 G2 实施: plugin 抽象

目的: 把 controller.thermal() 写死的 8 个子命令改为可插拔的 plugin
       借鉴 TuneD 的 plugin base.py 30+ 内置 plugin 机制

特性:
  - Plugin 基类（_init / _apply / _undo 3 钩子）
  - 自动发现（用户目录 + 内置目录）
  - 注册表（plugin_name → PluginClass）
  - 简化 API（无需 30+ 钩子也能工作）
  - 错误隔离（plugin 失败不影响其他 plugin）
  - 兼容原 controller.thermal() 8 命令（fallback）
"""
import importlib
import importlib.util
import inspect
import os
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

# 内置 plugin 目录（项目自带）
BUILTIN_PLUGIN_DIR = "plugins"

# 用户 plugin 目录
USER_PLUGIN_DIR = "~/.config/system-console/plugins"


class PluginContext:
    """plugin 运行时上下文（传递给 _init/_apply/_undo）"""

    def __init__(self, logger=None, dry_run=False):
        self.logger = logger
        self.dry_run = dry_run
        self.results: Dict[str, Any] = {}

    def log(self, msg: str):
        if self.logger:
            self.logger(msg)
        else:
            print(f"[plugin] {msg}")

    def run(self, args: List[str], timeout: int = 30):
        """执行系统命令（封装 subprocess）"""
        import subprocess
        if self.dry_run:
            self.log(f"[dry-run] would run: {' '.join(args)}")
            return 0, "", ""
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            return r.returncode, r.stdout.strip(), r.stderr.strip()
        except Exception as e:
            return -1, "", str(e)

    def set_result(self, key: str, value: Any):
        self.results[key] = value


class Plugin(ABC):
    """plugin 基类（所有 plugin 继承此类）"""

    # 子类必须定义
    name: str = ""          # plugin 名（用于注册和调用）
    version: str = "1.0"    # plugin 版本（semver）

    def __init__(self):
        self.enabled = True

    @abstractmethod
    def _init(self, ctx: PluginContext):
        """plugin 加载时调用一次（可选实现）"""
        pass

    @abstractmethod
    def _apply(self, ctx: PluginContext):
        """场景切换时调用（必须实现）"""
        pass

    def _undo(self, ctx: PluginContext):
        """切回时调用（可选）"""
        pass

    def __repr__(self):
        return f"<Plugin name={self.name!r} version={self.version!r}>"


class PluginRegistry:
    """plugin 注册表（单例）"""

    def __init__(self, builtin_dir: Path, user_dir: Path):
        self.builtin_dir = builtin_dir
        self.user_dir = user_dir
        self._plugins: Dict[str, Plugin] = {}

    def discover(self) -> List[str]:
        """发现所有可用 plugin"""
        names = set()

        for d in [self.builtin_dir, self.user_dir]:
            if d.exists():
                for f in d.glob("*.py"):
                    if f.name.startswith("_") or f.name == "base.py":
                        continue
                    stem = f.stem
                    # 用户目录优先
                    if stem not in names or d == self.user_dir:
                        names.add(stem)

        return sorted(names)

    def load(self, name: str) -> Optional[Plugin]:
        """加载一个 plugin"""
        if name in self._plugins:
            return self._plugins[name]

        # 1. 用户目录优先
        for d in [self.user_dir, self.builtin_dir]:
            if not d.exists():
                continue
            path = d / f"{name}.py"
            if not path.exists():
                continue
            try:
                plugin = self._load_from_file(path, name)
                if plugin is not None:
                    self._plugins[name] = plugin
                    return plugin
            except Exception as e:
                print(f"⚠ 加载 plugin {name} 失败 ({path}): {e}")
                continue

        return None

    def _load_from_file(self, path: Path, name: str) -> Optional[Plugin]:
        """从 .py 文件动态加载 plugin

        重要: 不依赖 issubclass(obj, Plugin) — 改用 __mro__ 检查
        因为 Plugin 类在不同模块上下文里可能是不同对象
        （如 __main__.Plugin vs src.core.plugin.Plugin）
        """
        try:
            spec = importlib.util.spec_from_file_location(f"plugin_{name}", str(path))
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)

            # 找继承 Plugin 的类（用 mro 检查，避免跨模块 issubclass 问题）
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if obj is Plugin:
                    continue
                # 检查是否继承 Plugin（通过 mro）
                mro_names = [b.__name__ for b in obj.__mro__] if hasattr(obj, '__mro__') else []
                if 'Plugin' not in mro_names:
                    continue
                # 检查 name 属性
                obj_name = getattr(obj, 'name', None)
                if obj_name == name:
                    return obj()
            return None
        except Exception as e:
            print(f"⚠ 加载 plugin {name} 时异常 ({path}): {e}")
            return None

    def list_plugins(self) -> Dict[str, str]:
        """列出所有 plugin（name → version）"""
        result = {}
        for name in self.discover():
            p = self.load(name)
            if p is not None:
                result[name] = p.version
        return result

    def apply_plugin(self, name: str, ctx: PluginContext) -> bool:
        """应用一个 plugin（带错误隔离）"""
        plugin = self.load(name)
        if plugin is None:
            ctx.log(f"plugin {name!r} 不存在")
            return False
        if not plugin.enabled:
            ctx.log(f"plugin {name!r} 已禁用")
            return False
        try:
            plugin._init(ctx)
            plugin._apply(ctx)
            return True
        except Exception as e:
            ctx.log(f"plugin {name!r} _apply 失败: {e}")
            return False

    def undo_plugin(self, name: str, ctx: PluginContext) -> bool:
        """撤销一个 plugin"""
        plugin = self.load(name)
        if plugin is None:
            return False
        try:
            plugin._undo(ctx)
            return True
        except Exception as e:
            ctx.log(f"plugin {name!r} _undo 失败: {e}")
            return False


# 兼容原 controller.thermal() 8 子命令的 fallback
class ThermalControlPlugin(Plugin):
    """thermal_ctl.sh 8 子命令的 plugin 包装（fallback）"""
    name = "thermal_ctl"
    version = "1.0"

    # 子命令映射
    COMMANDS = {
        "fan_boost": ("on", "off"),
        "tcc": None,  # 读 /sys 类
        "pclamp": None,
        "maxperf": ("on", "off"),
        "usb": ("on", "off"),
        "wifi": ("on", "off"),
        "pl": None,
        "camera": ("on", "off"),
    }

    def _init(self, ctx: PluginContext):
        import controller
        self._controller = controller

    def _apply(self, ctx: PluginContext):
        # 简单 pass（兼容层）
        ctx.set_result("note", "thermal_ctl 由 controller.thermal() 直接处理")

    def _undo(self, ctx: PluginContext):
        pass


def get_registry() -> PluginRegistry:
    """获取默认 plugin 注册表（单例）"""
    global _registry
    if _registry is None:
        import os
        import sys
        # 总是先把项目根加 sys.path（保险起见）
        try:
            plugin_file = Path(__file__).resolve()
            project_root = str(plugin_file.parent.parent.parent)
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
        except Exception:
            pass

        try:
            from .config import Config
            cfg = Config.get()
            builtin = Path(cfg.base_dir) / BUILTIN_PLUGIN_DIR
        except (ImportError, ValueError):
            try:
                from src.core.config import Config as _C
                cfg = _C.get()
                builtin = Path(cfg.base_dir) / BUILTIN_PLUGIN_DIR
            except Exception:
                # 兑底：硬编码默认路径
                builtin = Path(__file__).parent.parent.parent / BUILTIN_PLUGIN_DIR
        user = Path(USER_PLUGIN_DIR).expanduser()
        _registry = PluginRegistry(builtin, user)
    return _registry


_registry: Optional[PluginRegistry] = None


# CLI
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Plugin 管理")
    parser.add_argument("--list", action="store_true", help="列出所有 plugin")
    parser.add_argument("--apply", metavar="NAME", help="应用一个 plugin")
    parser.add_argument("--show", metavar="NAME", help="显示 plugin 信息")
    parser.add_argument("--dir", metavar="PATH", help="切换内置 plugin 目录")
    args = parser.parse_args()

    reg = get_registry()
    if args.dir:
        reg.builtin_dir = Path(args.dir)

    if args.list:
        plugins = reg.list_plugins()
        print(f"可用 plugin ({len(plugins)}):")
        for n, v in plugins.items():
            print(f"  • {n} (v{v})")
        return 0

    if args.show:
        p = reg.load(args.show)
        if p is None:
            print(f"❌ plugin {args.show!r} 不存在")
            return 1
        print(f"Plugin: {p.name}")
        print(f"Version: {p.version}")
        print(f"Class: {type(p).__name__}")
        methods = [m for m in dir(p) if not m.startswith('__')]
        print(f"Methods: {methods}")
        return 0

    if args.apply:
        ctx = PluginContext()
        ok = reg.apply_plugin(args.apply, ctx)
        return 0 if ok else 1

    parser.print_help()
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
