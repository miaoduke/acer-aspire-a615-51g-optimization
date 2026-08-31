# AI 自主科学优化 SOP v1.0（自包含版）【Linux 专用】

> **用途**：本文件可在**全新 AI 对话**中直接发送（无需任何前置上下文），
> 驱动 AI 安全、科学地完成一台 **Linux** 笔记本的 CPU 电源/性能优化全流程。
> 本 SOP 仅适用于 **Linux**（sysfs/systemd/msr-tools 工具链）；Windows 侧需另写版本
> （等价工具：ThrottleStop/XTU + powercfg，决策逻辑可复用本 SOP）。
> 参考机型：Acer Aspire A615-51G / i5-8250U（KBL-R 4C8T，15W TDP）
> 但本 SOP 内所有**判定逻辑**适用于任意 Intel/AMD Linux 笔记本，仅参考值与阈值需按第 2 节识别替换。
>
> **配套文档**（非必需，有更好）：同目录 `科学优化方案_v2_20260812.md`（17 节完整实测档案）、
> `bench_compare_results.csv`（历史数据）、`数据来源与参考.csv`（外部来源链接）。
>
> ⚠️ **2026-08-17 定稿更新声明**（⚠️ 本节与下方 08-18 声明**均已被 2026-08-29 三次更新覆盖**，
> 其 -105mV / -100mV / max_cstate=1 / intel-undervolt 四项均已错，**请直接跳读三次更新**）：
> 本文所有"本机结论/参考值"（如 PL1=15W 最优、
> 降压 -50mV 保守、满载 88-90°C 散热顶）均为 **2026-08-13 换硅脂前** 的结论。
> 换硅脂后散热顶降至 ~60°C，**当前定稿以 `00_交接手册_重装后启动.md` 为准**：
> PL1=PL2=**25W** / 降压 **-105mV** / 4 服务（cpu-power-limit, turbo-enable, intel-undervolt,
> acdc-profile）/ GRUB `intel_idle.max_cstate=1`（Acer 死机修复）/ prime-discrete=off。
> 本文的**流程/协议/安全红线仍然有效**，仅"本机结论"过时。
>
> ⚠️ **2026-08-18 定稿二次更新（务必先读）**：
> - **降压 -105mV → -100mV**：08-18 死机 #6（首次 AC，kernel panic MCE 广播超时，符合 12.1"满载后冷却期冻结"模式）
>   触发 12.4 规则"冻结则退回"，已回退并复测稳定（1707.2万/s @71°C）。
> - **prime-discrete=off → on（带电默认独显）**：用户决策（nvidia 挂起风险知悉）。
> - **kernel.panic=10** 已加（panic 自动重启）。
> - **三电源模式方案**（M1 极致/M2 均衡/M3 效能）已实测定稿，见 `三电源模式方案_20260818.md`；
>   死机 #6 完整调查见 `死机调查_20260818.md`。
>
> ⚠️ **2026-08-29 定稿三次更新（真机实测校正，覆盖前两次）**：
> 前两版声明中的"降压 -100mV / C-state=1 / 服务名 intel-undervolt"**三项均错**，
> 与真机实测不符。以 `sudo undervolt --read` + `/etc/systemd/system/undervolt.service` +
> `/etc/default/grub` 三方印证后的**真值为准**：
> | 项 | 前版声明 | 真机实测 |
> |----|---------|---------|
> | 降压 | -100mV | **-50mV**（实测 core/gpu/cache = -49.8mV） |
> | C-state | max_cstate=1 | **=4** |
> | 服务名 | intel-undervolt | **undervolt**（+ undervolt-resume） |
> | 降压工具 | intel-undervolt(C版) | **`undervolt`(Python 版, `/usr/local/bin/undervolt`)** |
> | PL1/PL2 | 25W/25W | ✅ 确认（回读 25.0W/25.0W） |
> | Turbo | ON | ✅ 确认（`turbo: enable`） |
>
> **本文流程/协议/安全红线仍然有效**；仅"本机参考值"按上表替换。
> 另：C-state 演进为 9→1(0817)→9(0818 撤销**失败**)→1(0820)→6(0821)→**4(现状)**，
> 每一步均由死机证据驱动，勿凭旧文档回退。

---

## 第 0 章 AI 工作准则（必读）

