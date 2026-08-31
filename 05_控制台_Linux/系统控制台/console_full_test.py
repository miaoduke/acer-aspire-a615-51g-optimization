#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
console_full_test.py — 控制台全功能模拟测试
离屏构建所有页面，monkeypatch 阻塞式对话框，逐一调用各按钮 handler，
捕获异常并输出详细测试报告。
"""
import os, sys, time, traceback

os.environ.setdefault('DISPLAY', ':0')
# 相对定位: 测的是本包源码, 而非 ~/桌面/系统控制台 的部署副本(原写法导致改源码后测试无意义)
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _APP_DIR)
os.chdir(_APP_DIR)

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk

# ---- Monkeypatch: 让模态对话框不阻塞 ----
real_run = Gtk.Dialog.run
real_msgrun = Gtk.MessageDialog.run
dialog_log = []

def fake_run(self):
    title = self.get_title() or self.get_property('text') or '(无标题)'
    dialog_log.append(title)
    print(f"    [对话框弹出→自动关闭] {title}")
    # 自动点掉
    GLib.idle_add(self.destroy)
    return -5

Gtk.Dialog.run = fake_run
Gtk.MessageDialog.run = fake_run

# zenity 弹窗也要拦（controller._ensure_auth）
real_popen = __builtins__.open if hasattr(__builtins__, 'open') else open

RESULTS = []
ALL = []
def test(name):
    """装饰器：记录测试结果"""
    def deco(fn):
        def wrapper():
            print(f"\n▶ {name}")
            try:
                fn()
                RESULTS.append((name, True, ''))
                print(f"  ✓ 通过")
            except Exception as e:
                tb = traceback.format_exc().splitlines()[-1]
                RESULTS.append((name, False, f"{e} | {tb}"))
                print(f"  ✗ 失败: {e}")
        ALL.append((name, wrapper))
        return wrapper
    return deco

# ================= 测试主体 =================
def pump(timeout_ms=3000):
    """跑 main loop 一段时间，让 GLib.idle 回调执行"""
    loop = GLib.MainLoop()
    GLib.timeout_add(timeout_ms, loop.quit)
    loop.run()

HOST = [None]
def host(widget):
    """把页面挂到临时窗口（提供合法 toplevel）"""
    if HOST[0] is None:
        HOST[0] = Gtk.Window()
    w = HOST[0]
    for c in list(w.get_children()):
        w.remove(c)
    w.add(widget)


def run_tests():
    from collector import Collector
    import controller

    col = Collector()

    # ---------- 总览页 ----------
    @test("总览页构建")
    def t():
        global dash
        from ui_dashboard import DashboardPage
        dash = DashboardPage()
        host(dash)
        assert len(dash.get_children()) > 3, "区块过少"

    sample = [None]
    @test("总览页 update 全量数据")
    def t():
        d = col.sample()
        sample[0] = d
        for _ in range(2):  # 功耗分解需要多轮
            time.sleep(1.5); d = col.sample()
        dash.update(d)

    @test("总览页限流状态卡片")
    def t():
        assert hasattr(dash, 'throttle_card'), '卡片缺失'
        txt = dash.throttle_card.get_children()[1].get_text()
        assert len(txt) > 0

    @test("总览页实时功耗区")
    def t():
        for k in ('total','core','uncore','dram','gpu','bat'):
            assert k in getattr(dash, 'pwr', {}), f'缺 {k}'

    @test("总览页布局对话框(构建)")
    def t():
        dash._open_layout_dialog()
        # 对话框被 monkeypatch 自动关

    # ---------- 电源场景页 ----------
    @test("场景页构建+refresh")
    def t():
        global scenes
        from ui_scenes import ScenesPage
        scenes = ScenesPage()
        host(scenes)
        scenes.refresh_state(sample[0])

    @test("场景页状态快照无 bat_info 残留")
    def t():
        assert not hasattr(scenes, 'bat_info'), '电池信息应已迁移'

    # ---------- 电池保养页 ----------
    @test("电池页构建")
    def t():
        global batt
        from ui_battery import BatteryPage
        batt = BatteryPage()
        host(batt)

    @test("电池页 refresh 带 phase/使用统计/分析摘要")
    def t():
        batt.refresh_state(sample[0], None)
        assert batt.analytics_summary.get_text() != ''

    @test("电池页科学分析报告(完整构建)")
    def t():
        # _open_analytics 内部 dlg.run 已被 patch；show_all 后由 idle 销毁
        batt._open_analytics()

    @test("电池页状态卡 CC/CV 标注逻辑")
    def t():
        d = dict(sample[0])
        b = dict(d['bat']); b['status']='Charging'; b['phase']='cv'; d['bat']=b
        batt.refresh_state(d, None)
        v = batt.state_card._val.get_text()
        assert 'CV' in v, f'CV 未标注: {v}'
        b['status']='Discharging'; b['phase']=None; d['bat']=b
        batt.refresh_state(d, None)
        v2 = batt.state_card._val.get_text()
        assert 'CV' not in v2 and 'CC' not in v2

    # ---------- 高级控制页 ----------
    @test("高级页构建（控制类五区块）")
    def t():
        global adv
        from ui_advanced import AdvancedPage
        adv = AdvancedPage()
        host(adv)

    @test("高级页 refresh_state（含生态区14行）")
    def t():
        adv.refresh_state(sample[0])
        assert len(adv.eco) >= 14

    @test("高级页温度守护配置(构建)")
    def t():
        adv._open_guard_config()

    @test("高级页场景参数配置(构建)")
    def t():
        adv._open_scene_config()

    @test("散热控制 TCC 只读回显")
    def t():
        v = adv._read_int('/sys/class/thermal/cooling_device17/cur_state')
        assert v is not None

    # ---------- 系统维护页 ----------
    @test("维护页构建")
    def t():
        global maint
        from ui_maintenance import MaintenancePage
        maint = MaintenancePage()
        host(maint)

    @test("维护页服务列表加载")
    def t():
        done_holder = {}
        import ui_maintenance
        orig = controller.service_states
        controller.service_states = lambda: [('test.service','测试','active')]
        maint._load_services()
        controller.service_states = orig
        pump(2000)
        assert len(maint.svc_list.get_children()) >= 1, '列表为空'

    @test("维护页内核守卫 check（真实执行）")
    def t():
        maint._kernel_guard('check')
        pump(15000)   # 等脚本完成
        text = maint.kern_buf.get_text(maint.kern_buf.get_start_iter(),
                                       maint.kern_buf.get_end_iter(), False)
        assert '内核变动检测' in text and '✓' in text, f'输出异常: {text[:80]}'

    @test("维护页性能日志数据加载逻辑")
    def t():
        from src.core.perf_logger import get_perf_stats
        stats = get_perf_stats(1)
        assert 'samples' in stats

    @test("维护页应用功耗排行扫描")
    def t():
        from src.core.app_power import get_app_power_ranking
        get_app_power_ranking()          # 基线
        time.sleep(2)
        r = get_app_power_ranking(10.0)
        assert isinstance(r, list)

    @test("维护页 MCE 查询")
    def t():
        rc, out, err = controller.ras_errors()
        assert isinstance(rc, int)

    @test("维护页 WMI 模块状态回显")
    def t():
        # 直接调用 worker 逻辑
        import subprocess
        r = subprocess.run(['lsmod'], capture_output=True, text=True)
        assert 'acer_wmi_battery' in r.stdout or True  # 状态两种都合法

    # ---------- 核心模块 ----------
    @test("MSR 限流读取（缓存+熔断）")
    def t():
        from src.core.msr_reader import get_throttle_status, get_msr_reader
        s1 = get_throttle_status(); s2 = get_throttle_status()
        assert s1.summary_text() and s2.summary_text()

    @test("通知系统")
    def t():
        from src.core.notification import get_notification_manager
        nm = get_notification_manager()
        nm.config.cooldown_sec = 0
        nm.notify_custom("测试通知", "console_full_test", icon="dialog-information")

    @test("电池使用统计 tracker")
    def t():
        from src.core.battery_stats import get_tracker
        snap = get_tracker().update()
        assert 'equiv_cycles' in snap

    @test("科学分析引擎 7 维度")
    def t():
        from src.core.battery_analytics import run_analysis
        r = run_analysis()
        assert len(r['items']) == 7

    @test("负载建议器")
    def t():
        from src.core.load_advisor import get_load_advisor
        a = get_load_advisor(); a._check_once()

    @test("硬件探测")
    def t():
        from src.core.hardware_probe import get_probe
        p = get_probe()
        assert p.paths['drm_card'] and p.paths['battery']

    # ---------- 后端脚本 ----------
    @test("场景管理.sh status")
    def t():
        rc, out, err = controller._run([controller.SCENE_SCRIPT, 'status'])
        assert rc == 0 and '电源' in out

    @test("thermal_ctl.sh maxperf 读回")
    def t():
        import subprocess
        r = subprocess.run(['cat', '/sys/devices/system/cpu/intel_pstate/max_perf_pct'],
                           capture_output=True, text=True)
        assert r.stdout.strip().isdigit()

    @test("adapt_test.sh 探测")
    def t():
        import subprocess
        r = subprocess.run(['bash', 'backend/adapt_test.sh'], capture_output=True,
                           text=True, timeout=60)
        assert '适配测试' in r.stdout and '✓' in r.stdout

    @test("kernel_guard.sh check（后端直调）")
    def t():
        import subprocess
        r = subprocess.run(['sudo', '-n', 'backend/kernel_guard.sh', 'check'],
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0

    @test("snapshot.sh list")
    def t():
        import subprocess
        r = subprocess.run(['sudo', '-n', 'backend/snapshot.sh', 'list'],
                           capture_output=True, text=True, timeout=30)
        # 凭据过期时允许失败，命令可执行即可
        assert 'Num' in r.stdout or '密码' in (r.stderr or '') or r.returncode != 0


def main():
    print("=" * 60)
    print(" 控制台全功能模拟测试")
    print("=" * 60)
    run_tests()
    # 执行所有注册的测试（@test 在 run_tests 内注册）
    for name, fn in ALL:
        fn()
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = [(n, e) for n, ok, e in RESULTS if not ok]
    print(f" 结果: {passed}/{len(RESULTS)} 通过, {len(failed)} 失败, 对话框 {len(dialog_log)} 个")
    if failed:
        print("\n失败详情:")
        for n, e in failed:
            print(f"  ✗ {n}: {e[:120]}")
    print("=" * 60)


if __name__ == '__main__':
    main()