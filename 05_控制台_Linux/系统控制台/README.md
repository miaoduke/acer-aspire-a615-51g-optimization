# 系统控制台 v1

本机可视化系统控制台（Python3 + GTK3）：系统监控 + 电源场景控制一体。

## 启动

```bash
python3 系统控制台/console.py
```
或：应用菜单 → 搜索"系统控制台"

## 安装（一次性）

```bash
sudo bash 系统控制台/install.sh
```
安装内容：
1. sudo 免密白名单（严格 3 条：场景管理.sh / m3_gui.sh / prime-select）
2. RAPL 功耗读取权限（systemd 服务，开机保持）
3. 桌面入口

## 三个页面

| 页面 | 功能 |
|---|---|
| 总览 | 温度 / CPU 功耗 / 电池 / 供电 四卡 + CPU 每线程曲线 + 实时明细（内存/GPU/PL/Turbo/EPP/PPD/Governor/电池健康） |
| 电源场景 | 6 场景一键切换（插电 3 + 离电 3，推荐高亮）+ M3 离电效能模式（进入/退出）+ 状态快照 |
| 高级控制 | 参数状态 + GPU 模式切换（intel/nvidia，需重启）+ 优化栈 7 服务状态 + MCE 记录 |

## 省电设计

- 前台 1s 采样 / 失焦 5s / 最小化暂停
- 核心采样直读 /proc、/sysfs（无子进程），GPU 每 3s
- 控制操作后台线程执行，不阻塞 UI

## 技术说明

- 控制后端：复用已验证脚本（优化脚本/场景管理.sh、backend/m3_gui.sh）
- 依赖：Python3 + PyGObject(GTK3)（Mint 自带）
- 采集：/proc/stat、intel-rapl、thermal_zone0、BAT1、nvidia-smi
- 日志：无持久化；操作结果实时对话框反馈

## 版本记录

- v1 (2026-08-19)：三页面 + 安装脚本 + 采集器（实测 CPU 功耗 4.2W 读数、温度、GPU、电池健康 81.8%）
- v1.1 (2026-08-19)：**电池真实温度显示**——打通固件 method 19（WMBE Case 0x13）SBS 温度查询，依赖 acer-wmi-battery 内核模块（已随安装部署，开机自载），sysfs 路径 `/sys/bus/wmi/drivers/acer-wmi-battery/temperature`（0444，全用户可读）。无模块时显示"—"