1. **每次修改系统前**，先向用户展示「现状 vs 建议」对比表，**得到明确同意后才执行**。
2. **每个高风险操作**（降压/MSR/GRUB/服务安装）前，先展示回退路径，确认用户知情。
3. **测试纪律**见第 2.4 节安全红线，任何违反 → 立即中止并冷却，绝不含糊。
4. **单向顺序执行**：基线 → PL → Turbo → 降压 → 其他。不得跳跃。
5. 所有写入值、回读值、测试数据**原样记录**到 CSV（格式见第 8 节），不推测填充。
6. 每个优化项完成后：实测验证 → 更新对比表 → 询问"是否持久化/保留"。
7. **回退优先于前进**：任何操作失败或异常，先恢复原值，再分析。
8. 用户环境可能在任何时刻重启 —— 数据盘挂载、sudo 凭证、后台进程均会变化，**每次恢复操作后重新检查环境**。
9. **场景维度**：优化结果分「AC 带电 / DC 离电 / 安静 / 极致性能」多场景呈现（见 4.8 章），
   AC 实测结论**不得直接套用到电池场景**——离电数据必须实测补齐（4.8.3 协议）后才可给出离电方案。
10. **会话备份原则（最高优先, 先备份后动手）**：**每次执行下一个新任务前**，必须先运行
   `会话备份/00_保存会话与日志.sh`（可带任务说明参数），把「本 AI 会话内容 + 系统实时日志
   （journalctl/dmesg/重启记录/电源快照/服务状态/降压MSR/配置/项目数据快照」保存到
   `性能优化方案/会话备份/<时间戳>/`。任何系统修改（含测试）之前必须已有可查验的备份；
   重装系统后以此快速查验问题并续接研究。详见第 13 章。

---

## 第 1 章 目标系统识别（第一步，5 分钟内完成）

```bash
# 1. 系统/内核
cat /etc/os-release | grep PRETTY
uname -r
# 2. CPU
grep -m1 "model name" /proc/cpuinfo
lscpu | grep -E "^(CPU\(s\)|Model name|Thread|Core)"
# 3. 功耗墙
ls /sys/class/powercap/ | grep rapl        # 无 rapl = 无法功耗测量(虚拟化/AMD 部分型号)
cat /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw  # PL1
cat /sys/class/powercap/intel-rapl:0/constraint_1_power_limit_uw  # PL2
# 4. 调速器/EPP
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
cat /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference
# 5. Turbo 状态 (Intel)
sudo rdmsr -f 38:38 0x1a0          # 1=Turbo 关, 0=开 (需 msr-tools)
# 6. 温度源
sensors | grep -A2 "Package"        # 确认 coretemp 输出格式
# 7. 工具
for t in turbostat stress-ng rdmsr sensors powerprofilesctl intel-undervolt; do which $t >/dev/null 2>&1 || echo "缺: $t"; done
# 8. BIOS/安全启动 (决定降压可行性)
sudo dmidecode -s bios-version
sudo mokutil --sb-state 2>/dev/null || echo "secure boot 工具未装, 视为未知"
```

**识别产物（写进 CSV 第 8 节）**：
机型 / CPU 代际 / 内核版本 / BIOS / SecureBoot / PL1 / PL2 / governor / EPP / Turbo / 工具齐全与否。

---

## 第 2 章 安全红线与测试协议（最高优先级）

### 2.1 安全红线（违反 → 立即中止测试，冷却 ≥120s）

| 红线 | 阈值（参考机型） | 说明 |
|------|----------------|------|
| 起始满载温度 | **>75°C 禁止开跑** | 热态满载 = 热积累 + 尖峰叠加, 崩溃风险 |
| 测试中温度 | **>92°C 立即停止** | 此机型 crit=100°C, ≥92°C 停止余量不够 |
| 紧急熔断 | **>95°C 无条件 sleep 120s** | 曾实测 98-99°C 尖峰 1-2s 即崩机 |
| 轮间冷却 | **≥45s**（温升 <5°C 时 ≥10s） | 曾测连续满载 -44% 且逼近断电 |
| 单轮满载 | **≤60s**（长测分 3 段，段间冷却） | — |
| 降压 | 首轮 **-50mV**，稳定后再 ±25mV 步进 | 上限与 CPU 代际相关（见 6.3） |
| MSR/Sysfs 写入 | 先记录原值，再写 | 写后必回读确认 |

**本机（i5-8250U）的已知事实**：满载 15W 稳态 88-90°C = 散热极限；crit=100°C；
**PL2=44W 短时突刺可在 1-2s 内冲到 98-99°C**（曾致硬关机）——所以 PL2 与 PL1 同等重要（见第 5 章）。

### 2.2 测试采样协议

```bash
# 1s 采样循环 (bg) + 满载 (fg), 20s:
( for i in $(seq 1 20); do
    T=$(sensors -u coretemp-isa-0000 2>/dev/null | awk '/Package id 0:/{f=1;next} f&&/temp1_input/{print $2;exit}')
    F=$(awk '{s+=$1;n++} END{if(n)printf "%.0f", s/n/1000}' /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq)
    echo "t=${i}s ${F}MHz ${T}°C"; sleep 1
  done ) &
SAMPLER=$!
stress-ng --cpu $(nproc) --timeout 20s
wait $SAMPLER
```

