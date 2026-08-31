# THIRDPARTY.md — 第三方组件与许可清单

本仓库为**个人业余优化研究项目**，非官方、非 ACER/微软 或其任何厂商认可或背书。仓库内**不随包分发**第三方专有二进制/安装包，仅以「文档引用 + 源码/说明」形式提供；确需用到第三方二进制时请自行从其官方渠道获取。下列组件按其各自许可**并行分发**（本仓库主代码为 MIT，见 [LICENSE](LICENSE)）。

| 组件 | 用途 | 许可 | 是否随库分发 | 出处 / 说明 |
|---|---|---|---|---|
| **acer-wmi-battery 内核模块** | Linux 电池保养/充电阈值（WMI 接口） | **GPL-2.0-only** | ✅ 分发**源码备份**（含 LICENSE） | `03_Linux/性能优化方案_20260822/acer-wmi-battery_源码备份/`。社区开源内核模块源码，完整保留其 GPL-2.0 LICENSE |
| **LibreHardwareMonitorLib (LHM)** | Windows 端 CPU 核心温度/功耗等传感器读取 | **MIT** | ❌ 不分发二进制（`.dll` 已从 git 排除） | Windows 系统控制台运行时引用；请自行从官方 GitHub 获取对应版本的 DLL |
| **WinRing0** | LHM 底层 Ring0 驱动（非管理员温度读取） | **Modified BSD** | ❌ 随 LHM 分发/不作为独立文件 | 注意：微软 2025-03 起 Defender 标记 WinRing0（CVE-2020-14979）；本机 LHM 当前正常，若未来被拦，温度监控会退回 ACPI 温区路径 |
| **nvidia-smi / nvml** | 独立显卡（MX150）状态/功耗墙解析 | NVIDIA 专有工具（命令行） | ❌ 随系统附带 | 仅作为外部 CLI 调用，不随库分发 |
| **intel-undervolt** | Linux CPU/GPU 降压（-80mV） | **MIT** | ❌ 不随库分发 | 系统控制台降压场景依赖；由部署脚本独立安装 |
| **ThrottleStop** | Windows 侧功耗/睿频调节（未部署、未生效） | 专有（免费个人用） | ❌ 已排除（`02_Win/ThrottleStop_20260811/` 不入库） | 仅离线存档，非本仓库发布对象 |
| **PowerSettingsExplorer.exe** | 隐藏电源设置浏览（Windows） | 专有 | ❌ 已排除 | 仅存档引用，非本仓库发布对象 |
| **.NET Framework 4.8 / csc** | Windows 控制台编译与运行 | 微软专有（随系统） | ❌ 系统自带 | `build.cmd` 使用系统自带 `csc` 编译，零外部依赖 |

> **许可注意事项**
> - **GPL-2.0 边界**：`acer-wmi-battery` 源码备份按 GPL-2.0 独立分发，与本仓库主代码（MIT）**不构成衍生合并**。凡对该内核模块的修改/再分发均须遵守 GPL-2.0。请勿将 GPL-2.0 源码混入 MIT 主代码树。
> - **专有二进制**：仓库**不包含、不索引**任何第三方专有二进制的下载链接指向的实体文件；请勿向本仓库提交 `*.exe`/`*.dll`/`*.bin` 等第三方闭源产物。
> - Reverse-engineered / 逆向相关内容：本仓库不包含 OEM 逆向产物、转储或抓包载荷，仅保留结论与方法论（见 README「未公开内容」）。