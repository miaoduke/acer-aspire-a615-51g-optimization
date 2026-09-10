# 经验知识库（data/knowledge/）

> 按机型/CPU 归档的实测调优数据。适配测试向导按 CPU 型号匹配推荐初始值。
> 新机器跑完 sweep 后将结果存入本目录，命名: `<类型>_<CPU代号>.csv`

## 本机档案（Aspire A615-51G / i5-8250U / Kaby Lake-R）

### undervolt 扫描结论
> ⚠️ **本节已于 2026-08-30 更新**（原文写"-80mV 不建议直接使用"，与已定稿的 -80mV 直接冲突）。
> 🟩 **2026-09-07 再更新（D7 验收通过，取代 -80mV）：** 本机定稿已推进至 **-100mV**（实测 core -99.61mV，D7 观察期 2026-09-03→09-07 验收 16/16 项全过，零死机/MCE/误触发）。下方"当前定稿 -80mV / 观察期至 09-03"为**历史记录**，已被 `data/phase1/D7_验收报告_20260907.md` 取代。*Updated 2026-09-07: final now **-100mV** (D7-accepted), superseding the -80mV record below.*
> 完整实验数据见 `性能优化方案_20260822/降压实验记录_-80mV_20260830.md`。

- **当前定稿（历史，已由 -100mV 取代）: -80mV**（core/cache/gpu 三域，实测 -80.08mV）✅ 曾持久化
- **定稿（2026-09-07 起）: -100mV**（实测 core -99.61mV；D7 验收通过，见上方横幅）
- **历史**: -50mV（多日稳定）→ **-80mV**（2026-08-30 五项场景验证全过，MCE 全 0）→ **-100mV**（2026-09-07 D7 验收）
- **-105mV**: 死机 #6（`kernel panic` MCE 广播超时）→ **禁止**；止步 -100mV
- **观察期**: -80mV 曾设 3-5 天（至 09-03）；-100mV 观察期（09-03→09-07）已如期通过
- **安全网**: `uv-safeguard` 异常关机三级判定 + `msr_deadman` 30s 巡检（95°C 回退）
- **注意**: Plundervolt 补丁状态因 BIOS 而异——新 BIOS 可能锁 MSR 0x150
- **加深流程**: 必须用 `测量脚本/uv_sweep_v2.sh`（带防护），**禁止手改服务值**

### 新机器初始值建议（与上区分：这是给"其他机器"的保守起点）
- **推荐初始值**: -50mV；观察 ≥24h 后按 25-30mV 步进
- 本机档案已推进到 -80mV，**不意味着新机器可直接套用**

### bench 场景对比（bench_compare_results_backup.csv）
| 场景 | PL1 | EPP | Governor | 吞吐量 |
|------|-----|-----|----------|--------|
| ac-perf | 25W | performance | performance | ~1600 万/s 基线 |
| ac-bal | 15W | balance_performance | powersave | 中等 |
| bat-save | 10W | power | powersave | 受限 |

### 已验证的固件/硬件边界（勿重复踩坑）
- ❌ 充电上限：固件 WMI health 不支持（dmesg unexpected length 4）
- ❌ 风扇控制：fan_boost=死机4 操作；acer-wmi PWM 仅 Predator
- ❌ PSR：Kaby Lake-R 死机 bug（fdo#112159）
- ❌ 刷新率降级：EDID 仅 60Hz + crtc failed
- ❌ FBC：面板不支持
- ✅ C-state=6：可用但 C8 待机闪烁关联 → 回滚至 max_cstate=4
- ⚠ csd-power 亮度管理有拉锯 bug → helper 已改名禁用（重装后如复发重复此操作）

## 移植到其他同配置机器（A615-51G 同款）检查单
1. `sudo bash backend/adapt_test.sh apply` — 硬件探测+档案
2. 对照本文件"边界清单"确认固件行为一致
3. undervolt 从 -50mV 开始，禁止直接套用深降压
4. C-state 从 max_cstate=4 起步，观察后再放开
5. 跑 `backend/kernel_guard.sh check` 确认功能栈完整

## 不同 CPU 代际的适配提示
- **8代 Kaby/Coffee Lake**: 本文档全部适用
- **11代+ Tiger Lake**: Panel Replay 可用（替代 PSR）；undervolt 大概率被锁
- **AMD**: RAPL 路径不同（amdgpu），intel_pstate 不存在 → 用 amd_pstate+EPP

## 网络 WiFi 省电调研（网络省电调研_20260827.md）
> 2026-08-31 补入索引：该文件此前仅存在于控制台的另一份副本中，**本目录从未收录且无人引用**，易丢失。

- 对象: QCA9377 / ath10k 无线网卡
- 结论要点见原文件；涉及 `iw` 命令可用性的部分需注意：
  `backend/thermal_ctl.sh` 已于 2026-08-20 修复「原用 `iw` 命令不存在导致静默失败」，
  改用 `/usr/sbin/iwconfig`。引用本调研时请以修复后的实现为准。

## 补充定案（2026-08-22 三项调研）
- **屏幕颜色省电**: LCD 背光恒定，黑白/暗色主题实测零差异（±0.04W 噪声级）。本机无 CABC/CABLC/DPST。省电唯靠背光亮度。
- **漏洞即能力穷尽**: Plundervolt(MSR 0x150)=已用满(-50mV)；BD PROCHOT(0x1FC)=死机史不做;PL锁单向无效;ME/Spectre 类无硬件调控价值。无遗漏能力。
- **0817 快照**: 定位=保底回滚点+适配测试基线。测试规程见"铁律更新"节。

## 生态清单格式约定（2026-08-22 起）
以后所有生态整理统一使用四态分类：
【实现】已落地且实测生效 | 【未实现】有依据放弃或固件不支持
【待做】条件触发或有价值待排期 | 【监测中】观察期验证的变更项