**关键教训（采样间隔）**：turbostat 默认 5s 采样会**平滑掉 1-2s 的 98°C 尖峰**，
全部历史误判因此而来。**任何热测试必须 1s 采样**（上方模板）。

**变量控制（2026-08-15 新增，必记两项）**：
1. **环境温度**：测试前后记录 `sensors | grep -A3 acpitz` 值（本机 27-30°C）。
   室温每升 1°C ≈ CPU 满载升 ~0.95°C，且**不能线性修正**（节流非线性）。
   前后对比环境差 >2°C 必须注明，否则结论无效。
2. **GPU 状态**：测试前后记录 `nvidia-smi --query-gpu=utilization.gpu,temperature.gpu`。
   本机 MX150 与 CPU **共享单热管**，独显活跃时挤占 CPU 散热（证据：GitHub
   thinkpad-firmware-patches #56 / LTT / Acer 社区）。前后对比必须 GPU 同态。

### 2.3 后台干扰判别

- 测试前 `ps aux --sort=-%cpu | head -5`，任何 >10% CPU 的进程需处理（renice 19 / 绑核 / 等结束）
- **判定法**：满载轮温升 <15°C 且吞吐 <预期 60% → 后台抢负载, 数据作废重测
- 常见污染源: OpenCode(本次 44%+)、rsync、fwupd、浏览器、flatpak 更新

### 2.4 功耗测量

```bash
# RAPL 能量差 (需 root): (E1-E0)/1e6/秒数 = W
E0=$(sudo cat /sys/class/powercap/intel-rapl:0/energy_uj)
stress-ng --cpu $(nproc) --timeout 20s
E1=$(sudo cat /sys/class/powercap/intel-rapl:0/energy_uj)
awk "BEGIN{printf \"%.1f\", ($E1-$E0)/1000000/20}"
```

---

## 第 3 章 基线测试（任何优化前的"初始画像"）

1. 等温度 **≤65°C**（`sensors` Package）
2. 跑 2.2 模板 20s 满载 × 2 轮（轮间冷却 45s），取均值
3. 记录 CSV：配置=「出厂/当前」、吞吐、温度起止、频率范围

**参考值（i5-8250U）**：
| 配置 | 吞吐(LCG 万/s) | 温度 | 备注 |
|------|---------------|------|------|
| 出厂(15W+Turbo关) | ~765 | ≤68°C | 固件默认关 Turbo |
| 15W+Turbo开 | ~1297-1320 | 88-90°C | 热平衡点 |
| +降压 -50mV | ~1370 | 87-89°C | +5.5% |

（吞吐 = LCG 8 线程 20s 的 total/20/1e4；不同 bench 不可直接比较，**必须同工具同比**）

---

## 第 4 章 优化流程（按顺序，逐项决策）

### 4.1 阶段 A —— PL1/PL2 功耗墙

**原理**：RAPL 是"窗口能量预算"而非瞬时限制。
- PL1(long_term) 窗口 ~28s，允许 28s 内透支 → 15W 墙下实测整周期功耗可达 22W
- PL2(short_term) 窗口 ~2.4ms，**瞬时允许 44W → 满载启动 1-2s 内 98-99°C 尖峰（崩溃电源）**
- sysfs 写权限：`echo 瓦数x1000000 > /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw`

**操作**（建议值 = 15W/15W；25W 仅当散热条件证明有余量后）：
```bash
echo 15000000 | sudo tee /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw
echo 15000000 | sudo tee /sys/class/powercap/intel-rapl:0/constraint_1_power_limit_uw
# 验证回读与满载尖峰: 1s 采样满载 20s, 尖峰 ≤90°C 即通过
```

**决策点**：
- 若满载温度峰值 ≤85°C → 可试 PL1=25W（保持 PL2 与原 PL1 同值），重测对比收益
- 若收益 <3% 或温度逼近 90°C → 保持 15W（本机实测 25W 无增益：热顶限制）
- **持久化**：systemd 服务（oneshot 写两值），回退 = disable 服务

**本机结论**：PL1=PL2=15W 为最优（25W 在散热顶下无增益）。

### 4.2 阶段 B —— Turbo 状态（Intel）

**原理**：MSR 0x1A0 bit38=Turbo Disable。**本机实测开机后 EC 会在桌面初始化阶段把它重置为 1**
（一次性服务会失效，需要守护进程：每 30s 检查非 0 即修复，日志化）。

```bash
# 查询/开启
sudo rdmsr -f 38:38 0x1A0                      # 1=关
sudo bash -c 'v=$(rdmsr 0x1a0); wrmsr -a 0x1a0 $(( 0x$v & ~(1<<38) ))'
# 验证: 满载 2s, scaling_cur_freq 应 > 1.6GHz(基准)
```

**决策点**：
- 开启后实测满载温度若 ≤90°C（PL 已 15W）→ 保留并持久化（守护）
- AMD/无 RAPL 老平台 → 跳过或改用 `cpupower` / BIOS
- Turbo 开收益巨大（本机 +50-74%），**绝大多数情况值得守护**

