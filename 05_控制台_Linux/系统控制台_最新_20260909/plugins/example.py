"""
plugins/example.py — 用户自定义 plugin 示例

复制到 ~/.config/system-console/plugins/ 即可启用
"""
import os
import sys
try:
    from src.core.plugin import Plugin, PluginContext
except (ImportError, ValueError):
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(plugin_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from src.core.plugin import Plugin, PluginContext


class ExamplePlugin(Plugin):
    """用户自定义 plugin 模板"""
    name = "example"
    version = "1.0"

    def _init(self, ctx: PluginContext):
        ctx.log(f"[{self.name}] 初始化完成")

    def _apply(self, ctx: PluginContext):
        """场景切换时调用"""
        ctx.log(f"[{self.name}] 切换场景")
        # 你的逻辑：写 sysfs / 执行命令 / 修改配置
        # ctx.run(["bash", "-c", "echo 1 > /tmp/example.flag"])
        ctx.set_result('example_applied', True)

    def _undo(self, ctx: PluginContext):
        """切回时调用（可选）"""
        ctx.log(f"[{self.name}] 撤销")
