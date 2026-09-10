"""
plugins/thermal_ctl.py — 散热/功耗统一控制 plugin

对应 controller.thermal() 8 个子命令
"""
import os
import sys
# 多种 import 路径尝试（兼容性）
try:
    from src.core.plugin import Plugin, PluginContext
except (ImportError, ValueError):
    # 作为脚本独立运行时
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(plugin_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from src.core.plugin import Plugin, PluginContext


class ThermalCtlPlugin(Plugin):
    """thermal_ctl.sh 8 子命令 wrapper"""
    name = "thermal_ctl"
    version = "1.0"

    # 子命令 → 行为映射
    COMMANDS = ["fan_boost", "tcc", "pclamp", "maxperf", "usb", "wifi", "pl", "camera"]

    def _init(self, ctx: PluginContext):
        # 实际应用由 controller.thermal() 处理
        ctx.log(f"thermal_ctl plugin ready")

    def _apply(self, ctx: PluginContext):
        # 从 profile 获取参数
        sub_command = ctx.results.get('sub_command', 'pl')
        arg = ctx.results.get('arg', 'on' if sub_command in ('fan_boost', 'maxperf', 'usb', 'wifi', 'camera') else '0')

        # 委托给 controller
        import controller
        rc, out, err = controller.thermal(sub_command, arg)
        ctx.set_result('rc', rc)
        ctx.set_result('out', out)
        if err:
            ctx.set_result('err', err)