**本机结论**：守护方案（`turbo-guard.sh` + systemd simple 服务）实证必要且有效。

### 4.3 阶段 C —— Governor / EPP

**原理**：intel_pstate active + HWP 下，governor=powersave + EPP 决定能效偏好。
EPP 写 `energy_performance_preference`（每核）。

**操作**：
```bash
echo balance_performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference
```

**决策点**：
- 满载吞吐三档对比（performance / balance_performance / power）差 <3% → **保持默认**
- 空载/日常场景若想省电 → power 只在**非满载**下有意义（本机满载 power 反而能效最低）
- **不单独持久化**：由 power-profiles-daemon 管理即可，手动写仅测试用

**本机结论**：三档满载无差异（差 <1% 冷态）；balance_performance 为最优默认。

### 4.4 阶段 D —— 降压 undervolt（高风险，需逐级验证）

**前置**：
- Intel 8/9 代正常可用；**10 代+(KBL 后) 部分锁死**；AMD 无此机制
- Secure Boot 若启用：可能需要 mok 或回退（先确认, 通常禁用即可）
- 工具：intel-undervolt / throttled / undervolt(GUI)

**分级流程**（每级执行 2.2 协议 20s + 2.4 功耗, 无 MCE 才继续）：
```bash
# 配置 /etc/intel-undervolt.conf (该工具格式):
#   undervolt 0 "CPU" -50
#   undervolt 1 "GPU" -50
#   undervolt 2 "CPU Cache" -50      # Cache 必须与 CPU 同步或更低
#   undervolt 3 "System Agent" 0     # SA 保守
#   undervolt 4 "Analog I/O" 0
sudo intel-undervolt apply && sudo intel-undervolt read   # 回读确认
# 验证: MCE 检查 (dmesg | grep -i mce) + 满载 + 长测 3x60s
```

**决策点（每级停下问用户）**：
| 级别 | 适用场景 | 预期收益 |
|------|---------|---------|
| -50mV | 散热差/保守（本机） | +5-6% |
| -75mV | 散热尚可 | +8-12% |
| -100mV | 散热好/确认体质 | +15-25%（可低于同频功耗） |
| -125mV+ | 仅极限(开盖/水冷) | 高风险 |

**本机结论**：-50mV 通过 3×60s 零 MCE；-100mV 曾验证（历史），清灰前不激进。

**持级回退**：`intel-undervolt` 改回 0 + apply；系统服务 disable。

### 4.5 阶段 E —— mitigations（安全权衡，默认不做）

**实测评测（i5-8250U）**：纯计算 +2-4%（浏览器/IO 类或许 5-10%），但 **14 项漏洞全暴露**。
**决策点**：家用单机情报价值低时可不做；任何联网/多用户场景**不做**。
若做：GRUB 临时验证 (`linux 行尾加 mitigations=off` → 重启 → `cat /sys/devices/system/cpu/vulnerabilities/*`) 
→ 有显著收益再永久化（`/etc/default/grub` 改 cmdline + `update-grub`）。
**本机结论：否决（收益不值得风险）。**

### 4.6 阶段 F —— 硬件（清灰/换硅脂）

**必要性判断**：满载稳态温度 ≥85°C → 散热是瓶颈，软件优化到顶。
**预期**：硅脂老化/积灰, 清灰后通常 -10~15°C → 解锁 25W、更深降压的潜力。
**提示用户**：本机风扇无 PWM 控制接口（nbfc 不可用），清灰是唯一降温手段。

### 4.7 阶段 G —— 新装系统恢复（优化栈重建清单）

> ⚠️ **2026-08-29 实测校正**: 上一行定稿值已过时（降压 -105mV 为**死机 #6 元凶**）。
> **当前真值: PL1=PL2=25W / 降压 -50mV / C-state=4 / 服务 `undervolt`(+`undervolt-resume`)**。
> **重装后请直接运行 `00_重建优化栈.sh`(一键重建+自动验证), 勿按下方旧清单手工重建。**

若系统重装，以下全部失效，按此重建（**本机已验证的服务版**）：
1. 重装工具: `apt install -y linux-tools-common linux-tools-generic msr-tools lm-sensors` + `pip install undervolt`
   （⚠️ 本机用 **Python 版 `undervolt`**（`/usr/local/bin/undervolt`），**非** C 版 `intel-undervolt`；
   后者本机未安装，本文 7.C 旧模板按其格式书写，本机请勿照抄）
2. 创建服务（内容见第 7 节 A/B/C 模板）：cpu-power-limit / turbo-enable / **undervolt** / **undervolt-resume**
3. `systemctl enable --now` 前三者，`systemctl enable` undervolt-resume（由 suspend.target 触发）
   → 重启验证矩阵（第 7 节）
