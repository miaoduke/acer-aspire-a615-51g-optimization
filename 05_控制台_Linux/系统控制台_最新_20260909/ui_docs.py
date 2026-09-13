#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ui_docs.py — 说明文档页：控制台完整使用手册
职责：提供控制台功能详解、核心概念、生态清单、安全规则、故障排查
"""
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

import os


# ---------------- 2026-09-08: 文档正文双语（en locale 显示英文版）----------------
# DOC_EN: 文档正文 zh→en 对照表（独立于主 i18n 字典——长文档文案不入 T() 字典
# 是科学决策：避免主字典膨胀；zh 原文为键，en locale 时 _D() 查表，未收录回退原文）
DOC_EN = {

        # --- 多行拼接段落（整段键，2026-09-08 补 27 条）---
        'ui_docs.py — 说明文档页：控制台完整使用手册\n职责：提供控制台功能详解、核心概念、生态清单、安全规则、故障排查\n': "ui_docs.py — Documentation page: the console's complete user manual\nProvides feature walkthroughs, core concepts, ecosystem list, safety rules, troubleshooting\n",
        '系统控制台是一款专为 Acer Aspire A615-51G（i5-8250U + MX150）设计的笔记本电源与性能管理工具。基于 Python 3 + GTK3 构建，通过七个功能页面提供全方位的硬件监控、电源场景切换、电池保养、高级调优、进程详情、系统维护和说明文档。': 'System Console is a laptop power & performance manager built for the Acer Aspire A615-51G (i5-8250U + MX150).Built with Python 3 + GTK3,it provides comprehensive hardware monitoring, power-scene switching, battery care,advanced tuning, process details, system maintenance and documentation across seven pages.',
        '控制台采用「科学优化」理念：所有优化决策基于实测数据和权威文档，严格遵循死机史铁律（不碰 EC、不用 stress-ng、不动风扇），保证系统稳定性的前提下最大化续航和性能。': 'The console follows a science-first approach: every decision is based on measured data and authoritative docs,and strictly obeys the crash-history iron rules (no EC access, no stress-ng, no fan control),maximizing battery life and performance without sacrificing stability.',
        '实时硬件状态仪表盘，每秒刷新。展示 CPU/内存/GPU/电池 四大状态卡片，下方为 CPU 频率历史曲线（最近 120 点）、电池电量/温度双轴曲线、GPU 利用率趋势。右侧面板显示每核柱条、内存使用条、网络收发速率、磁盘 IO。': 'A live hardware dashboard refreshing every second: CPU/memory/GPU/battery status cards,CPU frequency history (last 120 points), battery level/temperature dual-axis curves,and GPU utilization trend. The side panel shows per-core bars, memory usage,network rates and disk I/O.',
        '六个预设电源场景的一键切换界面。每个场景定义了 CPU 频率范围、Governor、EPP、PL1 功耗墙、GPU 频率等参数组合。支持 M3 极致省电（物理快捷键触发）、GPU 独显/集显切换。': 'One-click switching across six preset power scenes. Each scene defines CPU frequency range,Governor, EPP, PL1 power cap, GPU frequency and more.Includes M3 ultra power-save (hardware hotkey) and dGPU/iGPU switching.',
        'AC/DC 自动切换：插入电源自动切 ac-perf，拔出自动切 bat-save。由 acdc-profile 服务实现（3秒轮询检测）。': 'AC/DC auto-switch: plug in → ac-perf, unplug → bat-save.Implemented by the acdc-profile service (3s polling).',
        '电池科学分析与保养管理。提供七维分析引擎（容量衰减、温度敏感度、充电行为、等效循环、使用模式、健康趋势、异常检测），配合实时温度/功率曲线和充电阈值协议。': 'Scientific battery analysis and care: a 7-dimension engine (capacity fade, temperature sensitivity,charging behavior, equivalent cycles, usage patterns, health trend, anomaly detection),plus live temperature/power curves and charge-threshold protocols.',
        '系统健康监测与诊断维护。包含优化栈服务状态、内核变动检测、MCE 硬件错误记录、性能日志回看、应用功耗排名。': 'System health monitoring and diagnostics: service states, kernel-change detection,MCE hardware errors, performance log review, app power ranking.',
        '按 PSS（比例集大小，精确共享内存）排序的 Top 50 进程监控（2026-09-02 新增）。支持搜索过滤、双击查看详情、右键 kill/renice 操作。': 'Top 50 processes ranked by PSS (proportional set size, accurate shared memory) — added 2026-09-02.Search filtering, double-click details, right-click kill/renice.',
        '即本页。提供控制台的完整使用手册，包括功能详解、核心概念解释、生态清单、安全规则、故障排查指南。': 'This page: the complete user manual — feature walkthroughs, core concepts,ecosystem list, safety rules, troubleshooting.',
        'Linux 内核通过 Governor（调度器）控制 CPU 频率。powersave 倾向低频省电，performance 倾向高频响应。EPP（Energy Performance Preference）在 Governor 基础上进一步微调能效偏好：performance=全力输出，power=极致省电，balance_* = 中间档。场景系统通过组合 Governor + EPP + 频率范围 + PL1 实现六种预设功耗档位。': 'The kernel controls CPU frequency via Governors. powersave biases toward low frequency,performance toward high frequency. EPP (Energy Performance Preference) fine-tunesthe balance further: performance=max output, power=max saving,balance_* = middle ground. Scenes combine Governor + EPP + frequency range + PL1into six preset power profiles.',
        '通过 MSR 0x150 寄存器降低 CPU 核心/缓存/GPU 的工作电压。电压降低 → 功耗以电压平方关系下降 → 温度降低 → 可维持更高频率更久。本机实测 -100mV 稳定运行（实测 -99.61mV，量化误差 0.39mV），2026-09-07 通过 D7 观察期验收：零死机、零 MCE、保护机制零误触发（详见下方死机史记录说明）。MSR 0x150 未被 BIOS 锁定。三重保护：msr_deadman（95°C 自动回退）、uv-safeguard（异常关机回退）、uv-daily-check（每日巡检告警）。每次 suspend/resume 后需重新应用（undervolt-resume.service）。': 'Lowers CPU core/cache/GPU voltage via MSR 0x150. Lower voltage →power drops with the square of voltage → lower temperature → sustained boost longer.-100mV measured stable on this machine (actual -99.61mV, 0.39mV quantization error); passed the D7 observation window on 2026-09-07:zero crashes, zero MCE, zero false protection triggers (see crash history below). MSR 0x150 is not BIOS-locked.Triple protection: msr_deadman (auto-revert at 95°C), uv-safeguard (abnormal-shutdown revert), uv-daily-check (daily patrol with alerts).Re-applied after each suspend/resume (undervolt-resume.service).',
        'PL1（Package Level 1）= 持续功耗上限，PL2 = 短时峰值上限。本机默认 PL1=25W，场景系统按需调整（bat-save=10W，ac-perf=25W）。thermal-guard 在温度过高时自动降低 PL1 以降温。': 'PL1 (Package Level 1) = sustained power cap; PL2 = short-term peak cap.Default PL1=25W here; scenes adjust as needed (bat-save=10W, ac-perf=25W).thermal-guard lowers PL1 automatically when the CPU runs hot.',
        'CPU 空闲时进入的休眠深度。C0=工作，C1=停核时钟，C6=深度休眠（功耗最低）。深度越大省电越多，但唤醒延迟越长。本机 GRUB 设置 max_cstate=4 （禁用 C8），原因：Kaby Lake-R 深度 C-state 在本机 BIOS 下会导致随机唤醒黑屏/死机。': 'How deeply the CPU sleeps when idle. C0=working, C1=clock stop, C6=deep sleep (lowest power).Deeper saves more power but wakes slower. GRUB sets max_cstate=4(C8 disabled) because Kaby Lake-R deep C-states under this BIOScaused random wake freezes/crashes.',
        'acdc-profile 服务每 3 秒检测 AC 电源状态，拔插电源时自动切换场景。插电→ac-perf（极致性能），拔电→bat-save（省电续航）。切换时同步调整 CPU/GPU/PL1/EPP 参数，并通过 libnotify 通知用户。': 'The acdc-profile service polls AC state every 3s and switches scenes on changes.Plugged → ac-perf (performance); unplugged → bat-save (battery life).CPU/GPU/PL1/EPP are adjusted together; a libnotify notification confirms the switch.',
        '后台守护进程，每 5 秒读取 CPU 温度。当温度 ≥ 85°C 时，自动将 PL1 限制到 15W 以降低发热；温度回落到 ≤ 75°C 时恢复原 PL1。提供被动散热安全网，防止热降频抖动。': 'A daemon reading CPU temperature every 5s. At ≥85°Cit caps PL1 at 15W; at ≤75°C the original PL1 is restored.A passive-cooling safety net against thermal-throttle oscillation.',
        '通过 MSR 0x150 寄存器调整 CPU 核心电压。降低电压可以减少功耗和发热，同时保持频率不变。本机 BIOS 未锁定 MSR 0x150，允许安全降压。当前设置 -100mV（三域：core/uncore/gpu），由 undervolt.service 统一管理，实测 -99.61mV（量化误差 0.39mV）。D7 观察期验收通过（2026-09-07，16/16 项证据达标）。suspend/resume 后需重新应用（undervolt-resume.service）。': 'Adjusts CPU core voltage via MSR 0x150. Lower voltage reduces power and heatat the same frequency. This BIOS leaves MSR 0x150 unlocked.Current setting -100mV (core/uncore/gpu) managed by undervolt.service;measured -99.61mV (0.39mV quantization). D7 acceptance passed (2026-09-07, 16/16 criteria).Re-applied after suspend/resume (undervolt-resume.service).',
        '电池寿命以「完整充放电循环」计量。本控制台使用「累计放电量 / 设计容量」计算等效循环：每次放电记录放电量，累加后除以设计容量（48,944 mWh）。例如累计放电 48,944 mWh = 1 次等效循环。': 'Battery life is measured in full charge-discharge cycles. This console computes cycles as cumulative discharge / design capacity(48,944 mWh on this pack).E.g. 48,944 mWh cumulative discharge = 1 equivalent cycle.',
        'Governor 是 CPU 频率调度策略：powersave（倾向低频省电）、performance（倾向高频响应）。EPP（Energy Performance Preference）是更细粒度的能效偏好：performance（全力输出）、balance_performance（偏性能）、balance_power（偏省电）、power（极致省电）。场景系统通过组合 Governor + EPP + 频率范围来实现不同的性能/功耗档位。': 'Governor = CPU frequency policy: powersave (low-freq, saving) vs performance (high-freq, responsive).EPP (Energy Performance Preference) is a finer-grained preference:performance (max output), balance_performance (performance-biased),balance_power (saving-biased), power (max saving).Scenes combine Governor + EPP + frequency ranges to build power profiles.',
        'CPU 空闲时进入的低功耗状态。C0=活跃，C1=停核时钟，C6=深度休眠。C-state 越深省电越多，但唤醒延迟越长。本机限制为 max_cstate=4（禁止 C8/C10），因为 Kaby Lake-R 在深度 C-state 下存在唤醒后 BIOS 重置问题。': 'Low-power states the CPU enters when idle. C0=active, C1=clock stop, C6=deep sleep.Deeper C-states save more power but wake slower.This machine caps at max_cstate=4 (C8/C10 disabled) because Kaby Lake-Rhad a BIOS-reset-after-wake issue in deep C-states.',
        '后台守护进程，每 5 秒读取 CPU 温度，根据阈值自动调整 PL1 功耗墙：≥85°C → PL1=15W（压功耗降温），≤75°C → 恢复原 PL1。提供被动散热安全网，防止温度过高触发硬件热降频导致的性能抖动。': 'A daemon reading CPU temperature every 5s and auto-adjusting PL1:≥85°C → PL1=15W (throttle to cool); ≤75°C → restore.A passive-cooling safety net preventing thermal-throttle jitter.',
        'acer-wmi-battery 是重新编译的内核模块，提供对 Acer 笔记本 WMI 接口的访问。用于电池充电阈值、EC 配置读取等功能。从 snapshot 0818 恢复后已按当前内核 7.0.0-28 重新编译并加载。': 'acer-wmi-battery is a rebuilt kernel module exposing the Acer WMIinterface — battery charge thresholds and EC config reads.Rebuilt and loaded for kernel 7.0.0-28 after restoring snapshot 0818.',
        'zswap 是 Linux 内核的压缩交换缓存。当内存不足时，不直接写磁盘，而是将匿名页压缩后存入内存中的 zswap pool，减少慢速磁盘 IO。shrinker_enabled 允许 zswap 主动回收冷页，进一步优化内存使用效率。本机 GRUB 已启用 zswap.enabled=1 + zswap.shrinker_enabled=1。': "zswap is the kernel's compressed swap cache. Under memory pressure, pages arecompressed into an in-memory pool instead of hitting slow disk I/O.shrinker_enabled lets zswap proactively evict cold pages for better memory efficiency.GRUB enables zswap.enabled=1 + zswap.shrinker_enabled=1 here.",
        '本机有明确的死机历史记录。以下铁律是经过实测验证的安全边界，任何优化操作不得违反：': 'This machine has a documented crash history. The iron rules below aremeasured safety boundaries — no optimization may violate them:',
        '已知问题：Cinnamon csd-backlight-helper 在亮度调节时可能产生高频振荡（200+ 次/8秒写入亮度）。当前缓解措施：': "Known issue: Cinnamon's csd-backlight-helper may oscillate during brightness changes(200+ writes per 8s). Current mitigations:",
        '本项目支持 Linux（GTK3）和 Windows（C#/WinForms）双平台。共享文档和方案在「共享」目录，各平台实现独立。': 'This project ships on Linux (GTK3) and Windows (C#/WinForms).Shared docs live in "Shared"; implementations are independent.',
        'hardware_probe.py 自动探测当前机器的硬件能力：DRM 显卡、电池接口、温度传感器、RAPL 功耗域。生成能力矩阵，指导场景系统自适应。adapt_test.sh 生成兼容性报告，列出可用/不可用功能。': 'hardware_probe.py auto-discovers capabilities: DRM GPUs, battery interfaces,thermal sensors, RAPL domains — a capability matrix driving scene adaptation.adapt_test.sh generates compatibility reports (available/unavailable).',
    'ui_docs.py — 说明文档页：控制台完整使用手册\n职责：提供控制台功能详解、核心概念、生态清单、安全规则、故障排查\n': "ui_docs.py — Documentation page: the console's complete user manual\nProvides feature walkthroughs, core concepts, ecosystem list, safety rules, troubleshooting\n",
    '目录:': 'Contents:',
    '概述': 'Overview',
    '页面功能': 'Pages',
    '核心概念': 'Core Concepts',
    '生态清单': 'Ecosystem',
    '安全规则': 'Safety Rules',
    '故障排查': 'Troubleshooting',
    '跨平台': 'Cross-platform',
    '更新日志': 'Changelog',
    '滚动到指定章节': 'Scroll to a section',
    '一、系统控制台概述': '1. System Console Overview',
    '系统控制台是一款专为 Acer Aspire A615-51G（i5-8250U + MX150）': 'System Console is a laptop power & performance manager built for the Acer Aspire A615-51G (i5-8250U + MX150).',
    '设计的笔记本电源与性能管理工具。基于 Python 3 + GTK3 构建，': 'Built with Python 3 + GTK3,',
    '通过七个功能页面提供全方位的硬件监控、电源场景切换、电池保养、': 'it provides comprehensive hardware monitoring, power-scene switching, battery care,',
    '高级调优、进程详情、系统维护和说明文档。': 'advanced tuning, process details, system maintenance and documentation across seven pages.',
    '控制台采用「科学优化」理念：所有优化决策基于实测数据和权威文档，': 'The console follows a science-first approach: every decision is based on measured data and authoritative docs,',
    '严格遵循死机史铁律（不碰 EC、不用 stress-ng、不动风扇），': 'and strictly obeys the crash-history iron rules (no EC access, no stress-ng, no fan control),',
    '保证系统稳定性的前提下最大化续航和性能。': 'maximizing battery life and performance without sacrificing stability.',
    '界面语言切换': 'UI Language Switching',
    '系统维护页 → 「界面语言」下拉框 → 选择（自动/中文/English）→ 应用 → 重启控制台生效': 'Maintenance page → "UI language" combo → pick (Auto/中文/English) → Apply → restart the console',
    '托盘图标右键菜单 → 语言 Language → 选择（与维护页等效）': 'Tray icon right-click → Language → pick (equivalent to the maintenance page)',
    '配置文件：~/.config/system-console/config.yaml 的 language 项（auto=跟随系统）': 'Config file: the language key in ~/.config/system-console/config.yaml (auto = follow system)',
    '设计原则': 'Design Principles',
    '轻量：内存占用 < 60MB，CPU < 2%（前台采样）': 'Lightweight: < 60 MB RAM, < 2% CPU (foreground sampling)',
    '安全：所有操作需用户手动确认，自动操作仅限 AC/DC 场景切换': 'Safe: every operation needs explicit confirmation; only AC/DC scene switching is automatic',
    '科学：优化决策基于实测数据，不凭经验猜测': 'Scientific: decisions from measurements, never guesses',
    '可逆：所有系统改动均可通过 snapshot 回退': 'Reversible: every change can be rolled back via snapshots',
    '二、页面功能详解': '2. Page Reference',
    '1. 总览页（Dashboard）': '1. Dashboard',
    '实时硬件状态仪表盘，每秒刷新。展示 CPU/内存/GPU/电池 四大状态卡片，': 'A live hardware dashboard refreshing every second: CPU/memory/GPU/battery status cards,',
    '下方为 CPU 频率历史曲线（最近 120 点）、电池电量/温度双轴曲线、': 'CPU frequency history (last 120 points), battery level/temperature dual-axis curves,',
    'GPU 利用率趋势。右侧面板显示每核柱条、内存使用条、': 'and GPU utilization trend. The side panel shows per-core bars, memory usage,',
    '网络收发速率、磁盘 IO。': 'network rates and disk I/O.',
    'CPU 状态卡：显示当前频率、温度、限流状态（绿=正常，红=热降频，黄=功耗墙）': 'CPU card: frequency, temperature, throttling state (green=OK, red=thermal, yellow=power limit)',
    '电池状态卡：显示电量%、功率、充电阶段（CC恒流/CV恒压/满电/放电）': 'Battery card: level %, power, charge phase (CC constant-current / CV constant-voltage / full / discharging)',
    '历史曲线：自动缩放 Y 轴，鼠标悬停显示数据点数值': 'History curves: auto-scaling Y axis; hover shows point values',
    '2. 电源场景页（Scenes）': '2. Power Scenes',
    '六个预设电源场景的一键切换界面。每个场景定义了 CPU 频率范围、': 'One-click switching across six preset power scenes. Each scene defines CPU frequency range,',
    'Governor、EPP、PL1 功耗墙、GPU 频率等参数组合。': 'Governor, EPP, PL1 power cap, GPU frequency and more.',
    '支持 M3 极致省电（物理快捷键触发）、GPU 独显/集显切换。': 'Includes M3 ultra power-save (hardware hotkey) and dGPU/iGPU switching.',
    '场景参数一览：': 'Scene parameters:',
    'AC/DC 自动切换：插入电源自动切 ac-perf，拔出自动切 bat-save。': 'AC/DC auto-switch: plug in → ac-perf, unplug → bat-save.',
    '由 acdc-profile 服务实现（3秒轮询检测）。': 'Implemented by the acdc-profile service (3s polling).',
    'GPU 切换：独显↔集显，切换时自动暂停/恢复 Xorg 进程': 'GPU switch: dGPU↔iGPU; Xorg is paused/resumed during the switch',
    '场景配置：可自定义各场景参数，保存到 ~/.config/system-console/default_scene': 'Scene config: defaults saved to ~/.config/system-console/default_scene',
    '3. 电池保养页（Battery）': '3. Battery Care',
    '电池科学分析与保养管理。提供七维分析引擎（容量衰减、温度敏感度、': 'Scientific battery analysis and care: a 7-dimension engine (capacity fade, temperature sensitivity,',
    '充电行为、等效循环、使用模式、健康趋势、异常检测），': 'charging behavior, equivalent cycles, usage patterns, health trend, anomaly detection),',
    '配合实时温度/功率曲线和充电阈值协议。': 'plus live temperature/power curves and charge-threshold protocols.',
    '电池状态卡：电量、电压、功率、健康度（实测容量/设计容量）、CC/CV 阶段': 'Battery card: level, voltage, power, health (measured/design capacity), CC/CV phase',
    '温度历史：最近 120 个温度数据点，自适应缩放': 'Temperature history: last 120 points, auto-scaled',
    '浮充检测：监控充满后的微电流补电行为': 'Float-charge detection: monitors trickle top-up after full',
    '健康趋势：每次放电记录等效循环次数（累计放电量/设计容量）': 'Health trend: equivalent cycles recorded per discharge (cumulative discharge / design capacity)',
    '使用统计：今日/本周/本月累计使用时间、平均功率': 'Usage stats: today/week/month runtime and average power',
    '七维分析：容量、温度、充电、循环、使用、趋势、异常——自动计算评分': '7-dimension analysis: capacity, temperature, charging, cycles, usage, trend, anomalies — auto-scored',
    '4. 高级控制页（Advanced）': '4. Advanced Control',
    '硬件参数精细调控界面，分为三大板块：': 'Fine-grained hardware tuning in three panels:',
    '4a. CPU 参数': '4a. CPU Parameters',
    'Governor：powersave/performance schedutil——CPU 频率调度策略': 'Governor: powersave/performance schedutil — CPU frequency policy',
    'EPP：performance/balance_performance/balance_power/power——能效偏好': 'EPP: performance/balance_performance/balance_power/power — energy preference',
    'Turbo Boost：开启/关闭——影响最高频率和功耗': 'Turbo Boost: on/off — affects max frequency and power',
    'C-state 深度：max_cstate=1~10——CPU 空闲深度，影响唤醒延迟': 'C-state depth: max_cstate=1~10 — idle depth, affects wake latency',
    'Undervolt：CPU/GPU/Cache 核心电压降——降低功耗和温度（MSR 0x150）': 'Undervolt: CPU/GPU/cache voltage offset — lowers power & temperature (MSR 0x150)',
    'PL1/PL2：持续/峰值功耗墙——控制 CPU 最大功耗': 'PL1/PL2: sustained/peak power caps — CPU power ceiling',
    '4b. GPU 参数': '4b. GPU Parameters',
    '独显/集显切换：NVIDIA MX150 ↔ Intel UHD 620': 'dGPU/iGPU switch: NVIDIA MX150 ↔ Intel UHD 620',
    'PowerMizer：高性能/自适应/最佳省电——GPU 性能档位': 'PowerMizer: max performance/adaptive/max power saving — GPU profile',
    'GPU 频率：400-1100MHz 手动设定': 'GPU frequency: 400–1100 MHz manual setting',
    '4c. 热管理与周边': '4c. Thermal & Peripherals',
    'Thermal Guard：温度阈值联动 PL1 限制（≥85°C→15W，≤75°C→恢复）': 'Thermal Guard: temp-coupled PL1 limiting (≥85°C→15W, ≤75°C→restore)',
    '亮度：直接写入 /sys/class/backlight/': 'Brightness: writes /sys/class/backlight/ directly',
    '触摸板/键盘背光：libinput 启用/禁用': 'Touchpad/keyboard backlight: enable/disable via libinput',
    'WMI 模块状态：acer-wmi-battery 加载检测': 'WMI module state: acer-wmi-battery load detection',
    '5. 系统维护页（Maintenance）': '5. Maintenance',
    '系统健康监测与诊断维护。包含优化栈服务状态、内核变动检测、': 'System health monitoring and diagnostics: service states, kernel-change detection,',
    'MCE 硬件错误记录、性能日志回看、应用功耗排名。': 'MCE hardware errors, performance log review, app power ranking.',
    '服务状态：显示 acdc-profile、thermal-guard、undervolt 等服务运行状态': 'Service states: acdc-profile, thermal-guard, undervolt etc., plus the safeguard verdict badge',
    '内核变动检测：17 项自动检查 + 一键修复（内核版本、GRUB、initramfs、模块等）': 'Kernel-change detection: 17 automatic checks + one-click repair (kernel version, GRUB, initramfs, modules)',
    'MCE 检测：读取 /var/log/mcelog 或 rasdaemon 硬件错误记录': 'MCE detection: reads rasdaemon records with an authoritative CPU MCE count badge',
    '性能日志：查看 perf 目录下的 TSV 日志，支持时间范围筛选': 'Performance log: TSV logs with time-range filtering and a live latest-sample header',
    '应用功耗排名：基于 cgroup 的进程级功耗估算': 'App power ranking: cgroup-based per-process power estimation',
    '6. 进程详情页（Processes）': '6. Processes',
    '按 PSS（比例集大小，精确共享内存）排序的 Top 50 进程监控（2026-09-02 新增）。': 'Top 50 processes ranked by PSS (proportional set size, accurate shared memory) — added 2026-09-02.',
    '支持搜索过滤、双击查看详情、右键 kill/renice 操作。': 'Search filtering, double-click details, right-click kill/renice.',
    'PSS 排序：比 RSS 更精确地反映真实内存占用（共享页按比例分摊）': 'PSS ranking: truer memory usage than RSS (shared pages split proportionally)',
    '性能优化：两阶段读取（轻扫 top-50 后才读 smaps_rollup）+ 5s PSS 缓存，冷启 <300ms 热刷 <100ms': 'Performance: two-phase reading (smaps_rollup only for top-50) + 5s PSS cache; cold <300ms, warm <100ms',
    '进程操作：右键菜单支持 TERM/KILL/HUP 信号与 renice 优先级调整（需授权）': 'Actions: right-click TERM/KILL/HUP signals and renice priority (requires authorization)',
    '实时刷新：可切换自动刷新（3s）或手动刷新': 'Live refresh: auto (3s) or manual',
    '7. 说明文档页（Documentation）': '7. Documentation',
    '即本页。提供控制台的完整使用手册，包括功能详解、核心概念解释、': 'This page: the complete user manual — feature walkthroughs, core concepts,',
    '生态清单、安全规则、故障排查指南。': 'ecosystem list, safety rules, troubleshooting.',
    '三、核心概念解释': '3. Core Concepts',
    'CPU 频率调度': 'CPU Frequency Scaling',
    'Linux 内核通过 Governor（调度器）控制 CPU 频率。powersave 倾向低频省电，': 'The kernel controls CPU frequency via Governors. powersave biases toward low frequency,',
    'performance 倾向高频响应。EPP（Energy Performance Preference）在 Governor ': 'performance toward high frequency. EPP (Energy Performance Preference) fine-tunes',
    '基础上进一步微调能效偏好：performance=全力输出，power=极致省电，': 'the balance further: performance=max output, power=max saving,',
    'balance_* = 中间档。场景系统通过组合 Governor + EPP + 频率范围 + PL1 ': 'balance_* = middle ground. Scenes combine Governor + EPP + frequency range + PL1',
    '实现六种预设功耗档位。': 'into six preset power profiles.',
    'Undervolt（降压）': 'Undervolt',
    '通过 MSR 0x150 寄存器降低 CPU 核心/缓存/GPU 的工作电压。电压降低 → ': 'Lowers CPU core/cache/GPU voltage via MSR 0x150. Lower voltage →',
    '功耗以电压平方关系下降 → 温度降低 → 可维持更高频率更久。': 'power drops with the square of voltage → lower temperature → sustained boost longer.',
    '本机实测 -100mV 稳定运行（实测 -99.61mV，量化误差 0.39mV），2026-09-07 通过 D7 观察期验收：': '-100mV measured stable on this machine (actual -99.61mV, 0.39mV quantization error); passed the D7 observation window on 2026-09-07:',
    '零死机、零 MCE、保护机制零误触发（详见下方死机史记录说明）。MSR 0x150 未被 BIOS 锁定。': 'zero crashes, zero MCE, zero false protection triggers (see crash history below). MSR 0x150 is not BIOS-locked.',
    '三重保护：msr_deadman（95°C 自动回退）、uv-safeguard（异常关机回退）、uv-daily-check（每日巡检告警）。': 'Triple protection: msr_deadman (auto-revert at 95°C), uv-safeguard (abnormal-shutdown revert), uv-daily-check (daily patrol with alerts).',
    '每次 suspend/resume 后需重新应用（undervolt-resume.service）。': 'Re-applied after each suspend/resume (undervolt-resume.service).',
    'PL1 / PL2 功耗墙': 'PL1 / PL2 Power Caps',
    'PL1（Package Level 1）= 持续功耗上限，PL2 = 短时峰值上限。': 'PL1 (Package Level 1) = sustained power cap; PL2 = short-term peak cap.',
    '本机默认 PL1=25W，场景系统按需调整（bat-save=10W，ac-perf=25W）。': 'Default PL1=25W here; scenes adjust as needed (bat-save=10W, ac-perf=25W).',
    'thermal-guard 在温度过高时自动降低 PL1 以降温。': 'thermal-guard lowers PL1 automatically when the CPU runs hot.',
    'C-state 深度': 'C-state Depth',
    'CPU 空闲时进入的休眠深度。C0=工作，C1=停核时钟，C6=深度休眠（功耗最低）。': 'How deeply the CPU sleeps when idle. C0=working, C1=clock stop, C6=deep sleep (lowest power).',
    '深度越大省电越多，但唤醒延迟越长。本机 GRUB 设置 max_cstate=4 ': 'Deeper saves more power but wakes slower. GRUB sets max_cstate=4',
    '（禁用 C8），原因：Kaby Lake-R 深度 C-state 在本机 BIOS 下': '(C8 disabled) because Kaby Lake-R deep C-states under this BIOS',
    '会导致随机唤醒黑屏/死机。': 'caused random wake freezes/crashes.',
    'AC/DC 自动切换': 'AC/DC Auto-switching',
    'acdc-profile 服务每 3 秒检测 AC 电源状态，拔插电源时自动切换场景。': 'The acdc-profile service polls AC state every 3s and switches scenes on changes.',
    '插电→ac-perf（极致性能），拔电→bat-save（省电续航）。': 'Plugged → ac-perf (performance); unplugged → bat-save (battery life).',
    '切换时同步调整 CPU/GPU/PL1/EPP 参数，并通过 libnotify 通知用户。': 'CPU/GPU/PL1/EPP are adjusted together; a libnotify notification confirms the switch.',
    'Thermal Guard（温度守卫）': 'Thermal Guard',
    '后台守护进程，每 5 秒读取 CPU 温度。当温度 ≥ 85°C 时，': 'A daemon reading CPU temperature every 5s. At ≥85°C',
    '自动将 PL1 限制到 15W 以降低发热；温度回落到 ≤ 75°C 时恢复原 PL1。': 'it caps PL1 at 15W; at ≤75°C the original PL1 is restored.',
    '提供被动散热安全网，防止热降频抖动。': 'A passive-cooling safety net against thermal-throttle oscillation.',
    '通过 MSR 0x150 寄存器调整 CPU 核心电压。降低电压可以减少功耗和发热，': 'Adjusts CPU core voltage via MSR 0x150. Lower voltage reduces power and heat',
    '同时保持频率不变。本机 BIOS 未锁定 MSR 0x150，允许安全降压。': 'at the same frequency. This BIOS leaves MSR 0x150 unlocked.',
    '当前设置 -100mV（三域：core/uncore/gpu），由 undervolt.service 统一管理，': 'Current setting -100mV (core/uncore/gpu) managed by undervolt.service;',
    '实测 -99.61mV（量化误差 0.39mV）。D7 观察期验收通过（2026-09-07，16/16 项证据达标）。': 'measured -99.61mV (0.39mV quantization). D7 acceptance passed (2026-09-07, 16/16 criteria).',
    'suspend/resume 后需重新应用（undervolt-resume.service）。': 'Re-applied after suspend/resume (undervolt-resume.service).',
    '等效循环次数': 'Equivalent Cycles',
    '电池寿命以「完整充放电循环」计量。本控制台使用「累计放电量 / 设计容量」': 'Battery life is measured in full charge-discharge cycles. This console computes cycles as cumulative discharge / design capacity',
    '计算等效循环：每次放电记录放电量，累加后除以设计容量（48,944 mWh）。': '(48,944 mWh on this pack).',
    '例如累计放电 48,944 mWh = 1 次等效循环。': 'E.g. 48,944 mWh cumulative discharge = 1 equivalent cycle.',
    'Governor 是 CPU 频率调度策略：powersave（倾向低频省电）、performance（倾向高频响应）。': 'Governor = CPU frequency policy: powersave (low-freq, saving) vs performance (high-freq, responsive).',
    'EPP（Energy Performance Preference）是更细粒度的能效偏好：': 'EPP (Energy Performance Preference) is a finer-grained preference:',
    'performance（全力输出）、balance_performance（偏性能）、': 'performance (max output), balance_performance (performance-biased),',
    'balance_power（偏省电）、power（极致省电）。': 'balance_power (saving-biased), power (max saving).',
    '场景系统通过组合 Governor + EPP + 频率范围来实现不同的性能/功耗档位。': 'Scenes combine Governor + EPP + frequency ranges to build power profiles.',
    'CPU 空闲时进入的低功耗状态。C0=活跃，C1=停核时钟，C6=深度休眠。': 'Low-power states the CPU enters when idle. C0=active, C1=clock stop, C6=deep sleep.',
    'C-state 越深省电越多，但唤醒延迟越长。': 'Deeper C-states save more power but wake slower.',
    '本机限制为 max_cstate=4（禁止 C8/C10），因为 Kaby Lake-R ': 'This machine caps at max_cstate=4 (C8/C10 disabled) because Kaby Lake-R',
    '在深度 C-state 下存在唤醒后 BIOS 重置问题。': 'had a BIOS-reset-after-wake issue in deep C-states.',
    '后台守护进程，每 5 秒读取 CPU 温度，根据阈值自动调整 PL1 功耗墙：': 'A daemon reading CPU temperature every 5s and auto-adjusting PL1:',
    '≥85°C → PL1=15W（压功耗降温），≤75°C → 恢复原 PL1。': '≥85°C → PL1=15W (throttle to cool); ≤75°C → restore.',
    '提供被动散热安全网，防止温度过高触发硬件热降频导致的性能抖动。': 'A passive-cooling safety net preventing thermal-throttle jitter.',
    'WMI 模块': 'WMI Module',
    'acer-wmi-battery 是重新编译的内核模块，提供对 Acer 笔记本 WMI ': 'acer-wmi-battery is a rebuilt kernel module exposing the Acer WMI',
    '接口的访问。用于电池充电阈值、EC 配置读取等功能。': 'interface — battery charge thresholds and EC config reads.',
    '从 snapshot 0818 恢复后已按当前内核 7.0.0-28 重新编译并加载。': 'Rebuilt and loaded for kernel 7.0.0-28 after restoring snapshot 0818.',
    'zswap 是 Linux 内核的压缩交换缓存。当内存不足时，不直接写磁盘，': "zswap is the kernel's compressed swap cache. Under memory pressure, pages are",
    '而是将匿名页压缩后存入内存中的 zswap pool，减少慢速磁盘 IO。': 'compressed into an in-memory pool instead of hitting slow disk I/O.',
    'shrinker_enabled 允许 zswap 主动回收冷页，进一步优化内存使用效率。': 'shrinker_enabled lets zswap proactively evict cold pages for better memory efficiency.',
    '本机 GRUB 已启用 zswap.enabled=1 + zswap.shrinker_enabled=1。': 'GRUB enables zswap.enabled=1 + zswap.shrinker_enabled=1 here.',
    '四、优化生态清单（26 项已实现）': '4. Optimization Ecosystem (26 items implemented)',
    '以下为本机已实现并通过验证的优化措施。每项标注实现方式和当前状态。': 'Measures implemented and verified on this machine, with implementation and status:',
    '[已实现] AC/DC 场景自动切换': '[Done] AC/DC scene auto-switch',
    'acdc-profile v9，3秒轮询，6场景自动切换，含 GPU GT 频率联动（AC 1100/DC 700MHz，2026-09-07 修复生效）': 'acdc-profile v9, 3s polling, 6 scenes, GPU GT freq coupling (AC 1100/DC 700MHz, fixed 2026-09-07)',
    '[已实现] Undervolt 降压 -100mV': '[Done] Undervolt -100mV',
    'MSR 0x150，三域（core/uncore/gpu），D7 验收通过，三重保护（deadman/safeguard/daily-check）': 'MSR 0x150, three domains (core/uncore/gpu), D7 accepted, triple protection',
    '[已实现] 降压三重保护体系': '[Done] Undervolt triple protection',
    'msr_deadman（95°C 自动回退，30s 巡检）+ uv-safeguard（三级判定 CLEAN/CRASH_REVERT/WATCH）+ uv-daily-check（每日 10:01 巡检告警）': 'msr_deadman (95°C auto-revert, 30s patrol) + uv-safeguard (3-tier verdict) + uv-daily-check (daily 10:01 patrol)',
    '[已实现] C-State 深度限制': '[Done] C-state depth cap',
    'GRUB max_cstate=4，防止 KBL-R 唤醒死机': 'GRUB max_cstate=4 — prevents KBL-R wake crashes',
    '[已实现] PL1/PL2 功耗墙': '[Done] PL1/PL2 power caps',
    '开机 25W/25W 钳位，场景按需调整': '25W/25W clamped at boot; scenes adjust',
    '[已实现] Thermal Guard 温度守卫': '[Done] Thermal Guard',
    '≥85°C→PL1=15W，≤75°C→恢复': '≥85°C→PL1=15W; ≤75°C→restore',
    '[已实现] GPU 独显/集显切换': '[Done] dGPU/iGPU switching',
    '场景联动 + 手动切换，PowerMizer 控制': 'scene-coupled + manual, PowerMizer control',
    '[已实现] Turbo Boost 控制': '[Done] Turbo Boost control',
    'turbo-guard 双守护 + 场景联动': 'turbo-guard dual watchdog + scene coupling',
    '[已实现] zswap + Shrinker': '[Done] zswap + shrinker',
    'GRUB 启用，压缩交换缓存': 'GRUB-enabled compressed swap cache',
    '[已实现] Kernel Guard 内核守卫': '[Done] Kernel Guard',
    '17项检查 + 一键修复': '17 checks + one-click repair',
    '[已实现] WMI 模块': '[Done] WMI module',
    'acer-wmi-battery 按 7.0.0-28 重编译': 'acer-wmi-battery rebuilt for 7.0.0-28',
    '[已实现] smartd 硬盘监控': '[Done] smartd disk monitoring',
    'SMART 健康检测，温度告警': 'SMART health checks with temperature alerts',
    '[已实现] rasdaemon MCE': '[Done] rasdaemon MCE',
    '硬件错误记录（MCE/EDAC）': 'hardware error records (MCE/EDAC)',
    '[已实现] 电池等效循环追踪': '[Done] Battery equivalent-cycle tracking',
    'battery_stats.py，JSON 持久化': 'battery_stats.py, JSON-persisted',
    '[已实现] 电池七维分析引擎': '[Done] 7-dimension battery analytics',
    'battery_analytics.py，容量/温度/充电/循环/使用/趋势/异常': 'battery_analytics.py: capacity/temp/charging/cycles/usage/trend/anomaly',
    '[已实现] 性能+功耗日志': '[Done] Performance + power logging',
    'perf_logger.py，30秒采样，7天保留': 'perf_logger.py, 30s sampling, 7-day retention',
    '[已实现] 应用功耗排名': '[Done] App power ranking',
    'app_power.py，cgroup 级进程功耗估算': 'app_power.py, cgroup-based estimates',
    '[已实现] 高负载告警': '[Done] High-load alerts',
    'load_advisor.py，电池场景高负载通知': 'load_advisor.py, high-load notices on battery',
    '[已实现] 温度/节流/低电通知': '[Done] Temp/throttle/low-battery notifications',
    'notification.py，libnotify，含冷却期': 'notification.py, libnotify, cooldowns built in',
    '[已实现] Timeshift 快照管理': '[Done] Timeshift snapshot management',
    'snapshot.sh，GUI 一键创建/查看/备注': 'snapshot.sh, GUI create/view/comment',
    '[已实现] WS1 同步': '[Done] WS1 sync',
    'sync_to_ws1.sh，rsync 排除 opencode_data': 'sync_to_ws1.sh, rsync excluding opencode_data',
    '[已实现] 会话导出': '[Done] Session export',
    'export_session.py，MD + 图片打包': 'export_session.py, MD + image bundling',
    '[已实现] 备份脚本': '[Done] Backup script',
    '00_保存会话与日志.sh，一键备份会话记录': '00_保存会话与日志.sh, one-click session backup',
    '[已实现] 场景配置备份': '[Done] Scene config backup',
    '场景快照与重建脚本': 'snapshot & rebuild scripts',
    '[已实现] 硬件探测': '[Done] Hardware probe',
    'hardware_probe.py，自动发现硬件能力': 'hardware_probe.py, auto hardware discovery',
    '[已实现] 跨平台适配测试': '[Done] Cross-platform adaptation test',
    'adapt_test.sh，兼容性报告生成': 'adapt_test.sh, compatibility reports',
    '[已实现] 知识库': '[Done] Knowledge base',
    'data/knowledge/，经验文档与待办规划': 'data/knowledge/, docs & planning',
    '已放弃项（15 项，有实锤证据）': 'Abandoned items (15, with hard evidence)',
    'PSR（Panel Self Refresh）—— Kaby Lake-R 唤醒后屏幕冻结（fdo#112159）': 'PSR — screen freeze after wake on KBL-R (fdo#112159)',
    'FBC（Frame Buffer Compression）—— BOE 面板不支持': 'FBC — unsupported by the BOE panel',
    '刷新率调节 —— EDID 锁定 60Hz': 'Refresh-rate control — EDID locks 60Hz',
    'LCD 节能模式 —— 实测黑/白屏功耗差 ±0.04W（噪声水平）': 'LCD power-save mode — ±0.04W difference (noise)',
    'PWM 频率调整 —— VBT 硬编码，无法修改': 'PWM frequency — hardcoded in VBT',
    '充电阈值 Linux 侧 —— 固件 WMI 不支持': 'Linux-side charge threshold — firmware WMI unsupported',
    '风扇手动控制 —— EC 直接读写导致死机（#4）': 'Manual fan control — EC access caused crash (#4)',
    'Stress-ng 压力测试 —— 导致死机（#2/#3）': 'stress-ng stress tests — caused crashes (#2/#3)',
    'BD PROCHOT 写入 —— MSR 风险': 'BD PROCHOT writes — MSR risk',
    'PL2 窗口调整 —— 测试 -13% 负效果': 'PL2 window tuning — tested -13% regression',
    'Turbo Override MSR 0x1A0 —— HWP 模式下无效': 'Turbo override MSR 0x1A0 — ineffective under HWP',
    'M3 物理快捷键 —— 硬件不支持': 'M3 hardware hotkey — unsupported',
    'Panel Replay —— 需要 Gen12+ GPU': 'Panel Replay — needs Gen12+ GPU',
    '动画节电 —— 测试仅节省 0.1W（噪声水平）': 'Animation power saving — 0.1W (noise)',
    'LCD 黑白屏省电 —— 实测无显著差异': 'LCD dark/light theme — no measurable difference',
    '待做项（监测中/待实现）': 'Pending items (monitored/planned)',
    '夜间模式（Night Light）—— Phase 1 规划': 'Night Light — planned for Phase 1',
    'undervolt 更深档位探索 —— -100mV 已验收稳定使用中（如需推进需重新走 7 天观察期流程）': 'Deeper undervolt — -100mV accepted & stable (advancing requires a new 7-day window)',
    'cross-machine portability —— hardware_probe + adapt_test 已实现，待实际验证': 'Cross-machine portability — built, awaiting real-world validation',
    'GitHub 发布 —— 仓库已就绪（v2.0.0 + v2.0.1-accepted 双 tag），待推送凭据': 'GitHub release — repo ready (dual tags), awaiting push credentials',
    '隐形功能 GUI 化 —— 2026-09-07 已完成 A/B 类收编（诊断快照/冲突复查/MCE 计数/自定义方案向导/继承链）': 'Hidden-feature GUI-ization — completed 2026-09-07 (snapshot/conflict recheck/MCE count/wizard/inheritance)',
    '五、安全规则与死机史铁律': '5. Safety Rules & Crash-History Iron Laws',
    '本机有明确的死机历史记录。以下铁律是经过实测验证的安全边界，': 'This machine has a documented crash history. The iron rules below are',
    '任何优化操作不得违反：': 'measured safety boundaries — no optimization may violate them:',
    '死机史记录': 'Crash History',
    '#1 — C-state 深度（C8/C10）导致唤醒后 BIOS 重置 → 已修复（max_cstate=4）': '#1 — deep C-states (C8/C10) caused BIOS reset after wake → fixed (max_cstate=4)',
    '#2 — stress-ng 压力测试导致系统死机 → 已放弃压力测试': '#2 — stress-ng caused crashes → stress testing abandoned',
    '#3 — Undervolt -100mV 导致不稳定（2026-08-18 时点）→ 后经科学验证重启：v2.0 方案配三重保护，2026-09-07 D7 观察期验收通过（零死机/零 MCE/零误触发），现稳定运行于 -100mV（详见更新日志）': '#3 — -100mV unstable (as of 2026-08-18) → scientifically revisited: the v2.0 plan with triple protection passed the D7 window on 2026-09-07 (zero crashes/MCE/false triggers) and now runs stably at -100mV (see changelog)',
    '#4 — 风扇手动控制（EC 直接读写）导致死机 → 已放弃风扇控制': '#4 — manual fan control (direct EC access) caused crashes → abandoned',
    '铁律清单': 'Iron Rules',
    '不碰 EC（Embedded Controller）—— 不直接读写 EC 寄存器': 'Never touch the EC — no direct EC register access',
    '不用 stress-ng —— 不进行压力测试': 'No stress-ng — no stress testing',
    '不动风扇 —— 不尝试手动控制风扇转速': 'No fan control — never adjust fan speed manually',
    'MSR 限制 —— 仅允许 undervolt（0x150）和 turbo-guard（0x1A0 读），禁止其他 MSR 写入': 'MSR restrictions — only undervolt (0x150) and turbo-guard (0x1A0 read); no other MSR writes',
    'C-state 观察期 —— 任何 C-state 变更后需观察 48 小时': 'C-state observation — 48h observation after any C-state change',
    'Undervolt 步进 —— 每次调整 10mV，稳定 7 天后方可继续': 'Undervolt stepping — 10mV steps, 7 stable days before advancing',
    'Snapshot 优先 —— 任何系统改动前先创建快照': 'Snapshot first — always snapshot before system changes',
    '当前安全状态': 'Current Safety Status',
    'C-state: max_cstate=4 ✓（C8 已禁用）': 'C-state: max_cstate=4 ✓ (C8 disabled)',
    'Undervolt: -50mV ✓（安全范围）': 'Undervolt: -100mV ✓ (D7-accepted production value)',
    'Fan: 无手动控制 ✓': 'Fan: no manual control ✓',
    'Stress: 无压力测试 ✓': 'Stress: none ✓',
    'Snapshot: 0817（基线）+ 0822_110321（当前恢复点）': 'Snapshots: 0817 (baseline) + 0822_110321 (current restore point)',
    '六、故障排查指南': '6. Troubleshooting',
    '屏幕闪烁': 'Screen flicker',
    '已知问题：Cinnamon csd-backlight-helper 在亮度调节时可能产生高频振荡': "Known issue: Cinnamon's csd-backlight-helper may oscillate during brightness changes",
    '（200+ 次/8秒写入亮度）。当前缓解措施：': '(200+ writes per 8s). Current mitigations:',
    'C-state 回退到 max_cstate=4（禁用 C8，减少唤醒抖动）': 'C-state rolled back to max_cstate=4 (C8 off, less wake jitter)',
    'csd-backlight-helper 已被禁用（需确认是否被 snapshot 恢复）': "csd-backlight-helper disabled (verify it wasn't restored by a snapshot)",
    '观察期进行中（约 20 小时），监控闪烁是否复发': 'Observation ongoing (~20h) to confirm the fix',
    'Undervolt 失效': 'Undervolt not applying',
    'Undervolt 值在 suspend/resume 后可能丢失。解决：': 'Values may be lost after suspend/resume. Fixes:',
    '确认 undervolt-resume.service 已启用（systemctl is-enabled undervolt-resume）': 'Verify undervolt-resume.service is enabled (systemctl is-enabled undervolt-resume)',
    '手动重新应用：sudo systemctl restart undervolt（推荐，服务内含标准参数）': 'Re-apply manually: sudo systemctl restart undervolt (recommended — standard params inside)',
    '应急回退：sudo undervolt --core -50 --cache -50 --gpu -50（降压不稳时降至安全档）': 'Emergency fallback: sudo undervolt --core -50 --cache -50 --gpu -50 (safe level if unstable)',
    '每日巡检：uv-daily-check 每日 10:01 自动检查，异常会弹通知并写 /var/log/uv_daily_check.alert': 'Daily patrol: uv-daily-check at 10:01 notifies and writes /var/log/uv_daily_check.alert on anomalies',
    '场景切换失败': 'Scene switch fails',
    'acdc-profile 服务异常时：': 'If acdc-profile misbehaves:',
    '检查日志：journalctl -u acdc-profile -n 50': 'Check logs: journalctl -u acdc-profile -n 50',
    '重启服务：sudo systemctl restart acdc-profile': 'Restart: sudo systemctl restart acdc-profile',
    '手动切换：python3 控制台 → 电源场景页 → 点击场景按钮': 'Manual: open the console → Power Scenes → click a scene',
    'GPU 切换卡死': 'GPU switch hangs',
    '独显↔集显切换时可能短暂黑屏（1-2秒正常）。如果超过 5 秒：': 'A brief black screen (1-2s) during switching is normal. If it exceeds 5s:',
    '检查 Xorg 日志：grep EE ~/.local/share/xorg/Xorg.0.log': 'Check Xorg log: grep EE ~/.local/share/xorg/Xorg.0.log',
    '强制恢复：Ctrl+Alt+F2 → 登录 → sudo systemctl restart lightdm': 'Force recovery: Ctrl+Alt+F2 → login → sudo systemctl restart lightdm',
    '温度过高': 'Overheating',
    'thermal-guard 应自动降低 PL1。如果温度持续 >90°C：': 'thermal-guard should cap PL1 automatically. If temps stay >90°C:',
    '检查 thermal-guard 日志：cat /var/log/thermal-guard.log': 'Check its log: cat /var/log/thermal-guard.log',
    '手动降频：echo 15000000 | sudo tee /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw': 'Manual throttle: echo 15000000 | sudo tee /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw',
    '清理风扇灰尘（物理维护）': 'Clean the fan (physical maintenance)',
    'Kernel Guard 报警': 'Kernel Guard alert',
    'Kernel Guard 检测到内核变动后：': 'When Kernel Guard detects kernel changes:',
    '查看详情：系统维护页 → 内核变动检测 → 查看报告': 'Details: Maintenance → kernel-change detection → view report',
    '一键修复：系统维护页 → 一键修复按钮': 'One-click repair: Maintenance → one-click repair',
    '命令行：sudo %s check/repair': 'CLI: sudo %s check/repair',
    '回退到快照': 'Rolling back to a snapshot',
    '如果系统出现严重问题，可回退到已知良好的快照：': 'For serious problems, roll back to a known-good snapshot:',
    '查看快照：sudo timeshift --list': 'List: sudo timeshift --list',
    "创建当前快照：sudo timeshift --create --comments 'before rollback'": "Create one first: sudo timeshift --create --comments 'before rollback'",
    "回退：sudo timeshift --restore --snapshot '0822_110321'": "Restore: sudo timeshift --restore --snapshot '0822_110321'",
    '七、跨平台与可移植性': '7. Cross-platform & Portability',
    '双系统架构': 'Dual-platform architecture',
    '本项目支持 Linux（GTK3）和 Windows（C#/WinForms）双平台。': 'This project ships on Linux (GTK3) and Windows (C#/WinForms).',
    '共享文档和方案在「共享」目录，各平台实现独立。': 'Shared docs live in "Shared"; implementations are independent.',
    'Linux 控制台': 'Linux console',
    '技术栈：Python 3 + GTK3，零额外依赖': 'Stack: Python 3 + GTK3, zero extra dependencies',
    '数据采集：/sys 文件系统 + shell 命令 + MSR 寄存器': 'Collection: /sys + shell + MSRs',
    '功能：26 项优化生态，5 页 GUI': 'Features: 26-item ecosystem, 7-page GUI',
    '当前版本：v1.0（2026-08-22）': 'Version: v2.0.1 (2026-09-08)',
    'Windows 控制台': 'Windows console',
    '技术栈：C# + WinForms，.NET Framework 4.8（系统自带）': 'Stack: C# + WinForms, .NET Framework 4.8 (built-in)',
    '数据采集：PerformanceCounter + WMI + P/Invoke': 'Collection: PerformanceCounter + WMI + P/Invoke',
    '功能：6 页 GUI（总览/电源/调优/进程/系统/维护）': 'Features: 6-page GUI (overview/power/tuning/processes/system/maintenance)',
    '已实现：93 项能力（监控 24 + 电源 7 + 调优 9 + EC-WMI 4 + 进程 8 + 维护 9 + UI 13 + 电池 4 + 其他 15）': '93 capabilities implemented (24 monitoring + 7 power + 9 tuning + 4 EC-WMI + 8 process + 9 maintenance + 13 UI + 4 battery + 15 misc)',
    '当前版本：v6.6（2026-08-27）': 'Version: v6.6 (2026-08-27)',
    '硬件探测': 'Hardware probing',
    'hardware_probe.py 自动探测当前机器的硬件能力：DRM 显卡、电池接口、': 'hardware_probe.py auto-discovers capabilities: DRM GPUs, battery interfaces,',
    '温度传感器、RAPL 功耗域。生成能力矩阵，指导场景系统自适应。': 'thermal sensors, RAPL domains — a capability matrix driving scene adaptation.',
    'adapt_test.sh 生成兼容性报告，列出可用/不可用功能。': 'adapt_test.sh generates compatibility reports (available/unavailable).',
    '跨机器部署清单': 'Cross-machine deployment checklist',
    '检查 BIOS：MSR 是否锁定、C-state 支持、EC 接口类型': 'Check BIOS: MSR locks, C-state support, EC interface type',
    '运行 hardware_probe.py：自动发现硬件能力': 'Run hardware_probe.py: auto-discovery',
    '运行 adapt_test.sh：生成兼容性报告': 'Run adapt_test.sh: compatibility report',
    '逐项验证：undervolt（MSR 0x150）、C-state（max_cstate）、thermal-guard（温度读取）': 'Verify each: undervolt (MSR 0x150), C-state (max_cstate), thermal-guard (temp reads)',
    '参考知识库：data/knowledge/README.md（经验文档与待办规划）': 'Knowledge base: data/knowledge/README.md',
    '八、更新日志': '8. Changelog',
    '语言切换功能（中英双语可用化）': 'Language switching (bilingual enabled)',
    '语言不再只能跟随系统 locale：config.yaml 新增 language 项（auto/zh_CN/en_US）': 'Language no longer follows system locale only: config.yaml gains a language key (auto/zh_CN/en_US)',
    '维护页新增「界面语言」下拉框 + 应用按钮（托盘菜单也有入口）': 'Maintenance page gains a UI-language combo + apply button (tray menu too)',
    '选择后写入配置，重启控制台生效；自动模式跟随系统语言': 'Saved to config; applied on restart; auto follows the system',
    '隐形功能 GUI 化（审计 A/B 类收编）': 'Hidden features brought to the GUI (audit class A/B)',
    '维护页 +2 按钮：📋 一键诊断快照（tlp-stat 风格全景，此前仅 CLI）、🔍 冲突复查（互斥工具+double-sudo 运行期复查）': 'Maintenance +2 buttons: 📋 Diagnostic Snapshot (full-state dump, CLI-only before), 🔍 Conflict Recheck (tools + double-sudo)',
    'MCE 对话框 +权威 CPU MCE 计数徽标（接线 P0-1 修复的 mce_count，区分 CPU MCE vs PCIe AER）': 'MCE dialog + authoritative CPU MCE count badge (wires the P0-1-fixed parser; distinguishes CPU MCE from PCIe AER)',
    '场景页 +➕ 创建自定义方案（沙箱试用向导 GUI 化，顺手修复沙箱缺基类缺陷）+ 每行 🌲 继承链查看': 'Scenes page + ➕ Create Custom Scene (GUI wizard; fixed the sandbox base-class bug) + per-row 🌲 inheritance view',
    '性能日志页 +最新采样实时头部；进程页/总览页 +操作提示文案（可发现性）': 'Perf log + live latest-sample header; process/overview pages + discoverability hints',
    'controller 新增 4 API（system_snapshot/try_user_profile/profile_inheritance/conflict_recheck）': '4 new controller APIs (system_snapshot/try_user_profile/profile_inheritance/conflict_recheck)',
    'i18n 字典 453→474 条；全量测试 112/112 双绿': 'i18n dictionary 453→474 entries; full suite 112/112 green',
    '全面审计 + 双 P0 修复 + D7 验收': 'Full audit + dual P0 fixes + D7 acceptance',
    'D7 观察期提前验收通过：-100mV 确认稳定生产配置（16/16 项证据达标，零死机/零 MCE/零误触发）': 'D7 observation accepted early: -100mV confirmed stable (16/16 criteria; zero crashes/MCE/false triggers)',
    '全面审计发现 2 个 P0 生产 bug：': 'The audit found two P0 production bugs:',
    '  P0-A: perf 采样静默停摆 5 天（PerfSample 无效 kwarg + 静默 except 吞错）→ 已修，14:08 生产验证恢复（每 30s 精确采样）': '  P0-A: perf sampling silently dead for 5 days (invalid kwarg + silent except) → fixed; verified live at 14:08 (exact 30s cadence)',
    '  P0-B: GPU GT 频率联动从未生效（误写 NVIDIA 卡）→ 已修，14:15 验证首次真实写入': '  P0-B: GPU GT coupling never worked (wrote the wrong card) → fixed; first real write verified at 14:15',
    '审计加固：新增 perf 管道回归测试（3 项）、静默吞错治理（62→13→4 修复）、巡检 11→13 项（部署物一致性 + perf 零采样告警）': 'Hardening: perf pipeline regression tests (3), silent-except governance (62→13→4 fixed), health checks 11→13',
    '测试矩阵 112/112 双绿（91 Python + 21 shell，12 套件）': 'Test matrix 112/112 green (91 Python + 21 shell, 12 suites)',
    '清理：v4 死文件 + 2 个 sudoers 旧备份': 'Cleanup: v4 dead file + 2 stale sudoers backups',
    'i18n 全面应用（中英双语）': 'i18n rollout (bilingual)',
    '三批次完成 496 处 T() 替换（批1: 44 · 批2: 419 · 批3: 45 处 f-string 模板化）': '496 T() replacements in three batches (44 + 419 + 45 f-string templates)',
    '翻译字典扩至 453 条（zh/en 完全对齐，占位符全一致）': 'Dictionary grew to 453 entries (zh/en aligned, placeholders consistent)',
    'f-string 中文残留归零；en locale 6 页 GUI 实弹验证': 'f-string Chinese residues zeroed; 6 pages verified under en locale',
    '豁免项：页面注册键 20 处（B 类防断链）+ 本页内容（文档正文）': "Exemptions: 20 page-registry keys (chain-safety) + this page's body",
    '红线决定 + P0/P1 修复': 'Red-line decision + P0/P1 fixes',
    '用户决定：永久移除 API/Web UI（红线文档 NOT_API_WEBUI.md）': 'User decision: API/Web UI permanently removed (NOT_API_WEBUI.md)',
    'P0-1: uv-daily-check MCE 误报修复（ras-mc-ctl 权威源替代 dmesg 匹配）': 'P0-1: daily-check MCE false positives fixed (ras-mc-ctl as authoritative source)',
    'P1-1: uv-safeguard 三级判定（CLEAN/CRASH_REVERT/WATCH，手动重启不再误回退）': 'P1-1: safeguard 3-tier verdict (manual restarts no longer trigger reverts)',
    'A1: 进程列表性能修复（两阶段读取 + PSS 缓存，511ms→119ms）': 'A1: process-list performance (two-phase reads + PSS cache, 511ms→119ms)',
    'C1: git 仓库建立（含 .gitignore 隔离会话记录）': 'C1: git repo established (.gitignore isolates session records)',
    'Phase 1 部署 + Phase 2 G1-G6 + v2.0 基线': 'Phase 1 deployment + Phase 2 G1-G6 + v2.0 baseline',
    'Phase 1 部署：undervolt/acdc/cpu-power-limit/thermal-guard/deadman 五服务 + sudoers 白名单': 'Phase 1: five services (undervolt/acdc/cpu-power-limit/thermal-guard/deadman) + sudoers whitelist',
    'Phase 2 G1-G6：profile 解析器 + plugin 抽象 + 进程页 + 限流时间轴': 'Phase 2 G1-G6: profile parser, plugin abstraction, processes page, throttle timeline',
    'R4: MSR 限流实时读取集成（注：当日引入的 kwarg 缺陷 09-07 审计修复）': 'R4: live MSR throttle reads (the kwarg defect introduced that day was fixed in the 09-07 audit)',
    '降压方案重启：-100mV（v1 时代曾回退 -50mV，见死机史 #3）': 'Undervolt restarted at -100mV (v1 once rolled back to -50mV, see crash #3)',
    '本次更新': 'This update',
    '新增说明文档页（本页）': 'Added this documentation page',
    '修复 csd-backlight-helper 闪烁振荡（禁用 helper + C-state=4 回退）': 'Fixed csd-backlight-helper flicker (helper disabled + C-state=4)',
    '修复 MSR 读取批量 sudo（性能优化）': 'Optimized batched sudo for MSR reads',
    '修复 battery_stats 标签匹配（battery/batt）': 'Fixed battery_stats label matching',
    '修复 ui_advanced 被删除方法引用（迁移到 maintenance 页）': 'Fixed stale method references in ui_advanced',
    '修复 perf_logger _on_draw_charge 方法缺失（snapshot 恢复后）': 'Restored perf_logger _on_draw_charge after snapshot restore',
    '新增 undervolt-resume.service（suspend/resume 重新应用）': 'Added undervolt-resume.service (re-apply after suspend)',
    '清除残留 intel-undervolt.service 单元文件（-100mV 安全隐患）': 'Removed leftover intel-undervolt.service (security risk)',
    '电源优化打包三分类重组': 'Power-pack reorganized into three categories',
    'WS1 目录重组为 Win/Linux/共享 三分类': 'WS1 reorganized: Win/Linux/Shared',
    '新增 09A Windows 生态全景文档（93 项能力）': 'Added 09A Windows ecosystem doc (93 capabilities)',
    '新增 10 电源模式科学性审计（180 项设置验证）': 'Added 10 power-mode science audit (180 settings verified)',
    '新增 17-19 三篇审计报告（功能 100% PASS）': 'Added audit reports 17-19 (100% PASS)',
    'Windows 控制台升级到 v6.6': 'Windows console upgraded to v6.6',
    '文件空间回收 93.6%（2.75 GB → 176 MB）': 'Reclaimed 93.6% disk space (2.75 GB → 176 MB)',
    '当前恢复点': 'Current restore point',
    '创建 Timeshift 快照 0822_110321': 'Created Timeshift snapshot 0822_110321',
    '修复 console_full_test.py（34/34 PASS）': 'Fixed console_full_test.py (34/34 PASS)',
    '新增 battery_analytics.py 七维分析引擎': 'Added battery_analytics.py 7-dimension engine',
    '新增 hardware_probe.py 硬件探测': 'Added hardware_probe.py hardware probing',
    '新增 adapt_test.sh 跨平台适配测试': 'Added adapt_test.sh cross-platform test',
    '修复控制台三个 bug（曲线归一化/电源卡/通知文本）': 'Fixed three console bugs (curve normalization/power card/notification text)',
    '死机调查与修复': 'Crash investigation & fixes',
    '调查 C-state 深度导致死机（#1）': 'Investigated C-state crash (#1)',
    'GRUB 设置 max_cstate=4': 'GRUB max_cstate=4 set',
    '创建 Timeshift 快照 0817（基线）': 'Created Timeshift snapshot 0817 (baseline)',
    '恢复 undervolt 到 -50mV（-100mV 死机 #3）': 'Rolled back to -50mV (-100mV crash #3)',
    'C-State 深度': 'C-state Depth',
    '命令行别名（终端快捷方式）': 'CLI aliases (terminal shortcuts)',
    'syscon：启动控制台（等价桌面图标）': 'syscon: launch the console (same as the desktop icon)',
    'syscon-check：跑 13 项健康巡检（服务/降压/部署物/采样）': 'syscon-check: run the 13-item health check (services/undervolt/deployments/sampling)',
    'syscon-snap：导出系统诊断快照（等价维护页「📋 一键诊断快照」）': 'syscon-snap: export a diagnostic snapshot (same as the maintenance-page button)',
    'syscon-conflict：互斥工具冲突 + double-sudo 检测（等价「🔍 冲突复查」）': 'syscon-conflict: tool-conflict + double-sudo checks (same as 🔍 Conflict Recheck)',
    'syscon-profiles / syscon-plugins：列出 profile / plugin 清单': 'syscon-profiles / syscon-plugins: list profiles / plugins',
    'syscon-audit：double-sudo 静态审计': 'syscon-audit: double-sudo static audit',
    'syscon-test：跑全量测试套件': 'syscon-test: run the full test suite',
    'syscon-edit：用编辑器打开项目目录': 'syscon-edit: open the project in an editor',
    '安装方式：bash scripts/install_bash_alias.sh（重装后执行一次）': 'Install: bash scripts/install_bash_alias.sh (once after reinstall)',
}


def _D(text):
    """文档正文双语：en locale 时查 DOC_EN，否则原文"""
    from src.core.i18n import I18n
    loc = I18n.get()._current_locale or 'zh_CN'
    if loc == 'en_US':
        return DOC_EN.get(text, text)
    return text


class DocumentationPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(12)
        self.set_margin_end(12)

        # --- 目录导航栏 ---
        nav_box = Gtk.Box(spacing=6)
        nav_label = Gtk.Label(label=_D("目录:"), xalign=0)
        nav_label.get_style_context().add_class("section-title")
        nav_box.pack_start(nav_label, False, False, 0)

        toc_items = [
            ("overview", _D("概述")),
            ("pages", _D("页面功能")),
            ("concepts", _D("核心概念")),
            ("ecosystem", _D("生态清单")),
            ("safety", _D("安全规则")),
            ("troubleshoot", _D("故障排查")),
            ("crossmachine", _D("跨平台")),
            ("changelog", _D("更新日志")),
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
        text = _D(text)
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.get_style_context().add_class("section-title")
        return lbl

    @staticmethod
    def _subtitle(text):
        text = _D(text)
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.get_style_context().add_class("dim-text")
        return lbl

    @staticmethod
    def _h1(text):
        text = _D(text)
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.set_margin_top(16)
        lbl.set_margin_bottom(6)
        lbl.get_style_context().add_class("section-title")
        return lbl

    @staticmethod
    def _h2(text):
        text = _D(text)
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.set_margin_top(10)
        lbl.set_margin_bottom(4)
        lbl.get_style_context().add_class("dim-text")
        return lbl

    @staticmethod
    def _p(text, wrap=True):
        text = _D(text)
        lbl = Gtk.Label(label=text, xalign=0, wrap=wrap, selectable=True)
        lbl.set_line_wrap(True)
        return lbl

    @staticmethod
    def _bullet(text):
        text = _D(text)
        lbl = Gtk.Label(label=f"  • {text}", xalign=0, wrap=True, selectable=True)
        lbl.set_line_wrap(True)
        return lbl

    @staticmethod
    def _code(text):
        text = _D(text)
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
            "通过七个功能页面提供全方位的硬件监控、电源场景切换、电池保养、"
            "高级调优、进程详情、系统维护和说明文档。"), False, False, 4)
        box.pack_start(self._p(
            "控制台采用「科学优化」理念：所有优化决策基于实测数据和权威文档，"
            "严格遵循死机史铁律（不碰 EC、不用 stress-ng、不动风扇），"
            "保证系统稳定性的前提下最大化续航和性能。"), False, False, 4)
        box.pack_start(self._h2("界面语言切换"), False, False, 0)
        box.pack_start(self._bullet("系统维护页 → 「界面语言」下拉框 → 选择（自动/中文/English）→ 应用 → 重启控制台生效"), False, False, 0)
        box.pack_start(self._bullet("托盘图标右键菜单 → 语言 Language → 选择（与维护页等效）"), False, False, 0)
        box.pack_start(self._bullet("配置文件：~/.config/system-console/config.yaml 的 language 项（auto=跟随系统）"), False, False, 0)
        box.pack_start(self._h2("命令行别名（终端快捷方式）"), False, False, 0)
        box.pack_start(self._bullet("syscon：启动控制台（等价桌面图标）"), False, False, 0)
        box.pack_start(self._bullet("syscon-check：跑 13 项健康巡检（服务/降压/部署物/采样）"), False, False, 0)
        box.pack_start(self._bullet("syscon-snap：导出系统诊断快照（等价维护页「📋 一键诊断快照」）"), False, False, 0)
        box.pack_start(self._bullet("syscon-conflict：互斥工具冲突 + double-sudo 检测（等价「🔍 冲突复查」）"), False, False, 0)
        box.pack_start(self._bullet("syscon-profiles / syscon-plugins：列出 profile / plugin 清单"), False, False, 0)
        box.pack_start(self._bullet("syscon-audit：double-sudo 静态审计"), False, False, 0)
        box.pack_start(self._bullet("syscon-test：跑全量测试套件"), False, False, 0)
        box.pack_start(self._bullet("syscon-edit：用编辑器打开项目目录"), False, False, 0)
        box.pack_start(self._bullet("安装方式：bash scripts/install_bash_alias.sh（重装后执行一次）"), False, False, 0)
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
        box.pack_start(self._h2("4d. MSR 降压调节（2026-09-11 新增）"), False, False, 0)
        box.pack_start(self._bullet("core 与 cache 电气同轨：两域在同一电压平面，强制同值联动调节"), False, False, 0)
        box.pack_start(self._bullet("GPU 独立域：核显电压单独可调，可尝试比 core 更深档位"), False, False, 0)
        box.pack_start(self._bullet("范围 0 ~ -130mV（D7 验收余量），温度墙 60~105°C"), False, False, 0)
        box.pack_start(self._bullet("安全机制：应用即写 MSR + 原子更新 undervolt.service，回读校验失败自动回滚；uv_safeguard/uv_daily_check/msr_deadman 三重守护基准随 service 自动同步；挂起唤醒值同步（undervolt-resume.service）"), False, False, 0)
        box.pack_start(self._bullet("科学调法：每档 -10mV 逐级下调 + 24h 观察期 + 基准测试验证；异常关机后安全网自动回退"), False, False, 0)
        box.pack_start(self._bullet("全程留痕：/var/log/uv_set.log"), False, False, 0)
        box.pack_start(self._h2("4e. GRUB 启动菜单时间（2026-09-11 新增）"), False, False, 0)
        box.pack_start(self._bullet("等待秒数：0=跳过菜单直接启动默认项，最大 300 秒"), False, False, 0)
        box.pack_start(self._bullet("显示方式：显示菜单 / 隐藏（仅倒计时）"), False, False, 0)
        box.pack_start(self._bullet("自动同步 GRUB_RECORDFAIL_TIMEOUT：异常关机后不再回退 30 秒默认"), False, False, 0)
        box.pack_start(self._bullet("原配置备份于 /etc/default/grub.grubtime.bak，可一键还原"), False, False, 0)
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

        # 进程详情（v2.0 新增第七页）
        box.pack_start(self._h2("6. 进程详情页（Processes）"), False, False, 0)
        box.pack_start(self._p(
            "按 PSS（比例集大小，精确共享内存）排序的 Top 50 进程监控（2026-09-02 新增）。"
            "支持搜索过滤、双击查看详情、右键 kill/renice 操作。"), False, False, 4)
        box.pack_start(self._bullet("PSS 排序：比 RSS 更精确地反映真实内存占用（共享页按比例分摊）"), False, False, 0)
        box.pack_start(self._bullet("性能优化：两阶段读取（轻扫 top-50 后才读 smaps_rollup）+ 5s PSS 缓存，冷启 <300ms 热刷 <100ms"), False, False, 0)
        box.pack_start(self._bullet("进程操作：右键菜单支持 TERM/KILL/HUP 信号与 renice 优先级调整（需授权）"), False, False, 0)
        box.pack_start(self._bullet("实时刷新：可切换自动刷新（3s）或手动刷新"), False, False, 0)
        box.pack_start(self._sep(), False, False, 0)

        # 说明文档
        box.pack_start(self._h2("7. 说明文档页（Documentation）"), False, False, 0)
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
            "本机实测 -100mV 稳定运行（实测 -99.61mV，量化误差 0.39mV），2026-09-07 通过 D7 观察期验收："
            "零死机、零 MCE、保护机制零误触发（详见下方死机史记录说明）。MSR 0x150 未被 BIOS 锁定。"
            "三重保护：msr_deadman（95°C 自动回退）、uv-safeguard（异常关机回退）、uv-daily-check（每日巡检告警）。"
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
            "当前设置 -100mV（三域：core/uncore/gpu），由 undervolt.service 统一管理，"
            "实测 -99.61mV（量化误差 0.39mV）。D7 观察期验收通过（2026-09-07，16/16 项证据达标）。"
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
            ("[已实现] AC/DC 场景自动切换", "acdc-profile v9，3秒轮询，6场景自动切换，含 GPU GT 频率联动（AC 1100/DC 700MHz，2026-09-07 修复生效）"),
            ("[已实现] Undervolt 降压 -100mV", "MSR 0x150，三域（core/uncore/gpu），D7 验收通过，三重保护（deadman/safeguard/daily-check）"),
            ("[已实现] 降压三重保护体系", "msr_deadman（95°C 自动回退，30s 巡检）+ uv-safeguard（三级判定 CLEAN/CRASH_REVERT/WATCH）+ uv-daily-check（每日 10:01 巡检告警）"),
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
            box.pack_start(self._bullet(f"{_D(name)} — {_D(desc)}"), False, False, 0)

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
            box.pack_start(self._bullet(f"✗ {_D(item)}"), False, False, 0)

        box.pack_start(self._h2("待做项（监测中/待实现）"), False, False, 0)
        todo = [
            "夜间模式（Night Light）—— Phase 1 规划",
            "undervolt 更深档位探索 —— -100mV 已验收稳定使用中（如需推进需重新走 7 天观察期流程）",
            "cross-machine portability —— hardware_probe + adapt_test 已实现，待实际验证",
            "GitHub 发布 —— 仓库已就绪（v2.0.0 + v2.0.1-accepted 双 tag），待推送凭据",
            "隐形功能 GUI 化 —— 2026-09-07 已完成 A/B 类收编（诊断快照/冲突复查/MCE 计数/自定义方案向导/继承链）",
        ]
        for item in todo:
            box.pack_start(self._bullet(f"△ {_D(item)}"), False, False, 0)

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
        box.pack_start(self._bullet("#3 — Undervolt -100mV 导致不稳定（2026-08-18 时点）→ 后经科学验证重启：v2.0 方案配三重保护，2026-09-07 D7 观察期验收通过（零死机/零 MCE/零误触发），现稳定运行于 -100mV（详见更新日志）"), False, False, 0)
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
        box.pack_start(self._bullet("手动重新应用：sudo systemctl restart undervolt（推荐，服务内含标准参数）"), False, False, 0)
        box.pack_start(self._bullet("应急回退：sudo undervolt --core -50 --cache -50 --gpu -50（降压不稳时降至安全档）"), False, False, 0)
        box.pack_start(self._bullet("每日巡检：uv-daily-check 每日 10:01 自动检查，异常会弹通知并写 /var/log/uv_daily_check.alert"), False, False, 0)

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
        box.pack_start(self._bullet(_D("命令行：sudo %s check/repair") % os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "backend", "kernel_guard.sh")), False, False, 0)

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
            ("2026-09-08", "语言切换功能（中英双语可用化）", [
                "语言不再只能跟随系统 locale：config.yaml 新增 language 项（auto/zh_CN/en_US）",
                "维护页新增「界面语言」下拉框 + 应用按钮（托盘菜单也有入口）",
                "选择后写入配置，重启控制台生效；自动模式跟随系统语言",
            ]),
            ("2026-09-07", "隐形功能 GUI 化（审计 A/B 类收编）", [
                "维护页 +2 按钮：📋 一键诊断快照（tlp-stat 风格全景，此前仅 CLI）、🔍 冲突复查（互斥工具+double-sudo 运行期复查）",
                "MCE 对话框 +权威 CPU MCE 计数徽标（接线 P0-1 修复的 mce_count，区分 CPU MCE vs PCIe AER）",
                "场景页 +➕ 创建自定义方案（沙箱试用向导 GUI 化，顺手修复沙箱缺基类缺陷）+ 每行 🌲 继承链查看",
                "性能日志页 +最新采样实时头部；进程页/总览页 +操作提示文案（可发现性）",
                "controller 新增 4 API（system_snapshot/try_user_profile/profile_inheritance/conflict_recheck）",
                "i18n 字典 453→474 条；全量测试 112/112 双绿",
            ]),
            ("2026-09-07", "全面审计 + 双 P0 修复 + D7 验收", [
                "D7 观察期提前验收通过：-100mV 确认稳定生产配置（16/16 项证据达标，零死机/零 MCE/零误触发）",
                "全面审计发现 2 个 P0 生产 bug：",
                "  P0-A: perf 采样静默停摆 5 天（PerfSample 无效 kwarg + 静默 except 吞错）→ 已修，14:08 生产验证恢复（每 30s 精确采样）",
                "  P0-B: GPU GT 频率联动从未生效（误写 NVIDIA 卡）→ 已修，14:15 验证首次真实写入",
                "审计加固：新增 perf 管道回归测试（3 项）、静默吞错治理（62→13→4 修复）、巡检 11→13 项（部署物一致性 + perf 零采样告警）",
                "测试矩阵 112/112 双绿（91 Python + 21 shell，12 套件）",
                "清理：v4 死文件 + 2 个 sudoers 旧备份",
            ]),
            ("2026-09-07", "i18n 全面应用（中英双语）", [
                "三批次完成 496 处 T() 替换（批1: 44 · 批2: 419 · 批3: 45 处 f-string 模板化）",
                "翻译字典扩至 453 条（zh/en 完全对齐，占位符全一致）",
                "f-string 中文残留归零；en locale 6 页 GUI 实弹验证",
                "豁免项：页面注册键 20 处（B 类防断链）+ 本页内容（文档正文）",
            ]),
            ("2026-09-04", "红线决定 + P0/P1 修复", [
                "用户决定：永久移除 API/Web UI（红线文档 NOT_API_WEBUI.md）",
                "P0-1: uv-daily-check MCE 误报修复（ras-mc-ctl 权威源替代 dmesg 匹配）",
                "P1-1: uv-safeguard 三级判定（CLEAN/CRASH_REVERT/WATCH，手动重启不再误回退）",
                "A1: 进程列表性能修复（两阶段读取 + PSS 缓存，511ms→119ms）",
                "C1: git 仓库建立（含 .gitignore 隔离会话记录）",
            ]),
            ("2026-09-02", "Phase 1 部署 + Phase 2 G1-G6 + v2.0 基线", [
                "Phase 1 部署：undervolt/acdc/cpu-power-limit/thermal-guard/deadman 五服务 + sudoers 白名单",
                "Phase 2 G1-G6：profile 解析器 + plugin 抽象 + 进程页 + 限流时间轴",
                "R4: MSR 限流实时读取集成（注：当日引入的 kwarg 缺陷 09-07 审计修复）",
                "降压方案重启：-100mV（v1 时代曾回退 -50mV，见死机史 #3）",
            ]),
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
            box.pack_start(self._h2(f"{date} — {_D(title)}"), False, False, 0)
            for change in changes:
                box.pack_start(self._bullet(_D(change)), False, False, 0)

        box.pack_start(self._sep(), False, False, 0)
        return box
