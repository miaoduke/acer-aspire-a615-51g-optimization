"""
plugins/hwp_dynamic_boost.py — Intel HWP Dynamic Boost 控制 plugin

W6 实施: 在场景切换时按 profile 设置 hwp_dynamic_boost
  性能场景（ac-perf / bat-perf）→ enable
  省电场景（bat-save / ac-quiet）→ disable
  其他场景 → 继承（不动）

P0-2: sudo 缓存过期时静默（不刷屏）
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


class HwpDynamicBoostPlugin(Plugin):
    name = "hwp_dynamic_boost"
    version = "1.0"
    # P0-2: sudo 失败时静默（避免刷新刷屏）
    _silent_on_no_auth = True

    # Intel HWP 路径
    HWP_PATH = "/sys/devices/system/cpu/cpufreq/boost"

    def _init(self, ctx: PluginContext):
        ctx.log("hwp_dynamic_boost plugin ready")

    def _apply(self, ctx: PluginContext):
        scene_name = ctx.results.get('scene_name', '')

        enable_scenes = ('ac-perf', 'bat-perf')
        if scene_name in enable_scenes:
            value = "1"
        elif scene_name:
            value = "0"
        else:
            return

        rc, out, err = ctx.run(
            ["sudo", "-n", "bash", "-c", f"echo {value} > {self.HWP_PATH}"]
        )
        ctx.set_result('hwp_boost', value)
        # P0-2: sudo 失败且 _silent_on_no_auth=True → 完全静默
        if rc != 0 and "需要密码" in err:
            if not getattr(self, '_silent_on_no_auth', False):
                ctx.log(f"hwp_dynamic_boost: 需要 sudo 授权（忽略）")

    def _undo(self, ctx: PluginContext):
        ctx.run(["sudo", "-n", "bash", "-c", f"echo 0 > {self.HWP_PATH}"])