4. 复测基线 ≥ 优化前 90% 即视为重建成功
5. 复核：`sudo undervolt --read` 应显示 core/gpu/cache = -49.8mV 且 `turbo: enable`

---

## 第 4.8 章 使用场景矩阵（供电状态 × 性能需求 × 噪音）

> ⚠️ **本章状态标注**：本机（A615-51G）**AC 场景已全部实测**（☑），
> **离电/电池场景尚未实测**（☐）——SOP 要求：离电数据必须先按 4.8.3 协议实测补齐，
> 再按本章建议调整，**不得直接沿用 AC 结论**（电池供电下 PL/EPP/Turbo 行为可能不同，见 11.3 节）。

### 4.8.1 场景定义（用户使用意图 → 配置方案）

| 场景 | 意图 | 供电 | 核心需求 | 方案组合 | 本机实测状态 |
|------|------|------|---------|---------|------------|
| **S1 带电·极致性能** | 编译/渲染/测试 | AC | 最高吞吐 | balanced/performance + Turbo ON + PL=15W/15W + 降压 -50mV | ☑ 1370.9万/s, 88°C |
| **S2 带电·均衡日常** | 桌面/浏览器/办公 | AC | 响应快+安静 | balanced + Turbo ON + PL=15W/15W + 降压 | ☑ 1297万/s |
| **S3 带电·安静低载** | 阅读/文档/观影 | AC | 静音、低发热 | powersave + EPP=power + 限制 max_freq（如 1.6GHz） | ☑ 锁频 800MHz 时 405万/s |
| **S4 离电·续航优先** | 移动办公/通勤 | 电池 | 最长续航 | power-saver + Turbo OFF + PL 降为 8-10W（实测确定） | ☐ 未测 |
| **S5 离电·均衡** | 移动轻度办公 | 电池 | 续航+可用性 | balance_power + Turbo ON(短时) + PL=15W | ☐ 未测 |
| **S6 离电·极致续航** | 紧急/会议录播 | 电池 | 极限时长 | power-saver + 屏暗 + 飞行模式 | ☐ 未测（可沿用 PPD 默认） |

### 4.8.2 场景切换工具（无需重启）

```bash
# 场景级一键切换 (基于 power-profiles-daemon, 即时生效)
powerprofilesctl set performance   # S1
powerprofilesctl set balanced      # S2/S5
powerprofilesctl set power-saver   # S3/S4/S6 (更节能: 加 EPP=power + 限频)

# 进阶: S3 手动限频 (需 root)
echo 1600000 | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_max_freq

# 进阶: S4/S5 电池场景下临时降 PL (需 root, 重启失效——如需持久化写 systemd 服务)
echo 10000000 | sudo tee /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw
```

**AC/电池自动联动**（推荐持久化，可选）：Power-Profiles-Daemon 本身不区分供电状态，
如需"插电=balanced、离电=power-saver"自动切换，用 systemd 服务监听 AC 事件
（`/sys/class/power_supply/AC*/online` 变化触发 `powerprofilesctl set`）。

### 4.8.3 离电场景实测协议（S4/S5 必做，补齐数据）

> 电池供电下测试安全注意：**单轮满载 ≤20s、轮间冷却 ≥120s**（电池供电散热更差+避免深度放电；
> 测试前确认电池 ≥80%）。测试结论只用于「离电场景配置」，与 AC 数据分开记录（备注列标 DC）。

```bash
# 1. 确认在电池供电 (输出应为 0)
cat /sys/class/power_supply/AC*/online
# 2. 电池状态下跑 2.2 模板 20s 满载, 记录吞吐/温度/频率
# 3. 对比三档: power-saver / balanced / performance (按 12.1 节 AC 三档方法)
# 4. 记录 CSV: 配置列=DC_xxx, 供电列=DC
# 5. 额外测试: 电池下 PL=10W 与 PL=15W 的吞吐差 (决定 S4 是否值得降 PL)
```

**预期参考（未验证, 需实测）**：电池下 EPP/Turbo 行为可能由 EC 直接接管（厂商策略），
实测若发现「电池下 Turbo 自动关/频率锁低」→ S4/S5 的配置重点转为**调 PL 而非调 EPP**。

### 4.8.4 安静场景补充（S3）

本机风扇**无 PWM 控制**（nbfc 不可用，EC 固件自管），软件层面降噪手段只有两个：
1. 限频限功耗（S3 组合：EPP=power + max_freq=1.6GHz → 满载 ~405万/s 但温度 62°C 风扇低速）
2. 后台负载控制（renice/taskset 绑定，避免单核突发拉高风扇）

### 4.8.5 场景决策流程

```
用户说明当下使用场景/供电状态
   ↓
查 4.8.1 矩阵对应行 → 若 ☐ 未测 → 先跑 4.8.3 补测(问用户是否接受短时电池测试)
   ↓
执行配置 (4.8.2) → 用户实感体验 10 分钟 → 询问是否满意
   ↓
满意 → 如需自动切换写 AC 联动服务; 不满意 → 回退到前一场景配置
```

