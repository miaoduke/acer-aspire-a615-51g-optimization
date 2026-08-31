# Windows 系统控制台
> 版本: **v6.8** (2026-08-28) · 目标机: 本机 Acer A615-51G / Windows 11 专业工作站版 Build 26200 / .NET Framework 4.8 (csc 编译, 零外部依赖)
> 设计原则（对齐 Linux 版控制台）: 占用小 · 省电(自适应采样) · 高效(直读系统 API) · 快速启动
> 测试状态: 全绿 FAIL=0（详见 test_report.txt; v6.8 = 审计全修完 + 真值实测科学性修 3 条, 见 共享_20260825\系统控制台方案_20260825\20_代码审计_20260827.md 第七节）

## 功能（六页）

| 页面 | 内容 |
|---|---|
| 总览 | CPU/内存/GPU/电池状态卡、CPU 历史曲线(自绘)、每核占用柱条、内存条、磁盘 IO、网卡速率、温度行(LHM 核心温度优先/ACPI 温区)、CPU 功耗(LHM)、独立 GPU 行(nvidia-smi)、开机时长、当前电源计划 |
| 电源 | 电量与充放状态、剩余时间估计、电源计划一键切换、场景自动切换(AC/DC 联动)、生成 HTML 电池报告、电池损耗分析(循环次数/设计容量/满充容量) |
| 调优 (v6) | CPU 状态四项: 最大/最小处理器状态、Boost 模式、**EPP 能量性能偏好 AC/DC 双滑块 (v6.5; 当前 40/84)** · **无线适配器功耗 AC/DC 档位 (v6.6)** · 隐藏电源设置浏览与写入 · Win11 电源模式 overlay 切换 (含 v6.6 DC 独立修正) · **dGPU 断电辅助: 检测独显占用进程+一键结束 (v6.6)** · NVIDIA PowerMizer 注册表读写 · nvidia-smi 深度解析(P状态/时钟/功耗墙/降频原因) · Acer EC-WMI 三档配置切换 + 风扇状态只读 |
| 进程 | 进程列表(名称/PID/CPU%/内存)、点列头排序、结束任务带确认、**右键效率模式 EcoQoS 开/关 + 持久化规则 (v6.6)** |
| 系统 | 本机信息(OS+Build/CPU/BIOS/主板/磁盘分区，各段独立容错)、设置区：开机自启 / 气泡告警 / 采样间隔(1/2/5s)、**电池时降60Hz (v6.6)**、**低电量自动省电 (v6.6)**、以管理员重启、快捷入口 |
| 维护 (v3.3) | LHM 全传感器明细、维护工具入口 |

**版本里程碑**: v2 基础四页+LHM+nvidia-smi → v3.3 维护页 → v4 布局模块开关 → v5 对比测试工具 → v6.1 Acer EC-WMI 硬件联动 → v6.2 热点参数补全 → v6.3 NVIDIA 深度解析 → v6.4 隐藏设置浏览器 → v6.5 EPP 双滑块（A/B 实测: EPP 0→70 空闲频率 -75%、负载 -14%、GPU 突发 -4°C）→ **v6.6 EcoQoS 效率模式 + 无线功耗档位 + DC Overlay 独立修正 + dGPU 断电辅助 + 低电量自动省电 + 刷新率跟随（外接高刷屏）+ 断电后计数器挂死修复（PerProc 采集后台化）**（EPP 折中实验四点数据: 空闲收益 EPP=40 即饱和, 负载 0-50 无惩罚 → 已应用 AC=40/DC=84；数据见 ..\..\共享_20260825\系统控制台方案_20260825\证据存档_20260825\）

省电设计: 前台按设定间隔采样 / 失焦自动 ≥5s；GPU 计数器实例每分钟重建；nvidia-smi 每 5 次采样查询一次。

## 使用

```
双击 启动器.bat              （或直接运行 SysConsole.exe；启动控制台.cmd 等效）
build.cmd                  （重新编译，仅需系统自带 csc，零外部依赖）
powershell -File test_suite.ps1   （自动化测试套件，输出 test_report.txt）
SysConsoleDebug.exe --selftest    （采集层自检，含 LHM/nvidia/告警逻辑/注册表回环等 10+ 项）
SysConsole.exe /tab=N             （直接打开第 N 页, 0-5）
SysConsoleDebug.exe /get all      （CLI: 查询全部关键状态 — SysConsole.exe 是 winexe, CLI 输出不可见, 请用 Debug 版）
SysConsoleDebug.exe /set epp 40 84 （CLI: 写 EPP；另支持 boost/wireless/aspm/overlay/refresh/plan）
```

## 已知限制

1. **CPU 核心温度需管理员权限**——非管理员运行时 LHM 不启用(Ring0 驱动限制)，显示降级为 ACPI 温区提示；用"系统页→以管理员身份重启"解锁完整传感器。
2. GPU 功耗读数 N/A / 默认功耗墙 5001W —— MX150 VBIOS 功耗表未初始化(已实测复现)，非软件 bug；第三方超频工具同样无从下手。
3. 切换电源计划在部分系统策略下需管理员。
4. OSVersion 显示 6.2.9200 为 .NET 兼容模式行为，真实版本已用 WMI BuildNumber 补正。
5. EPP 在本机为隐藏设置（powercfg /q 查不到，/qh 可见），当前值 AC=40 / DC=84（v6.6 折中实验后已应用）。
6. 微软 2025-03 起 Defender 标记 WinRing0 驱动(CVE-2020-14979)；本机 LHM 当前正常，若未来被拦，温度监控退化 ACPI 温区路径。

## 文件清单

| 文件 | 说明 |
|---|---|
| Program.cs | 入口/单实例/DPI/--selftest//tab 参数/AppLogic 纯逻辑层 |
| Collector.cs | 采集: 性能计数器+内存 P/Invoke+WMI 温度/电池/亮度+LHM 反射+nvidia-smi(+深度查询)+powercfg+EPP/overlay/PowerMizer/Acer EC-WMI |
| MainForm.cs | UI: 六页+设置区+自绘曲线+进程表+托盘+告警+settings.ini |
| LoadAdvisor.cs | 负载建议逻辑 |
| TestRefresh.cs | 刷新率 API 功能自检 (csc Collector.cs TestRefresh.cs /out:TestRefresh.exe 后运行; 60Hz 往返验证) |
| LibreHardwareMonitorLib.dll | v0.9.6 (MIT)，可选依赖，反射加载 |
| build.cmd / 启动控制台.cmd / 提权运行.bat / test_suite.ps1 | 编译/启动/提权/自动化测试 |
| test_report.txt · selftest_result.txt · shot_tab*.png | 测试产物 (可随时删除, 由 test_suite/--selftest 重新生成) |
