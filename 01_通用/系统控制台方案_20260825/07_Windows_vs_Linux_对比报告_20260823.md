# Windows vs Linux 系统控制台 — 功能差异对比报告
> 日期：2026-08-23
> 对象：Windows v2 (WinForms/C#) vs Linux v3 (GTK3/Python)

---

## 一、功能矩阵总览

| 功能类别 | Linux | Windows | 差异 |
|---|:---:|:---:|---|
| **数据采集** | | | |
| CPU 利用率 (总+每核) | ✅ /proc/stat | ✅ PerformanceCounter | 平手 |
| CPU 频率 (每核) | ✅ sysfs cpufreq | ❌ | Win 缺失 |
| RAPL 功耗分解 (总/核/uncore/DRAM) | ✅ intel-rapl | ❌ | Win 缺失（LHM 有 Package 功耗） |
| CPU 温度 (LHM/ACPI) | ✅ thermal_zone | ✅ LHM + WMAcpi | 平手（需管理员） |
| 风扇转速 | ✅ thermal_zone | ❌ 0个 | Win 硬件不暴露 |
| GPU (独显+集显) | ✅ nvidia-smi + prime-select | ✅ nvidia-smi + PerfCounter | 平手 |
| GPU GT 频率联动 | ✅ sysfs gt_freq | ❌ | Win 缺失 |
| 内存 | ✅ /proc/meminfo | ✅ GlobalMemoryStatusEx | 平手 |
| 磁盘 I/O | ✅ (未详列) | ✅ PerfCounter | 平手 |
| 网络 I/O | ✅ (未详列) | ✅ PerfCounter | 平手 |
| 电池 (容量/功率/温度/健康度) | ✅ sysfs + WMI | ✅ SystemInformation | Linux 更深 |
| 充电阶段检测 (CC/CV) | ✅ 电流微分算法 | ❌ | Win 缺失 |
| 电池历史曲线 | ✅ TSV 持久化 | ❌ | Win 缺失 |
| 电源计划 | ✅ controller.py | ✅ powercfg 解析 | 平手 |
| **UI/交互** | | | |
| 实时曲线 (CPU/内存/电池) | ✅ Cairo 绘制 | ✅ CurvePanel | 平手 |
| 充电曲线 (双轴) | ✅ 容量%+电流mA | ❌ | Win 缺失 |
| 电池温度曲线 | ✅ acer-wmi-battery | ❌ | Win 缺失 |
| 健康度趋势线 | ✅ 最小二乘拟合 | ❌ | Win 缺失 |
| 可配置仪表板布局 | ✅ JSON 布局文件 | ❌ | Win 缺失 |
| 场景页 (一键切换) | ✅ 6场景+M3 | ❌ | Win 缺失 |
| 高级控制 (滑块) | ✅ TCC/PL1/PL2/CPU% | ❌ | Win 缺失 |
| 外设控制 (USB/WiFi/摄像头) | ✅ | ❌ | Win 缺失 |
| 电池保养页 | ✅ 7维分析+学术引用 | ❌ | Win 缺失 |
| 系统维护页 | ✅ 服务/内核/MCE | ❌ | Win 缺失 |
| 进程管理 | ❌ | ✅ 排序+Kill | Win 独有 |
| 系统信息页 | ❌ | ✅ WMI+注册表 | Win 独有 |
| 开机自启 | ✅ systemd | ✅ HKCU Run | 平手 |
| 气泡告警 | ✅ 通知系统 | ✅ NotifyIcon | 平手 |
| **后台系统** | | | |
| 性能日志 (TSV) | ✅ 30秒/条 | ❌ | Win 缺失 |
| 负载建议器 | ✅ load_advisor | ❌ | Win 缺失 |
| 应用功耗排行 (cgroup) | ✅ | ❌ | Win 缺失 |
| 基准测试 (EMP) | ✅ 统计学方法 | ❌ | Win 缺失 |
| 内核守卫 | ✅ 模块检测+修复 | ❌ | Win 不适用 |
| 自动测试套件 | ✅ console_full_test.py | ✅ test_suite.ps1 | 平手 |

---

## 二、Linux 独有功能（Windows 应借鉴）

### 🔴 高优先级（核心监控缺失）

| # | 功能 | Linux 实现 | Windows 可行方案 |
|---|---|---|---|
| 1 | **CPU 频率监控** | `/sys/devices/system/cpu/*/cpufreq/scaling_cur_freq` | WMI `Win32_Processor.CurrentClockSpeed` 或 `PowerShell Get-CimInstance` |
| 2 | **RAPL 功耗分解** | `/sys/class/powercap/intel-rapl:0/energy_uj` | LHM 已有 CPU Package 功耗；可补充 core/uncore/dram 子域（需管理员） |
| 3 | **充电曲线 (双轴)** | 容量% + 电流mA 实时绘制 | `SystemInformation.PowerStatus` + WMI `Win32_Battery` 获取电流/电压 |
| 4 | **电池温度** | `acer-wmi-battery` WMI 模块 | WMI `Win32_Battery` 有 `Temperature` 属性（需管理员） |
| 5 | **性能日志持久化** | TSV 文件，30秒/条 | 写 CSV/TSV 到 `%APPDATA%\SysConsole\logs\` |

### 🟡 中优先级（增强体验）

| # | 功能 | Linux 实现 | Windows 可行方案 |
|---|---|---|---|
| 6 | **场景一键切换** | 6场景 (ac-perf/bal/quiet, bat-save/bal/perf) | 4个电源计划 (高性能/平衡/静音/省电) 已有；加 UI 快捷入口 |
| 7 | **可配置仪表板布局** | JSON 布局文件 + 拖拽排序 | ListView + 上下移动按钮，保存到 settings.ini |
| 8 | **健康度趋势线** | 最小二乘拟合 | 简单线性回归，数据来自电池历史 |
| 9 | **应用功耗排行** | cgroup CPU 时间差分 | 任务管理器已有；可做简化版：按 CPU 时间排序 |
| 10 | **充电阶段检测** | CC/CV 电流微分 | 电流差分 + 电压阈值判断 |

### 🟢 低优先级（Linux 特有/Windows 不适用）

| # | 功能 | 说明 |
|---|---|---|
| 11 | 内核守卫 | Linux 模块管理，Windows 不适用 |
| 12 | MCE/RAS 硬件错误 | Linux 特有诊断 |
| 13 | 外设控制 (USB/WiFi/摄像头) | Windows 设备管理器已有 |
| 14 | GPU GT 频率联动 | Intel 集显特有，Windows 需注册表 |
| 15 | 基准测试 (EMP) | 可选功能，非核心 |
| 16 | 负载建议器 | 需要场景系统支撑 |

---

## 三、Windows 独有功能（Linux 应借鉴）

| # | 功能 | Windows 实现 | Linux 可行方案 |
|---|---|---|---|
| 1 | **进程管理 (排序+Kill)** | ListView + Process.Kill() | `psutil` + GTK TreeView |
| 2 | **系统信息页** | WMI + 注册表 | `/proc/cpuinfo` + `lsblk` + `lscpu` |
| 3 | **DPI 感知** | `SetProcessDPIAware()` | GTK3 自动处理 |
| 4 | **binding redirect 机制** | 解决 .NET 版本冲突 | N/A (Python 无此问题) |
| 5 | **selftest --autoclose** | 自动退出测试模式 | 可移植 |

---

## 四、推荐改进路线（按优先级）

### Phase 1: 核心数据补齐（预计 +2 天）

1. **CPU 频率监控** — WMI 查询或 PowerShell，总览页显示频率范围
2. **电池温度** — WMI `Win32_Battery.Temperature`，总览页+告警
3. **充电曲线** — 双轴 Chart 控件，电池页显示容量%+电流mA
4. **性能日志** — CSV/TSV 持久化到 `%APPDATA%`，支持时间范围查询

### Phase 2: 交互增强（预计 +3 天）

5. **场景快捷切换** — HeaderBar 下拉菜单，4个电源计划一键切换
6. **可配置布局** — 仪表板模块可拖拽排序，保存到 settings.ini
7. **电池健康度趋势** — 简单线性回归，历史数据持久化
8. **充电阶段检测** — CC/CV 判断，电池页显示当前阶段

### Phase 3: 高级功能（预计 +2 天）

9. **应用功耗排行** — 按 CPU 时间排序的 Top-N 进程
10. **电池科学分析** — 放电深度、循环率、健康外推
11. **系统维护页** — 服务状态、启动项管理

---

## 五、架构差异分析

| 维度 | Linux | Windows | 建议 |
|---|---|---|---|
| 语言 | Python3 + GTK3 | C# + WinForms + .NET 4.8 | 各自最优选 |
| 数据采集 | /proc + /sys + 命令 | WMI + PerfCounter + P/Invoke | 平手 |
| UI 框架 | GTK3 (Cairo 绘制) | WinForms (GDI+) | 平手 |
| 配置持久化 | TSV + JSON + systemd | settings.ini + registry | 平手 |
| 异步执行 | async_util.py | 无（同步 tick） | Win 可加 BackgroundWorker |
| 测试框架 | pytest + 自定义 | PowerShell 脚本 | 各自生态 |
| 部署 | install.sh (systemd) | 绿色目录 + bat | 各自生态 |
| 依赖管理 | pip | NuGet + 手动 DLL | Win 可考虑 dotnet CLI |

---

## 六、结论

| 指标 | Linux | Windows |
|---|---|---|
| 功能完整度 | ★★★★★ (55+ 功能) | ★★★☆☆ (30+ 功能) |
| 数据深度 | ★★★★★ (RAPL/CC-CV/健康趋势) | ★★★☆☆ (基础监控) |
| UI 丰富度 | ★★★★★ (5页+曲线+可配置) | ★★★☆☆ (4页+基础曲线) |
| 代码质量 | ★★★★☆ (模块化) | ★★★★☆ (清晰分层) |
| 可维护性 | ★★★★☆ | ★★★★☆ |
| 测试覆盖 | ★★★★★ (完整套件) | ★★★★★ (15断言) |

**核心差距**：Windows 版缺少 **CPU 频率、电池深度数据、充电曲线、性能日志、场景系统** 这 5 大模块。

**互补建议**：Windows 版的进程管理、系统信息页、DPI 感知、autoclose 测试模式可反向移植到 Linux 版。

---

## 七、v4.1 取长补短实施结果（2026-08-24 追加）

> v3/v4 已补齐 CPU 频率、电池深度、充电曲线、性能日志、场景切换、CC/CV、健康趋势、
> 功耗排行、维护页、可配置布局、电池科学分析。本轮针对**剩余高价值差距**实施：

### 7.1 本轮新增（Linux → Windows 移植）

| # | 功能 | Linux 原实现 | Windows v4.1 实现 | 验证 |
|---|---|---|---|---|
| 1 | **AC/DC 自动切换** | `acdc-profile.sh` 轮询3s+冷启动归位 | OnTick 检测 PowerLine 变化→自动切到用户配置的插电/离电默认计划+气泡通知+冷启动归位 | ✅ 初始状态检测日志 |
| 2 | **负载建议器** | `load_advisor.py` ≥70%持续30s+电池场景→通知 | `LoadAdvisor.cs` 纯逻辑类(70%/30s/15min冷却)，仅建议不自动切 | ✅ 自检4用例PASS |
| 3 | **托盘场景菜单** | `tray_menu.py` 场景子菜单+状态行 | 托盘右键: 电源计划子菜单(Popup动态填充+✓标记) + 状态行(插电/离电+当前计划) + 电池分析入口 | ✅ |
| 4 | **报告导出** | `export_session.py` | 电池分析对话框"导出到文件"按钮 → 文档目录 UTF-8 txt | ✅ |

### 7.2 设置项新增（settings.ini）

| 键 | 说明 | 默认 |
|---|---|---|
| `autoswitch` | 插拔电自动切换开关 | 0 (关) |
| `acplan` | 插电默认计划 GUID | 第1个计划 |
| `dcplan` | 离电默认计划 GUID | 省电计划 |

### 7.3 判定为不移植（附理由）

| Linux 功能 | 不移植理由 |
|---|---|
| M3 离电效能模式 | 依赖 TLP/systemd，Windows 用电源计划等价覆盖 |
| GPU GT 频率联动 | sysfs 特有；Windows 下驱动不暴露同等接口 |
| nvidia PowerMizer | X11 nvidia-settings 特有；Windows 用 nvidia-smi 已覆盖监控 |
| MSR 限流状态 | 需内核驱动；LHM 已提供功耗/温度等价信息（只读铁律不破坏） |
| 基准测试 EMP | 需受控满载，违反"禁止压力测试"铁律 |
| 内核守卫/MCE | Linux 特有，不适用 |

### 7.4 当前功能矩阵结论

| 指标 | Linux | Windows v4.1 |
|---|---|---|
| 功能完整度 | ★★★★★ (55+) | ★★★★☆ (45+) |
| 数据深度 | ★★★★★ | ★★★★☆ (RAPL 子域缺失, 其余对齐) |
| 场景自动化 | ★★★★★ | ★★★★★ (AC/DC 自动+负载建议+托盘) |
| 进程管理 | ★★☆ | ★★★★★ (Win 独有保持) |

**剩余已知差异（接受）**：RAPL core/uncore/dram 子域分解（Windows 无公开接口，LHM 仅 Package）；
可配置布局为显示/隐藏（无拖拽排序，低价值）；异步采集架构（同步 tick + 有界超时已足够稳）。