---

## 第 5 章 判定逻辑速查（决策树）

```
基线(3章) → 记录
   ↓ 温度上限?
满载峰值 ≥92°C ──是──▶ 先硬件清灰(阶段F), 拒做任何功耗提升
   ↓ 否
阶段A PL1=15W PL2=15W(必做, 防突刺)
   ↓ 满载 ≤85°C? ──是──▶ 试 PL1=25W 对比, 有收益且≤88°C 则保留
   ↓ 否(保持15W)
阶段B Turbo: rdmsr 0x1A0 bit38 ──1──▶ 开启+守护
   ↓
阶段C EPP 三档对比 ──差<3%──▶ 保持默认
   ↓
阶段D 降压 -50mV → 无MCE → (询问)持久化
   ↓ 用户同意纵深
   -75mV → -100mV (逐级)
   ↓
阶段E mitigations: 渗出公式 收益/风险 → 默认否决
   ↓
输出最终方案表 + 回退手册
```

---

## 第 6 章 跨环境适配（新机器如何套用本 SOP）

| 参数 | 本机(i5-8250U) | 适配方法 |
|------|---------------|---------|
| PL1 初始 | 15W | 默认**不高于 CPU 标称 TDP**；TDP 未知查 `cpufreq`/上盖标签 |
| PL2 初始 | 15W(=PL1) | **始终先设 =PL1**, 再单独实验提升 |
| 满载限温 | ≤88°C | 通用: 满载启动温度 ≤75°C, 峰值 ≤90°C |
| Turbo MSR | bit38 需守护 | 部分平台 BIOS 可持久; 守护版本通用无害 |
| 降压上限 | -50 保守/ -100 已验 | 8-9 代 ≤-100; 10 代+大概率锁死跳过; 台式/散热好可更深 |
| EPP 三档 | 无差异 | 普遍适用于 intel_pstate 驱动 |
| 是否支持 RAPL | 是 | AMD Zen2+ / Intel 全系通常支持; 虚拟化/服务器需确认 |

**新环境必测项（逐条跑 2.4 节, 先跑再说话）**：
①习惯用 1s 采样的尖峰 ②PL2 写 =PL1 后的尖峰消失与否 ③降压 20s 稳定
→ 三个都通过, 才进入「决策点」。

---

## 第 7 章 服务模板（可复制, 已在本机验证）

### 7.A cpu-power-limit.service
```ini
[Unit]
Description=PL1/PL2 功耗限制 - 防 44W 突刺过热
After=multi-user.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'echo 15000000 > /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw; echo 15000000 > /sys/class/powercap/intel-rapl:0/constraint_1_power_limit_uw'
[Install]
WantedBy=multi-user.target
```

### 7.B turbo-enable.service（守护, 防 EC 重置）
```ini
[Unit]
Description=Turbo Enable guard - MSR 0x1A0 bit38=0 持续守护
After=multi-user.target
[Service]
Type=simple
ExecStart=/usr/local/bin/turbo-guard.sh
Restart=on-failure
[Install]
WantedBy=multi-user.target
```
```bash
# /usr/local/bin/turbo-guard.sh
#!/bin/bash
sleep 15
while true; do
  if [ "$(/usr/sbin/rdmsr -f 38:38 0x1a0 2>/dev/null)" != "0" ]; then
    v=$(/usr/sbin/rdmsr 0x1a0 2>/dev/null || echo 0)
    /usr/sbin/wrmsr -a 0x1a0 $(( 0x$v & ~(1<<38) )) 2>/dev/null || true
    echo "$(date +%H:%M:%S) Turbo 被重置, 已修复" >> /var/log/turbo-guard.log
  fi
  sleep 30
done
```

### 7.C undervolt.service（降压）— 2026-08-29 按真机实测校正
> ⚠️ 原模板用 C 版 `intel-undervolt`（`/usr/bin/intel-undervolt apply`），
> **本机未安装该工具**；本机实际用 **Python 版 `undervolt`**（`/usr/local/bin/undervolt`）。
> 两者命令格式不同：C 版需先写 `/etc/intel-undervolt.conf` 再 `apply`，
> Python 版直接命令行传参。下方为本机**已在用**的真实单元。

```ini
# /etc/systemd/system/undervolt.service
[Unit]
Description=Intel CPU undervolt (MSR 0x150)
After=multi-user.target
[Service]
Type=oneshot
ExecStart=/usr/local/bin/undervolt --core -50 --cache -50 --gpu -50 --temp 98
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
```
```ini
# /etc/systemd/system/undervolt-resume.service
# MSR 掉电易失: 缺此服务会导致挂起/休眠唤醒后降压静默失效
[Unit]
Description=Re-apply undervolt after suspend/resume (MSR is volatile)
After=suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target
[Service]
Type=oneshot
ExecStart=/usr/local/bin/undervolt --core -50 --cache -50 --gpu -50 --temp 98
[Install]
WantedBy=suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target
```

