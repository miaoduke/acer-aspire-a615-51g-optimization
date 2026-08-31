#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ui_docs.py — 说明文档页：控制台完整使用手册
职责：提供控制台功能详解、核心概念、生态清单、安全规则、故障排查
"""
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class DocumentationPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(12)
        self.set_margin_end(12)

        # --- 目录导航栏 ---
        nav_box = Gtk.Box(spacing=6)
        nav_label = Gtk.Label(label="目录:", xalign=0)
        nav_label.get_style_context().add_class("section-title")
        nav_box.pack_start(nav_label, False, False, 0)

        toc_items = [
            ("overview", "概述"),
            ("pages", "页面功能"),
            ("concepts", "核心概念"),
            ("ecosystem", "生态清单"),
            ("safety", "安全规则"),
            ("troubleshoot", "故障排查"),
            ("crossmachine", "跨平台"),
            ("changelog", "更新日志"),
        ]
        self._anchors = {}
        for key, label in toc_items:
            btn = Gtk.Button(label=label)
            btn.get_style_context().add_class("flat")
            btn.set_size_request(-1, 28)
            btn.connect("clicked", lambda _b, k=key: self._scroll_to(k))
            nav_box.pack_start(btn, False, False, 0)
            self._anchors[key] = None  # 占位

        self.pack_start(nav_box, False, False, 4)

        # --- 内容区域 ---
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        sections = [
            ("overview", self._build_overview),
            ("pages", self._build_pages),
            ("concepts", self._build_concepts),
            ("ecosystem", self._build_ecosystem),
            ("safety", self._build_safety),
            ("troubleshoot", self._build_troubleshoot),
            ("crossmachine", self._build_crossmachine),
            ("changelog", self._build_changelog),
        ]

        for key, builder in sections:
            box = builder()
            self._anchors[key] = box
            content.pack_start(box, False, False, 0)

        sw.add(content)
        self.pack_start(sw, True, True, 0)

        self.show_all()

    # ---------- 导航 ----------
    def _scroll_to(self, key):
        """滚动到指定章节"""
        widget = self._anchors.get(key)
        if widget:
            alloc = widget.get_allocation()
            sw = self.get_children()[-1]  # ScrolledWindow
            sw.get_vadjustment().set_value(alloc.y)

    # ---------- 样式辅助 ----------
    @staticmethod
    def _title(text):
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.get_style_context().add_class("section-title")
        return lbl

    @staticmethod
    def _subtitle(text):
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.get_style_context().add_class("dim-text")
        return lbl

    @staticmethod
    def _h1(text):
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.set_margin_top(16)
        lbl.set_margin_bottom(6)
        lbl.get_style_context().add_class("section-title")
        return lbl

    @staticmethod
    def _h2(text):
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.set_margin_top(10)
        lbl.set_margin_bottom(4)
        lbl.get_style_context().add_class("dim-text")
        return lbl

    @staticmethod
    def _p(text, wrap=True):
        lbl = Gtk.Label(label=text, xalign=0, wrap=wrap, selectable=True)
        lbl.set_line_wrap(True)
        return lbl

    @staticmethod
    def _bullet(text):
        lbl = Gtk.Label(label=f"  • {text}", xalign=0, wrap=True, selectable=True)
        lbl.set_line_wrap(True)
        return lbl

    @staticmethod
    def _code(text):
        lbl = Gtk.Label(label=f"    {text}", xalign=0, selectable=True)
        lbl.get_style_context().add_class("mono-text")
        return lbl

    @staticmethod
    def _sep():
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(8)
        sep.set_margin_bottom(8)
        return sep

    # ================================================================
    # 章节构建
    # ================================================================

    def _build_overview(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(12)
        box.pack_start(self._h1("一、系统控制台概述"), False, False, 0)
        box.pack_start(self._p(
            "系统控制台是一款专为 Acer Aspire A615-51G（i5-8250U + MX150）"
            "设计的笔记本电源与性能管理工具。基于 Python 3 + GTK3 构建，"
            "通过六个功能页面提供全方位的硬件监控、电源场景切换、电池保养、"
            "高级调优、系统维护和说明文档。"), False, False, 4)
        box.pack_start(self._p(
            "控制台采用「科学优化」理念：所有优化决策基于实测数据和权威文档，"
            "严格遵循死机史铁律（不碰 EC、不用 stress-ng、不动风扇），"
            "保证系统稳定性的前提下最大化续航和性能。"), False, False, 4)
        box.pack_start(self._h2("设计原则"), False, False, 0)
        box.pack_start(self._bullet("轻量：内存占用 < 60MB，CPU < 2%（前台采样）"), False, False, 0)
        box.pack_start(self._bullet("安全：所有操作需用户手动确认，自动操作仅限 AC/DC 场景切换"), False, False, 0)
        box.pack_start(self._bullet("科学：优化决策基于实测数据，不凭经验猜测"), False, False, 0)
        box.pack_start(self._bullet("可逆：所有系统改动均可通过 snapshot 回退"), False, False, 0)
        box.pack_start(self._sep(), False, False, 0)
        return box

    def _build_pages(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(4)
        box.pack_start(self._h1("二、页面功能详解"), False, False, 0)

        # 总览
        box.pack_start(self._h2("1. 总览页（Dashboard）"), False, False, 0)
        box.pack_start(self._p(
            "实时硬件状态仪表盘，每秒刷新。展示 CPU/内存/GPU/电池 四大状态卡片，"
            "下方为 CPU 频率历史曲线（最近 120 点）、电池电量/温度双轴曲线、"
            "GPU 利用率趋势。右侧面板显示每核柱条、内存使用条、"
            "网络收发速率、磁盘 IO。"), False, False, 4)
        box.pack_start(self._bullet("CPU 状态卡：显示当前频率、温度、限流状态（绿=正常，红=热降频，黄=功耗墙）"), False, False, 0)
        box.pack_start(self._bullet("电池状态卡：显示电量%、功率、充电阶段（CC恒流/CV恒压/满电/放电）"), False, False, 0)
        box.pack_start(self._bullet("历史曲线：自动缩放 Y 轴，鼠标悬停显示数据点数值"), False, False, 0)
        box.pack_start(self._sep(), False, False, 0)

        # 电源场景
        box.pack_start(self._h2("2. 电源场景页（Scenes）"), False, False, 0)
        box.pack_start(self._p(
            "六个预设电源场景的一键切换界面。每个场景定义了 CPU 频率范围、"
            "Governor、EPP、PL1 功耗墙、GPU 频率等参数组合。"
            "支持 M3 极致省电（物理快捷键触发）、GPU 独显/集显切换。"), False, False, 4)
        box.pack_start(self._p("场景参数一览："), False, False, 4)
        box.pack_start(self._code("ac-perf  : 1.8-3.4GHz | powersave | performance | PL1=25W | GPU=1100MHz"), False, False, 0)
        box.pack_start(self._code("ac-bal   : 1.4-3.0GHz | powersave | balance_perf | PL1=20W | GPU=900MHz"), False, False, 0)
        box.pack_start(self._code("ac-quiet : 1.0-2.0GHz | powersave | power | PL1=15W | GPU=700MHz"), False, False, 0)
        box.pack_start(self._code("bat-save : 0.8-1.5GHz | powersave | power | PL1=10W | GPU=400MHz"), False, False, 0)
        box.pack_start(self._code("bat-bal  : 0.8-2.0GHz | powersave | balance_performance | PL1=15W | GPU=600MHz"), False, False, 0)
        box.pack_start(self._code("bat-max  : 0.8-2.5GHz | powersave | performance | PL1=20W | GPU=800MHz"), False, False, 0)
        box.pack_start(self._p(
            "AC/DC 自动切换：插入电源自动切 ac-perf，拔出自动切 bat-save。"
            "由 acdc-profile 服务实现（3秒轮询检测）。"), False, False, 4)
        box.pack_start(self._bullet("GPU 切换：独显↔集显，切换时自动暂停/恢复 Xorg 进程"), False, False, 0)
        box.pack_start(self._bullet("场景配置：可自定义各场景参数，保存到 ~/.config/system-console/default_scene"), False, False, 0)
        box.pack_start(self._sep(), False, False, 0)

        # 电池保养
        box.pack_start(self._h2("3. 电池保养页（Battery）"), False, False, 0)
        box.pack_start(self._p(
            "电池科学分析与保养管理。提供七维分析引擎（容量衰减、温度敏感度、"
            "充电行为、等效循环、使用模式、健康趋势、异常检测），"
            "配合实时温度/功率曲线和充电阈值协议。"), False, False, 4)
        box.pack_start(self._bullet("电池状态卡：电量、电压、功率、健康度（实测容量/设计容量）、CC/CV 阶段"), False, False, 0)
        box.pack_start(self._bullet("温度历史：最近 120 个温度数据点，自适应缩放"), False, False, 0)
        box.pack_start(self._bullet("浮充检测：监控充满后的微电流补电行为"), False, False, 0)
        box.pack_start(self._bullet("健康趋势：每次放电记录等效循环次数（累计放电量/设计容量）"), False, False, 0)
        box.pack_start(self._bullet("使用统计：今日/本周/本月累计使用时间、平均功率"), False, False, 0)
        box.pack_start(self._bullet("七维分析：容量、温度、充电、循环、使用、趋势、异常——自动计算评分"), False, False, 0)
        box.pack_start(self._sep(), False, False, 0)

        # 高级控制
        box.pack_start(self._h2("4. 高级控制页（Advanced）"), False, False, 0)
        box.pack_start(self._p(
            "硬件参数精细调控界面，分为三大板块："), False, False, 4)
        box.pack_start(self._h2("4a. CPU 参数"), False, False, 0)
        box.pack_start(self._bullet("Governor：powersave/performance schedutil——CPU 频率调度策略"), False, False, 0)
        box.pack_start(self._bullet("EPP：performance/balance_performance/balance_power/power——能效偏好"), False, False, 0)
        box.pack_start(self._bullet("Turbo Boost：开启/关闭——影响最高频率和功耗"), False, False, 0)
        box.pack_start(self._bullet("C-state 深度：max_cstate=1~10——CPU 空闲深度，影响唤醒延迟"), False, False, 0)
        box.pack_start(self._bullet("Undervolt：CPU/GPU/Cache 核心电压降——降低功耗和温度（MSR 0x150）"), False, False, 0)
        box.pack_start(self._bullet("PL1/PL2：持续/峰值功耗墙——控制 CPU 最大功耗"), False, False, 0)
        box.pack_start(self._h2("4b. GPU 参数"), False, False, 0)
        box.pack_start(self._bullet("独显/集显切换：NVIDIA MX150 ↔ Intel UHD 620"), False, False, 0)
        box.pack_start(self._bullet("PowerMizer：高性能/自适应/最佳省电——GPU 性能档位"), False, False, 0)
        box.pack_start(self._bullet("GPU 频率：400-1100MHz 手动设定"), False, False, 0)
        box.pack_start(self._h2("4c. 热管理与周边"), False, False, 0)
        box.pack_start(self._bullet("Thermal Guard：温度阈值联动 PL1 限制（≥85°C→15W，≤75°C→恢复）"), False, False, 0)
        box.pack_start(self._bullet("亮度：直接写入 /sys/class/backlight/"), False, False, 0)
        box.pack_start(self._bullet("触摸板/键盘背光：libinput 启用/禁用"), False, False, 0)
        box.pack_start(self._bullet("WMI 模块状态：acer-wmi-battery 加载检测"), False, False, 0)
        box.pack_start(self._sep(), False, False, 0)

        # 系统维护
        box.pack_start(self._h2("5. 系统维护页（Maintenance）"), False, False, 0)
        box.pack_start(self._p(
            "系统健康监测与诊断维护。包含优化栈服务状态、内核变动检测、"
            "MCE 硬件错误记录、性能日志回看、应用功耗排名。"), False, False, 4)
        box.pack_start(self._bullet("服务状态：显示 acdc-profile、thermal-guard、undervolt 等服务运行状态"), False, False, 0)
        box.pack_start(self._bullet("内核变动检测：17 项自动检查 + 一键修复（内核版本、GRUB、initramfs、模块等）"), False, False, 0)
        box.pack_start(self._bullet("MCE 检测：读取 /var/log/mcelog 或 rasdaemon 硬件错误记录"), False, False, 0)
        box.pack_start(self._bullet("性能日志：查看 perf 目录下的 TSV 日志，支持时间范围筛选"), False, False, 0)
        box.pack_start(self._bullet("应用功耗排名：基于 cgroup 的进程级功耗估算"), False, False, 0)
        box.pack_start(self._sep(), False, False, 0)

        # 说明文档
        box.pack_start(self._h2("6. 说明文档页（Documentation）"), False, False, 0)
        box.pack_start(self._p(
            "即本页。提供控制台的完整使用手册，包括功能详解、核心概念解释、"
            "生态清单、安全规则、故障排查指南。"), False, False, 4)
        box.pack_start(self._sep(), False, False, 0)
        return box

    def _build_concepts(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(4)
        box.pack_start(self._h1("三、核心概念解释"), False, False, 0)

        box.pack_start(self._h2("CPU 频率调度"), False, False, 0)
        box.pack_start(self._p(
            "Linux 内核通过 Governor（调度器）控制 CPU 频率。powersave 倾向低频省电，"
            "performance 倾向高频响应。EPP（Energy Performance Preference）在 Governor "
            "基础上进一步微调能效偏好：performance=全力输出，power=极致省电，"
            "balance_* = 中间档。场景系统通过组合 Governor + EPP + 频率范围 + PL1 "
            "实现六种预设功耗档位。"), False, False, 4)

        box.pack_start(self._h2("Undervolt（降压）"), False, False, 0)
        box.pack_start(self._p(
            "通过 MSR 0x150 寄存器降低 CPU 核心/缓存/GPU 的工作电压。电压降低 → "
            "功耗以电压平方关系下降 → 温度降低 → 可维持更高频率更久。"
            "本机实测 -50mV 稳定运行（-100mV 曾死机），MSR 0x150 未被 BIOS 锁定。"
            "每次 suspend/resume 后需重新应用（undervolt-resume.service）。"), False, False, 4)

        box.pack_start(self._h2("PL1 / PL2 功耗墙"), False, False, 0)
        box.pack_start(self._p(
            "PL1（Package Level 1）= 持续功耗上限，PL2 = 短时峰值上限。"
            "本机默认 PL1=25W，场景系统按需调整（bat-save=10W，ac-perf=25W）。"
            "thermal-guard 在温度过高时自动降低 PL1 以降温。"), False, False, 4)

        box.pack_start(self._h2("C-state 深度"), False, False, 0)
        box.pack_start(self._p(
            "CPU 空闲时进入的休眠深度。C0=工作，C1=停核时钟，C6=深度休眠（功耗最低）。"
            "深度越大省电越多，但唤醒延迟越长。本机 GRUB 设置 max_cstate=4 "
            "（禁用 C8），原因：Kaby Lake-R 深度 C-state 在本机 BIOS 下"
            "会导致随机唤醒黑屏/死机。"), False, False, 4)

        box.pack_start(self._h2("AC/DC 自动切换"), False, False, 0)
        box.pack_start(self._p(
            "acdc-profile 服务每 3 秒检测 AC 电源状态，拔插电源时自动切换场景。"
            "插电→ac-perf（极致性能），拔电→bat-save（省电续航）。"
            "切换时同步调整 CPU/GPU/PL1/EPP 参数，并通过 libnotify 通知用户。"), False, False, 4)

        box.pack_start(self._h2("Thermal Guard（温度守卫）"), False, False, 0)
        box.pack_start(self._p(
            "后台守护进程，每 5 秒读取 CPU 温度。当温度 ≥ 85°C 时，"
            "自动将 PL1 限制到 15W 以降低发热；温度回落到 ≤ 75°C 时恢复原 PL1。"
            "提供被动散热安全网，防止热降频抖动。"), False, False, 4)

        box.pack_start(self._h2("Undervolt（降压）"), False, False, 0)
        box.pack_start(self._p(
            "通过 MSR 0x150 寄存器调整 CPU 核心电压。降低电压可以减少功耗和发热，"
            "同时保持频率不变。本机 BIOS 未锁定 MSR 0x150，允许安全降压。"
            "当前设置 -50mV（三域：core/uncore/gpu），由 undervolt.service 统一管理。"
            "suspend/resume 后需重新应用（undervolt-resume.service）。"), False, False, 4)

        box.pack_start(self._h2("等效循环次数"), False, False, 0)
        box.pack_start(self._p(
            "电池寿命以「完整充放电循环」计量。本控制台使用「累计放电量 / 设计容量」"
            "计算等效循环：每次放电记录放电量，累加后除以设计容量（48,944 mWh）。"
            "例如累计放电 48,944 mWh = 1 次等效循环。"), False, False, 4)

        box.pack_start(self._h2("Governor / EPP"), False, False, 0)
        box.pack_start(self._p(
            "Governor 是 CPU 频率调度策略：powersave（倾向低频省电）、performance（倾向高频响应）。"
            "EPP（Energy Performance Preference）是更细粒度的能效偏好："
            "performance（全力输出）、balance_performance（偏性能）、"
            "balance_power（偏省电）、power（极致省电）。"
            "场景系统通过组合 Governor + EPP + 频率范围来实现不同的性能/功耗档位。"), False, False, 4)

        box.pack_start(self._h2("C-State 深度"), False, False, 0)
        box.pack_start(self._p(
            "CPU 空闲时进入的低功耗状态。C0=活跃，C1=停核时钟，C6=深度休眠。"
            "C-state 越深省电越多，但唤醒延迟越长。"
            "本机限制为 max_cstate=4（禁止 C8/C10），因为 Kaby Lake-R "
            "在深度 C-state 下存在唤醒后 BIOS 重置问题。"), False, False, 4)

        box.pack_start(self._h2("Thermal Guard（温度守卫）"), False, False, 0)
        box.pack_start(self._p(
            "后台守护进程，每 5 秒读取 CPU 温度，根据阈值自动调整 PL1 功耗墙："
            "≥85°C → PL1=15W（压功耗降温），≤75°C → 恢复原 PL1。"
            "提供被动散热安全网，防止温度过高触发硬件热降频导致的性能抖动。"), False, False, 4)

        box.pack_start(self._h2("WMI 模块"), False, False, 0)
        box.pack_start(self._p(
            "acer-wmi-battery 是重新编译的内核模块，提供对 Acer 笔记本 WMI "
            "接口的访问。用于电池充电阈值、EC 配置读取等功能。"
            "从 snapshot 0818 恢复后已按当前内核 7.0.0-28 重新编译并加载。"), False, False, 4)

        box.pack_start(self._h2("zswap + Shrinker"), False, False, 0)
        box.pack_start(self._p(
            "zswap 是 Linux 内核的压缩交换缓存。当内存不足时，不直接写磁盘，"
            "而是将匿名页压缩后存入内存中的 zswap pool，减少慢速磁盘 IO。"
            "shrinker_enabled 允许 zswap 主动回收冷页，进一步优化内存使用效率。"
            "本机 GRUB 已启用 zswap.enabled=1 + zswap.shrinker_enabled=1。"), False, False, 4)
        box.pack_start(self._sep(), False, False, 0)
        return box

    def _build_ecosystem(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(4)
        box.pack_start(self._h1("四、优化生态清单（26 项已实现）"), False, False, 0)
        box.pack_start(self._p(
            "以下为本机已实现并通过验证的优化措施。每项标注实现方式和当前状态。"), False, False, 4)

        items = [
            ("[已实现] AC/DC 场景自动切换", "acdc-profile 服务，3秒轮询，6场景自动切换"),
            ("[已实现] Undervolt 降压 -50mV", "MSR 0x150，三域（core/uncore/gpu），resume 钩子"),
            ("[已实现] C-State 深度限制", "GRUB max_cstate=4，防止 KBL-R 唤醒死机"),
            ("[已实现] PL1/PL2 功耗墙", "开机 25W/25W 钳位，场景按需调整"),
            ("[已实现] Thermal Guard 温度守卫", "≥85°C→PL1=15W，≤75°C→恢复"),
            ("[已实现] GPU 独显/集显切换", "场景联动 + 手动切换，PowerMizer 控制"),
            ("[已实现] Turbo Boost 控制", "turbo-guard 双守护 + 场景联动"),
            ("[已实现] zswap + Shrinker", "GRUB 启用，压缩交换缓存"),
            ("[已实现] Kernel Guard 内核守卫", "17项检查 + 一键修复"),
            ("[已实现] WMI 模块", "acer-wmi-battery 按 7.0.0-28 重编译"),
            ("[已实现] smartd 硬盘监控", "SMART 健康检测，温度告警"),
            ("[已实现] rasdaemon MCE", "硬件错误记录（MCE/EDAC）"),
            ("[已实现] 电池等效循环追踪", "battery_stats.py，JSON 持久化"),
            ("[已实现] 电池七维分析引擎", "battery_analytics.py，容量/温度/充电/循环/使用/趋势/异常"),
            ("[已实现] 性能+功耗日志", "perf_logger.py，30秒采样，7天保留"),
            ("[已实现] 应用功耗排名", "app_power.py，cgroup 级进程功耗估算"),
            ("[已实现] 高负载告警", "load_advisor.py，电池场景高负载通知"),
            ("[已实现] 温度/节流/低电通知", "notification.py，libnotify，含冷却期"),
            ("[已实现] Timeshift 快照管理", "snapshot.sh，GUI 一键创建/查看/备注"),
            ("[已实现] WS1 同步", "sync_to_ws1.sh，rsync 排除 opencode_data"),
            ("[已实现] 会话导出", "export_session.py，MD + 图片打包"),
            ("[已实现] 备份脚本", "00_保存会话与日志.sh，一键备份会话记录"),
            ("[已实现] 场景配置备份", "场景快照与重建脚本"),
            ("[已实现] 硬件探测", "hardware_probe.py，自动发现硬件能力"),
            ("[已实现] 跨平台适配测试", "adapt_test.sh，兼容性报告生成"),
            ("[已实现] 知识库", "data/knowledge/，经验文档与待办规划"),
        ]
        for name, desc in items:
            box.pack_start(self._bullet(f"{name} — {desc}"), False, False, 0)

        box.pack_start(self._h2("已放弃项（15 项，有实锤证据）"), False, False, 0)
        abandoned = [
            "PSR（Panel Self Refresh）—— Kaby Lake-R 唤醒后屏幕冻结（fdo#112159）",
            "FBC（Frame Buffer Compression）—— BOE 面板不支持",
            "刷新率调节 —— EDID 锁定 60Hz",
            "LCD 节能模式 —— 实测黑/白屏功耗差 ±0.04W（噪声水平）",
            "PWM 频率调整 —— VBT 硬编码，无法修改",
            "充电阈值 Linux 侧 —— 固件 WMI 不支持",
            "风扇手动控制 —— EC 直接读写导致死机（#4）",
            "Stress-ng 压力测试 —— 导致死机（#2/#3）",
            "BD PROCHOT 写入 —— MSR 风险",
            "PL2 窗口调整 —— 测试 -13% 负效果",
            "Turbo Override MSR 0x1A0 —— HWP 模式下无效",
            "M3 物理快捷键 —— 硬件不支持",
            "Panel Replay —— 需要 Gen12+ GPU",
            "动画节电 —— 测试仅节省 0.1W（噪声水平）",
            "LCD 黑白屏省电 —— 实测无显著差异",
        ]
        for item in abandoned:
            box.pack_start(self._bullet(f"✗ {item}"), False, False, 0)

        box.pack_start(self._h2("待做项（监测中/待实现）"), False, False, 0)
        todo = [
            "夜间模式（Night Light）—— Phase 1 规划",
            "屏幕闪烁观察期 —— Phase 0 进行中（C-state=4 + csd-backlight-helper 修复验证）",
            "undervolt 步进到 -60mV —— 需 7 天稳定 -50mV 后推进",
            "snapshot 验证方法 —— Phase 1 规划",
            "cross-machine portability —— hardware_probe + adapt_test 已实现，待实际验证",
        ]
        for item in todo:
            box.pack_start(self._bullet(f"△ {item}"), False, False, 0)

        box.pack_start(self._sep(), False, False, 0)
        return box

    def _build_safety(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(4)
        box.pack_start(self._h1("五、安全规则与死机史铁律"), False, False, 0)
        box.pack_start(self._p(
            "本机有明确的死机历史记录。以下铁律是经过实测验证的安全边界，"
            "任何优化操作不得违反："), False, False, 4)

        box.pack_start(self._h2("死机史记录"), False, False, 0)
        box.pack_start(self._bullet("#1 — C-state 深度（C8/C10）导致唤醒后 BIOS 重置 → 已修复（max_cstate=4）"), False, False, 0)
        box.pack_start(self._bullet("#2 — stress-ng 压力测试导致系统死机 → 已放弃压力测试"), False, False, 0)
        box.pack_start(self._bullet("#3 — Undervolt -100mV 导致不稳定 → 已回退到 -50mV"), False, False, 0)
        box.pack_start(self._bullet("#4 — 风扇手动控制（EC 直接读写）导致死机 → 已放弃风扇控制"), False, False, 0)

        box.pack_start(self._h2("铁律清单"), False, False, 0)
        box.pack_start(self._bullet("不碰 EC（Embedded Controller）—— 不直接读写 EC 寄存器"), False, False, 0)
        box.pack_start(self._bullet("不用 stress-ng —— 不进行压力测试"), False, False, 0)
        box.pack_start(self._bullet("不动风扇 —— 不尝试手动控制风扇转速"), False, False, 0)
        box.pack_start(self._bullet("MSR 限制 —— 仅允许 undervolt（0x150）和 turbo-guard（0x1A0 读），禁止其他 MSR 写入"), False, False, 0)
        box.pack_start(self._bullet("C-state 观察期 —— 任何 C-state 变更后需观察 48 小时"), False, False, 0)
        box.pack_start(self._bullet("Undervolt 步进 —— 每次调整 10mV，稳定 7 天后方可继续"), False, False, 0)
        box.pack_start(self._bullet("Snapshot 优先 —— 任何系统改动前先创建快照"), False, False, 0)

        box.pack_start(self._h2("当前安全状态"), False, False, 0)
        box.pack_start(self._bullet("C-state: max_cstate=4 ✓（C8 已禁用）"), False, False, 0)
        box.pack_start(self._bullet("Undervolt: -50mV ✓（安全范围）"), False, False, 0)
        box.pack_start(self._bullet("Fan: 无手动控制 ✓"), False, False, 0)
        box.pack_start(self._bullet("Stress: 无压力测试 ✓"), False, False, 0)
        box.pack_start(self._bullet("Snapshot: 0817（基线）+ 0822_110321（当前恢复点）"), False, False, 0)
        box.pack_start(self._sep(), False, False, 0)
        return box

    def _build_troubleshoot(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(4)
        box.pack_start(self._h1("六、故障排查指南"), False, False, 0)

        box.pack_start(self._h2("屏幕闪烁"), False, False, 0)
        box.pack_start(self._p(
            "已知问题：Cinnamon csd-backlight-helper 在亮度调节时可能产生高频振荡"
            "（200+ 次/8秒写入亮度）。当前缓解措施："), False, False, 4)
        box.pack_start(self._bullet("C-state 回退到 max_cstate=4（禁用 C8，减少唤醒抖动）"), False, False, 0)
        box.pack_start(self._bullet("csd-backlight-helper 已被禁用（需确认是否被 snapshot 恢复）"), False, False, 0)
        box.pack_start(self._bullet("观察期进行中（约 20 小时），监控闪烁是否复发"), False, False, 0)

        box.pack_start(self._h2("Undervolt 失效"), False, False, 0)
        box.pack_start(self._p(
            "Undervolt 值在 suspend/resume 后可能丢失。解决："), False, False, 4)
        box.pack_start(self._bullet("确认 undervolt-resume.service 已启用（systemctl is-enabled undervolt-resume）"), False, False, 0)
        box.pack_start(self._bullet("手动重新应用：sudo undervolt --core -50 --cache -50 --gpu -50"), False, False, 0)

        box.pack_start(self._h2("场景切换失败"), False, False, 0)
        box.pack_start(self._p(
            "acdc-profile 服务异常时："), False, False, 4)
        box.pack_start(self._bullet("检查日志：journalctl -u acdc-profile -n 50"), False, False, 0)
        box.pack_start(self._bullet("重启服务：sudo systemctl restart acdc-profile"), False, False, 0)
        box.pack_start(self._bullet("手动切换：python3 控制台 → 电源场景页 → 点击场景按钮"), False, False, 0)

        box.pack_start(self._h2("GPU 切换卡死"), False, False, 0)
        box.pack_start(self._p(
            "独显↔集显切换时可能短暂黑屏（1-2秒正常）。如果超过 5 秒："), False, False, 4)
        box.pack_start(self._bullet("检查 Xorg 日志：grep EE ~/.local/share/xorg/Xorg.0.log"), False, False, 0)
        box.pack_start(self._bullet("强制恢复：Ctrl+Alt+F2 → 登录 → sudo systemctl restart lightdm"), False, False, 0)

        box.pack_start(self._h2("温度过高"), False, False, 0)
        box.pack_start(self._p(
            "thermal-guard 应自动降低 PL1。如果温度持续 >90°C："), False, False, 0)
        box.pack_start(self._bullet("检查 thermal-guard 日志：cat /var/log/thermal-guard.log"), False, False, 0)
        box.pack_start(self._bullet("手动降频：echo 15000000 | sudo tee /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw"), False, False, 0)
        box.pack_start(self._bullet("清理风扇灰尘（物理维护）"), False, False, 0)

        box.pack_start(self._h2("Kernel Guard 报警"), False, False, 0)
        box.pack_start(self._p(
            "Kernel Guard 检测到内核变动后："), False, False, 4)
        box.pack_start(self._bullet("查看详情：系统维护页 → 内核变动检测 → 查看报告"), False, False, 0)
        box.pack_start(self._bullet("一键修复：系统维护页 → 一键修复按钮"), False, False, 0)
        box.pack_start(self._bullet("命令行：sudo ~/桌面/系统控制台/backend/kernel_guard.sh check/repair"), False, False, 0)

        box.pack_start(self._h2("回退到快照"), False, False, 0)
        box.pack_start(self._p(
            "如果系统出现严重问题，可回退到已知良好的快照："), False, False, 4)
        box.pack_start(self._bullet("查看快照：sudo timeshift --list"), False, False, 0)
        box.pack_start(self._bullet("创建当前快照：sudo timeshift --create --comments 'before rollback'"), False, False, 0)
        box.pack_start(self._bullet("回退：sudo timeshift --restore --snapshot '0822_110321'"), False, False, 0)
        box.pack_start(self._sep(), False, False, 0)
        return box

    def _build_crossmachine(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(4)
        box.pack_start(self._h1("七、跨平台与可移植性"), False, False, 0)

        box.pack_start(self._h2("双系统架构"), False, False, 0)
        box.pack_start(self._p(
            "本项目支持 Linux（GTK3）和 Windows（C#/WinForms）双平台。"
            "共享文档和方案在「共享」目录，各平台实现独立。"), False, False, 4)

        box.pack_start(self._h2("Linux 控制台"), False, False, 0)
        box.pack_start(self._bullet("技术栈：Python 3 + GTK3，零额外依赖"), False, False, 0)
        box.pack_start(self._bullet("数据采集：/sys 文件系统 + shell 命令 + MSR 寄存器"), False, False, 0)
        box.pack_start(self._bullet("功能：26 项优化生态，5 页 GUI"), False, False, 0)
        box.pack_start(self._bullet("当前版本：v1.0（2026-08-22）"), False, False, 0)

        box.pack_start(self._h2("Windows 控制台"), False, False, 0)
        box.pack_start(self._bullet("技术栈：C# + WinForms，.NET Framework 4.8（系统自带）"), False, False, 0)
        box.pack_start(self._bullet("数据采集：PerformanceCounter + WMI + P/Invoke"), False, False, 0)
        box.pack_start(self._bullet("功能：6 页 GUI（总览/电源/调优/进程/系统/维护）"), False, False, 0)
        box.pack_start(self._bullet("已实现：93 项能力（监控 24 + 电源 7 + 调优 9 + EC-WMI 4 + 进程 8 + 维护 9 + UI 13 + 电池 4 + 其他 15）"), False, False, 0)
        box.pack_start(self._bullet("当前版本：v6.6（2026-08-27）"), False, False, 0)

        box.pack_start(self._h2("硬件探测"), False, False, 0)
        box.pack_start(self._p(
            "hardware_probe.py 自动探测当前机器的硬件能力：DRM 显卡、电池接口、"
            "温度传感器、RAPL 功耗域。生成能力矩阵，指导场景系统自适应。"
            "adapt_test.sh 生成兼容性报告，列出可用/不可用功能。"), False, False, 4)

        box.pack_start(self._h2("跨机器部署清单"), False, False, 0)
        box.pack_start(self._bullet("检查 BIOS：MSR 是否锁定、C-state 支持、EC 接口类型"), False, False, 0)
        box.pack_start(self._bullet("运行 hardware_probe.py：自动发现硬件能力"), False, False, 0)
        box.pack_start(self._bullet("运行 adapt_test.sh：生成兼容性报告"), False, False, 0)
        box.pack_start(self._bullet("逐项验证：undervolt（MSR 0x150）、C-state（max_cstate）、thermal-guard（温度读取）"), False, False, 0)
        box.pack_start(self._bullet("参考知识库：data/knowledge/README.md（经验文档与待办规划）"), False, False, 4)
        box.pack_start(self._sep(), False, False, 0)
        return box

    def _build_changelog(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(4)
        box.pack_start(self._h1("八、更新日志"), False, False, 0)

        entries = [
            ("2026-08-27", "本次更新", [
                "新增说明文档页（本页）",
                "修复 csd-backlight-helper 闪烁振荡（禁用 helper + C-state=4 回退）",
                "修复 MSR 读取批量 sudo（性能优化）",
                "修复 battery_stats 标签匹配（battery/batt）",
                "修复 ui_advanced 被删除方法引用（迁移到 maintenance 页）",
                "修复 perf_logger _on_draw_charge 方法缺失（snapshot 恢复后）",
                "新增 undervolt-resume.service（suspend/resume 重新应用）",
                "清除残留 intel-undervolt.service 单元文件（-100mV 安全隐患）",
            ]),
            ("2026-08-25", "电源优化打包三分类重组", [
                "WS1 目录重组为 Win/Linux/共享 三分类",
                "新增 09A Windows 生态全景文档（93 项能力）",
                "新增 10 电源模式科学性审计（180 项设置验证）",
                "新增 17-19 三篇审计报告（功能 100% PASS）",
                "Windows 控制台升级到 v6.6",
                "文件空间回收 93.6%（2.75 GB → 176 MB）",
            ]),
            ("2026-08-22", "当前恢复点", [
                "创建 Timeshift 快照 0822_110321",
                "修复 console_full_test.py（34/34 PASS）",
                "新增 battery_analytics.py 七维分析引擎",
                "新增 hardware_probe.py 硬件探测",
                "新增 adapt_test.sh 跨平台适配测试",
                "修复控制台三个 bug（曲线归一化/电源卡/通知文本）",
            ]),
            ("2026-08-18", "死机调查与修复", [
                "调查 C-state 深度导致死机（#1）",
                "GRUB 设置 max_cstate=4",
                "创建 Timeshift 快照 0817（基线）",
                "恢复 undervolt 到 -50mV（-100mV 死机 #3）",
            ]),
        ]

        for date, title, changes in entries:
            box.pack_start(self._h2(f"{date} — {title}"), False, False, 0)
            for change in changes:
                box.pack_start(self._bullet(change), False, False, 0)

        box.pack_start(self._sep(), False, False, 0)
        return box
