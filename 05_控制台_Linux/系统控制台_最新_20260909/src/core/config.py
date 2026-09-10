"""
src/core/config.py — H1 实施: 路径配置化

目的: 解除 BASE = /home/<USER>/.local/share/系统控制台/ 硬编码依赖，
       从 ~/.config/system-console/config.yaml 读取
"""
import os
from pathlib import Path
from typing import Optional

# 默认配置
DEFAULTS = {
    "base_dir": "~/.local/share/系统控制台",
    "archive_root": "~/projects/ws1/acer-性能优化方案",
    "data_dir": "~/.local/share/系统控制台/data",
    "perf_log_dir": "~/.local/share/系统控制台/data/perf",
    "snapshot_dir": "~/.local/share/系统控制台/data/snapshots",
    "config_dir": "~/.config/system-console",
    "log_level": "INFO",
    # 2026-09-08 新增：界面语言（"auto"=跟随系统 locale / "zh_CN" / "en_US"）
    "language": "auto",
}


class Config:
    """系统控制台配置（单例）"""
    _instance: Optional["Config"] = None

    def __init__(self):
        self.base_dir: Path = Path(DEFAULTS["base_dir"]).expanduser()
        self.archive_root: Path = Path(DEFAULTS["archive_root"]).expanduser()
        self.data_dir: Path = Path(DEFAULTS["data_dir"]).expanduser()
        self.perf_log_dir: Path = Path(DEFAULTS["perf_log_dir"]).expanduser()
        self.snapshot_dir: Path = Path(DEFAULTS["snapshot_dir"]).expanduser()
        self.config_dir: Path = Path(DEFAULTS["config_dir"]).expanduser()
        self.log_level: str = DEFAULTS["log_level"]
        self.language: str = DEFAULTS["language"]  # auto / zh_CN / en_US

        self._load_yaml()

    def _load_yaml(self):
        """从 YAML 加载（如存在）"""
        yaml_path = self.config_dir / "config.yaml"
        if not yaml_path.exists():
            return

        try:
            import yaml  # type: ignore
        except ImportError:
            # 无 PyYAML 依赖时，回退到极简 key: value 解析
            self._parse_simple_yaml(yaml_path)
            return

        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            for key, value in data.items():
                if key in DEFAULTS:
                    if key.endswith('_dir') or key == 'base_dir' or key == 'archive_root':
                        setattr(self, key, Path(value).expanduser())
                    else:
                        setattr(self, key, value)
        except Exception as e:
            print(f"⚠ config.yaml 解析失败: {e}, 使用默认值")

    def _parse_simple_yaml(self, yaml_path: Path):
        """极简 YAML 解析（无 PyYAML 依赖时 fallback）"""
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if ':' in line:
                        key, _, value = line.partition(':')
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key in DEFAULTS:
                            if key.endswith('_dir') or key in ('base_dir', 'archive_root'):
                                setattr(self, key, Path(value).expanduser())
                            else:
                                setattr(self, key, value)
        except Exception as e:
            print(f"⚠ 简单 YAML 解析失败: {e}")

    @classmethod
    def get(cls) -> "Config":
        """获取单例"""
        if cls._instance is None:
            cls._instance = Config()
        return cls._instance

    def dump(self) -> str:
        """导出当前配置为 YAML 格式（用于调试和模板生成）"""
        lines = [
            "# 系统控制台配置 — 由 src/core/config.py 管理",
            "# 路径用 ~ 开头或绝对路径均可",
            "",
            f"base_dir: {self.base_dir}",
            f"archive_root: {self.archive_root}",
            f"data_dir: {self.data_dir}",
            f"perf_log_dir: {self.perf_log_dir}",
            f"snapshot_dir: {self.snapshot_dir}",
            f"config_dir: {self.config_dir}",
            f"log_level: {self.log_level}",
            f"language: {self.language}",  # auto=跟随系统 / zh_CN / en_US
            "",
        ]
        return '\n'.join(lines)


def write_default_config():
    """写入默认配置文件（首次安装时调用）"""
    cfg = Config.get()
    cfg.config_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = cfg.config_dir / "config.yaml"
    if yaml_path.exists():
        return
    with open(yaml_path, 'w', encoding='utf-8') as f:
        f.write(cfg.dump())
    print(f"✓ 已生成默认配置: {yaml_path}")


if __name__ == '__main__':
    # 调试入口
    cfg = Config.get()
    print("当前配置:")
    print(cfg.dump())