### 7.D 重启验证矩阵（重建栈后必跑）
```bash
cat /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw   # 25000000 (25W)
cat /sys/class/powercap/intel-rapl:0/constraint_1_power_limit_uw   # 25000000 (25W)
sudo rdmsr -f 38:38 0x1a0                                          # 0
sudo undervolt --read                                              # core/gpu/cache -49.8mV, turbo: enable
cat /sys/module/intel_idle/parameters/max_cstate                    # 4
tail -2 /var/log/turbo-guard.log                                   # 有修复记录=在工作
systemctl status cpu-power-limit turbo-enable intel-undervolt      # 均 active
```

---

## 第 8 章 数据记录格式（CSV）

```csv
时间戳,配置,供电,电池%,governor,EPP,PL1W,PL2W,Turbo,降压mV,备注,吞吐万/s,起点温度,终点温度
2026-08-13_12:47,UV50_8core,AC,100,powersave,balance_performance,15,15,ON,-50,isolated6,1370.9,79.000,
```

字段说明：`配置`=人类可读标签；`备注`=隔离方式/后台情况；吞吐=LCG total/20/1e4。
文件：`bench_compare_results.csv`（增量追加，永不覆盖）。

---

## 第 9 章 汇报模板（每阶段结束时向用户输出）

```
【阶段 X：<名称>】
  现状: <当前值/表现>
  建议: <改动 + 依据 + 风险 + 回退>
  ── 用户决策 ──┐
                ├─ ① 执行  ② 跳过  ③ 调整（说明怎么调）
```

最终交付：**优化前后对比表 + 持久化清单 + 回退手册**，
明确告诉用户"哪些是测试性的、哪些已持久化、哪些下次重启会丢"。

---

## 第 10 章 风险矩阵（写进每份报告尾部）

| 风险 | 可能 | 影响 | 缓解 |
|------|------|------|------|
| 降压过深死机 | 低(~5%) | 重启即恢复(降压不持久) | 逐级验证, 每级 3x60s+MCE 查 |
| 误改 MSR | 低 | 需要重启恢复 | 先存原值(rdmsr 记录), wrmsr 精确 |
| 满载热崩溃 | 中(高负载时) | 伤硬件/丢数据 | 红线+1s 采样+守护 |
| 数据盘未挂 | 高(每次重启) | 测试基路径失效 | 先验证 `ls /media/<USER>/Public/AItest` |
| 后台污染 | 高 | 数据失真 | 每轮前 ps 检查 + 隔离/降权 |
| GRUB 改错进不了系统 | 低 | 恢复: GRUB 菜单高级恢复/ live USB | 只改建议参数, 勿删原行 |

*SOP v1.0 生成: 2026-08-13 (Linux 专用) | 依据: 科学优化方案_v2_20260812.md 全程 17 节实测档案 (本项目独有经验) + 数据来源与参考.csv 外部来源 | 场景矩阵 4.8 章: AC 场景已实测, DC 场景待按 4.8.3 协议补齐*
---

## 第 11 章 ⚠️ 事故教训（2026-08-13 超压事故，最重要）

### 11.1 事故：-120mV 测试时脚本丢失负号 → +120mV 超压

- 现象：应用 +120mV 后系统满载死机；强制重启后多次进不了系统（service 开机自动应用超压值 → 崩溃循环）
- 根因：脚本用裸变量 `$MV` 拼接 conf，`mv=120` 时生成 `undervolt 0 "CPU" 120`（正值=超压）

### 11.2 永久规则（测试脚本/手动均须遵守）

1. **电压只允许负值**。任何 unsigned 正值一律拒绝。脚本内强制 `-${MV}` 前缀，数值只取 |mv|
2. **conf 生成三连校验**：写入 → `grep -E 'undervolt [0-9]+ "[^"]+" -[0-9]+'` 校验全负 → 才 apply
3. **apply 后回读**：`intel-undervolt read` 首行必须含 `-`，且数值与预期一致
4. **每档测试结束立即恢复 conf 为已验证安全值**（本机 -100mV）并 apply，防止 service 下次开机应用测试档
5. **电压上限**：降压 ≤200mV 封顶，超限拒绝
6. **禁止任何形式的正电压测试**：超压会损坏硬件（不可逆），测试现场保留 conf 备份（`conf.bak-*`）一条
7. **MCE > 0 立即停**：恢复安全值并报告用户，绝不继续测试

### 11.3 脚本模板（含防护，可直接复用）

```bash
MV_RAW=${1:?}; MV="${MV_RAW#-}"                     # 去负号
case "$MV" in ''|*[!0-9]*|0) exit 1;; esac         # 仅正整数
[ "$MV" -gt 200 ] && exit 1                        # 上限
MV_SIGNED="-${MV}"
cat > /etc/intel-undervolt.conf << EOF            # 写入(永远负值)
undervolt 0 "CPU" $MV_SIGNED

---

## 第 12 章 经验补充（2026-08-13 定稿过程教训）

### 12.1 冻结是概率性的，10轮通过≠可靠
- -110/-115 均"10轮复测 0 MCE 通过"，但随后终验冻结
- **冻结时机特征：发生在满载后的空闲/冷却期**（空闲时电压请求最低，降压偏移易跌破阈值）
- 判定规则：任何档位出现一次冻结即判定不可用（-110/-115 均被此规则淘汰），不要因"之前通过"而保留

### 12.2 后台 CPU 占用会污染 bench（15W 墙下尤其严重）
- 事故：opencode 客户端(自身UI)占 ~60% 单核 → bench 数值 -4.5%
- **任何后台进程(包括测试者自己的 AI 客户端)都会偷走功耗预算**
- 规则：测试前检查后台总 CPU 占用 ≤15%（uv_sweep.sh 已内置检测）；测试期间不进行其他操作
- 判定：同档位两次测量差 >2% 时，先怀疑后台污染而非电压差异

### 12.3 冷机首轮数据不可作基准
- 冷机(低温)首轮会虚高（如 1531.8 vs 稳态 1486），因温度低+频率冲高
- 规则：取中位数而非最大/首轮；冷机首轮可标记排除

### 12.4 本机最终档位（2026-08-13 定稿）
- **-105mV**（CPU/GPU/Cache），复测 1486.2万/s，+14.6% vs 基线
- 备份: /etc/intel-undervolt.conf.bak-50mv（-50 保守档）
- 观察期: 1 周；冻结则退回 -100

---

## 第 13 章 会话备份与日志留存原则（2026-08-15 新增, 制度级）

> 背景：2026-08-13 超压事故后总结——「当时会话内容/实时日志散落在各处, 重装系统后将无从查验」。
> 本原则为制度级：**任何 AI 会话/人工操作, 在开始下一个新任务前必须先执行备份**。

### 13.1 备份时机（铁律）

| 时机 | 必须执行 |
|------|---------|
| **每个新任务开始前**（含测试/修改/安装/读写 sysfs 之前） | ✅ 必做 |
| 高风险操作前（降压/MSR/GRUB/服务变更） | ✅ 必做（备份后再动手） |
| 一天工作结束/离开机器前 | ✅ 建议 |
| 每次重启/崩溃恢复后 | ✅ 建议（记录崩溃前后状态） |

### 13.2 备份内容（脚本自动收集）

```
性能优化方案/会话备份/<YYYYMMDD_HHMMSS>/
├── MANIFEST.md            备份清单 + 任务说明 + 目录说明
├── system_logs/           实时日志
│   ├── journalctl_current_boot.log / prev_boot.log / kernel.log / errors_7d.log
│   ├── dmesg.log + dmesg_mce_thermal.log
│   ├── reboot_history.log (last -x reboot shutdown)
│   ├── cpu_power_snapshot.txt   ← PL1/PL2/governor/EPP/Turbo/C-State/供电/温度 全快照
│   ├── services_status.txt      ← 三个优化服务 + PPD + thermald + turbo-guard 日志
│   └── undervolt_msr_status.txt ← 降压回读 + MSR 0x1A0 + MCE 计数
├── configs/                GRUB / intel-undervolt.conf / 服务文件 / turbo-guard.sh
├── opencode_data/          opencode 会话数据库 + 日志 (会话内容全文)
├── project_snapshot/       性能优化方案 当时全量快照 (md/csv/脚本/sweep_data)
└── session/                AI 按任务补充的会话纪要 (人工/AI 撰写)
```

### 13.3 执行方式

```bash
cd "性能优化方案/会话备份"
./00_保存会话与日志.sh            # 备份
./00_保存会话与日志.sh "任务说明" # 备份并标注任务
```

- AI 会话中：**新任务开始时先运行本脚本**，再把结果位置写入会话纪要（`session/`）。
- 重装系统后：先读 `MANIFEST.md` → `cpu_power_snapshot.txt`（判断当时电源状态）→
  `services_status.txt`（服务是否生效）→ `session/`（当时做了什么、为什么）。

### 13.4 数据落盘纪律（与 11 章/20 章呼应）

1. 备份目录位于数据盘（`/media/<USER>/Public`），**重装/崩溃不丢失**
2. 测试过程产生的 CSV/中间数据**立即**同步到数据盘（非 /tmp）+ `sync`
3. 重要中间结论**以文本写入报告文件**，不依赖对话内存
4. 备份目录自身用 rsync 排除，避免备份嵌套膨胀
