# Acer 电源优化工程 — 目录导航
# Acer Power Optimization Project — Directory Navigation

> This repository is documented in **both English and Simplified Chinese**. Each section first appears in English, then in Chinese. Technical terms, file names, paths and URLs are intentionally kept in their original form in both languages.

> 本仓库以**中英双语**编写。每节先英文、后中文。技术术语、文件名、路径与链接在两种语言中保持一致原文。

---

## ⚠️ About This Project / 项目说明

**English:**

**Acer Aspire A615-51G — power & thermal optimization (dual-boot).** This is a **personal hobby research project** on an Acer Aspire A615-51G (Intel i5-8250U, 12GB, UHD 620 + NVIDIA MX150, dual-boot Windows 11 / Linux Mint). It documents an evidence-based Linux power-tuning stack (**-80mV undervolt, PL1/PL2=25W, C-state=max_cstate=4, Turbo dual-guard, AC/DC auto-switch, safety-net services**) and a **zero-dependency self-made system console** (Python3 + GTK3 on Linux, C# WinForms v6.8 compiled with the system `csc` on Windows).

**Please note before using anything here:**
- This is an **unofficial personal study** — it is **not affiliated with, endorsed by, or the official product of, Acer / Microsoft / NVIDIA / Linux Mint**.
- It **reads and writes real system knobs** (MSR/EC-WMI undervolt, power limits, governor/EPP, Turbo, battery thresholds). A wrong value can destabilize the system or damage hardware. **Use at your own risk.**
- The repo ships **conclusions, methodologies, source and measurement data only**. It does **not** include OEM binaries, decompiled/dump artifacts, credentials, or personal machine data. Personal identifiers were **desensitized** into placeholders (`<USER>`, `<HOSTNAME>`, `<WIN_C_UUID>`) — replace them with your own values before use (see「About Redaction」below).
- Author & donations: if this project helps you and you feel like it, you're welcome to support the author voluntarily; donations do **not** change the free MIT license.

**中文：**

**Acer Aspire A615-51G —— 电源与散热优化（双系统）。** 这是一个针对 Acer Aspire A615-51G（Intel i5-8250U、12GB、UHD 620 + NVIDIA MX150、Windows 11 / Linux Mint 双系统）的**个人爱好研究项目**。它记录了基于实测的 Linux 电源调优栈（**-80mV 降压、PL1/PL2=25W、C-state=max_cstate=4、Turbo 双守护、AC/DC 自动切换、安全网服务**），以及一个**零依赖的自制系统控制台**（Linux 侧 Python3 + GTK3，Windows 侧 C# WinForms v6.8、用系统自带 `csc` 编译）。

**使用前请务必注意：**
- 这是**非官方的个人研究**——与 Acer / Microsoft / NVIDIA / Linux Mint **无任何关联、非官方支持、非其官方产品**。
- 它会**读写真实的系统旋钮**（MSR/EC-WMI 降压、功耗墙、governor/EPP、Turbo、电池阈值）。错误配置可能影响系统稳定性或损坏硬件。**风险自负**。
- 仓库**只包含**结论、方法论、源码与实测数据；**不包含** OEM 二进制、反编译/转储产物、凭据或个人机器数据。个人标识已**脱敏为占位符**（`<USER>`、`<HOSTNAME>`、`<WIN_C_UUID>`）——使用前请换成你自己的值（见下方「关于脱敏」）。
- 作者与打赏：若本项目对你有帮助，欢迎自愿支持作者；打赏**不改变** MIT 的免费许可性质。

**Spec / 机型：**

> - **机型**: Acer Aspire A615-51G | i5-8250U | 12GB | Intel UHD 620 + NVIDIA MX150
> - **系统 (OS)**: 双系统 (Dual-boot)（Windows 11 Build 26200 / Linux Mint 22.3）
> - **重组日期 (Reorganized): 2026-08-31**（原为 `电源优化打包_20260825` 三分类，现按四象限重排）
> - **上位目录 (Parent):** `/media/<USER>/WS/acer 性能优化方案/`

---

## 一、新结构一览 / 1. New Structure Overview

**English:** The original layout was grouped by "packaging batch" (Win/Linux/shared), which scattered related content (e.g. the console) across both sides and kept a duplicate console copy at the root. It has now been regrouped **by usage dimension** — you look for "what I want to do", not "which batch it belonged to when".

**中文：** 原结构按「打包批次」（Win/Linux/共享）组织，导致同一类内容（控制台）散落在 Linux 与 Win 两侧，且根目录另有一份控制台副本。现按**使用维度**重排——查找时按「我要做什么」而非「它当时归哪批」。

```
acer 性能优化方案/
├── 01_通用/               跨端共享的决策文档与知识 | cross-platform decision docs & knowledge
│   ├── 系统控制台方案_20260825/   01-22 号方案文档（Win/Linux 对比、审计、生态）| proposal docs 01-22 (Win/Linux comparison, audit, ecosystem)
│   └── 导航README_电源优化打包.md  （原打包根 README，存档）| (old package-root README, archived)
├── 02_Win/                Windows 侧专属 | Windows-specific
│   ├── ThrottleStop_20260811/     TS 9.7 绿色版（⚠️ 未部署、未生效）| TS 9.7 portable（⚠️ not deployed, not active）
│   └── battery-care-win_20260828/ 电池保养 PowerShell 版 | battery-care PowerShell version
├── 03_Linux/              Linux 侧方案主体 ⭐ | Linux-side main solution ⭐
│   └── 性能优化方案_20260822/     交接手册 / SOP / 脚本 / 实验记录 | handoff manual / SOP / scripts / experiment logs
├── 04_控制台_Win/         Windows 控制台（C# WinForms v6.8）| Windows console (C# WinForms v6.8)
│   └── 系统控制台Win_20260825/
├── 05_控制台_Linux/       Linux 控制台（Python3 + GTK3）⭐ | Linux console (Python3 + GTK3) ⭐
│   └── 系统控制台/
├── 99_存档_只读/          ⛔ 历史存档，勿改勿引用 | ⛔ historical archive, do not modify or reference
│   ├── Linux对比_20260812/        早期 Win/Linux 对比实验（53 文件）| early Win/Linux comparison (53 files)
│   ├── PowerSettingsBackup_20260811/  0811 电源实验工作台（75 文件，一次性胶水脚本）| 0811 power experiment bench (75 files, one-off glue scripts)
│   ├── 报告_20260818/             早期报告 | early reports
│   └── 迁移说明_20260825.txt
├── 系统控制台_latest        Linux 控制台根目录副本（快速访问）| Linux console root copy (quick access)
```
> 注 (Note)：原根目录的 `opencode.json` / `.opencode/`（AI 会话记忆）已于 2026-08-31 移除。 / The root-level `opencode.json` / `.opencode/` (AI session memory) was removed on 2026-08-31.

---

## 二、⚠️ 三个必须知道的坑 / 2. ⚠️ Three Pitfalls You Must Know

### 坑 1：目录名会骗人（最重要） / Pitfall 1: Directory Names Lie (Most Important)

| 目录名 (Directory) | 实际内容时间 (Actual Content Date) | 说明 (Note) |
|---|---|---|
| `系统控制台` | **2026-08-30** | ✅ **主版本 (main version)**，代码最新最全 (latest & most complete) |
| `系统控制台_最新_20260829` | 2026-08-20 | ❌ **旧分支 (old branch)**，代码停留在 08-20 (code stuck at 08-20) |

**名字更新的那份反而更旧 (The one with the "newer" name is actually older)。** `20260829` 只是「08-29 打的快照」，其代码基线是 08-20。核对结果：`20260822` 那份在 7 处代码分歧中 **7:0 全胜**，且独占 2 个关键诊断脚本。

> 已处理 (Handled)：08-31 将 20260829 中**唯一有价值的 4 个文件**单向合并进 20260822（3 个 08-27 遥测 tsv 是超集 + 1 份网络省电调研），原件保留在根目录供核对，确认无误后可删除。

### 坑 2：数据盘挂载点会在 WS / WS1 间漂移 / Pitfall 2: The Data-Drive Mount Point Drifts Between WS / WS1

盘标签是 `WS`，但 udisks2 遇重名会加序号 → 有时变 `WS1`。**所有脚本已改为自动探测**（`sync_to_ws1.sh` 依次尝试 WS/WS1/WS2 + 全盘兜底）。新增脚本请沿用此模式，**勿再硬编码 `/media/<USER>/WS1`**。

### 坑 3：知识库曾与定稿冲突（已修）/ Pitfall 3: The Knowledge Base Once Contradicted the Final Spec (Fixed)

`05_控制台_Linux/.../data/knowledge/README.md` 原写「-80mV 不建议直接使用」，与已定稿的 -80mV 相反。已于 08-31 修正。**若新对话只读知识库会得到错误指引**——权威入口是下方第三节。

---

## 三、权威入口（新对话先读这里）/ 3. Authoritative Entry Points (Read These First in a New Conversation)

**English (English is not necessary here):** In a fresh AI/user conversation, always start from the documents below, ordered by priority. / **中文：** 新对话请优先从以下文档按优先级读起。

| 优先级 (Priority) | 文档 (Document) | 位置 (Location) | 用途 (Purpose) |
|---|--|---|---|
| 🥇 | **00_交接手册_重装后启动.md** | `03_Linux/性能优化方案_20260822/` | **单一事实源 (single source of truth)**。定稿值、重建步骤、大事记 |
| 🥈 | **降压实验记录_-80mV_20260830.md** | 同上 (same) | 全树最新（08-30）。-80mV 五项场景验证全数据 |
| 🥉 | **AI自主科学优化SOP_Linux_v1_20260813.md** | 同上 (same) | 安全红线 / 测量协议 / 服务模板 |
| 4 | 未实现清单_20260820.md | `05_控制台_Linux/系统控制台/` | 放弃项 / 待观察项穷尽调研 |
| 4.5 | **Bug修复档案_20260831.md** | 根目录 (root) | 08-31 发现并修复的全部 bug（9 静态 + 5 动态）+ 方法论 |
| 5 | 09B_本机Linux生态_20260825.md | `01_通用/系统控制台方案_20260825/` | Linux 生态能力全景 |
| 6 | 事故复盘_DKMS_20260829.md | `03_Linux/性能优化方案_20260822/acer-wmi-battery_源码备份/` | 内核模块三次失效的根因与根治 |

---

## 四、当前定稿（2026-08-30，真机实测）/ 4. Current Final Spec (2026-08-30, real-hardware measured)

| 项 (Item) | 值 (Value) |
|---|---|
| 内核 (Kernel) | 7.0.0-30-generic |
| **降压 (Undervolt)** | **-80mV**（实测 -80.08mV，core/gpu/cache 三域）⏳ 观察期至 09-03 |
| PL1/PL2 | 25W / 25W |
| C-state | `max_cstate=4` |
| Turbo | ON（双守护 / dual-guard） |
| GPU | intel 集显 |
| 服务 (Services) | cpu-power-limit / turbo-enable / undervolt / undervolt-resume / acdc-profile / thermal-guard / rasdaemon / **uv-safeguard** / **uv-daily-check** |

**自动化保障 (Automation safeguards)：**
- `uv-safeguard` — 异常关机自动回退 -50mV，防死机循环 (auto-fallback to -50mV on abnormal shutdown, preventing crash loops)
- `uv-daily-check.timer` — 每日 10:00 + 开机 3 分钟巡检 7 项，正常静默、异常通知 (daily 10:00 + 3-min-after-boot check of 7 items; silent when OK, notifies on anomaly)

复测 (Re-test)：`sudo bash 05_控制台_Linux/系统控制台/backend/collect_ground_truth.sh`

---

## 五、重组与清理记录（2026-08-31）/ 5. Reorganization & Cleanup Record (2026-08-31)

- **迁移完整性 (Migration integrity)**：旧目录 780 个文件逐文件名校验，新结构**全部覆盖，零丢失**。
- **旧目录已删除 (Old dirs deleted)**：`电源优化打包_20260825`(673) · `系统控制台_最新_20260829`(106) · `battery-care-win_20260828`(1) · `迁移说明_20260825.txt`
- **删除前的最后一轮校验抓出 2 个真遗漏（均已修复）(Last-round check caught 2 real gaps, both fixed)**：
  1. `PowerSettingsExplorer.exe` — Win 侧根目录散落文件，首次迁移时漏掉 → 已补入 `04_控制台_Win/`
  2. **控制台 README 是残本 (console README was a mutilated copy)** — 主版本 README 缺失「三个页面」「省电设计」两节，而旧副本(20260829)中反而是完整版 → 已用完整版恢复
- **B→A 单向合并 (one-way merge, 4 files)**：3 个 08-27 遥测 tsv（经校验确为超集）+ `网络省电调研_20260827.md`（全树仅此一份且无索引，易丢失）→ 已并入并补知识库索引。原件备份在 `05_控制台_Linux/系统控制台/.merge_backup_20260831/`
- ⚠️ **反向合并被明确拒绝 (Reverse merge explicitly rejected)**：旧副本的 `thermal_ctl.sh` / `00_保存会话与日志.sh` / `sync_to_ws1.sh` 均为旧版，并入会把 3 个已修 bug 全部倒灌。

> 💡 **教训 (Lesson)**：即便目录名暗示「更新」，也必须逐文件比对内容而非看名字。本次若按名字取 20260829 作主版本，会同时丢失 2 份文档、倒灌 3 个 bug。

---

## 六、各目录详细说明 / 6. Per-Directory Details

### 01_通用 (01_General)
跨端共享的**决策文档**，不绑定某一系统。含 01-22 号方案文档：环境调研、热门控制台调研、差距分析、Win/Linux 对比、生态全景、科学性审计、代码审计等。⚠️ 其中部分条目已被后续实测取代，引用时注意文档内的取代横幅。

### 02_Win
Windows 侧专属资产。
- `ThrottleStop_20260811/` — TS 9.7.3 绿色版 + 教程链接。**当前未部署、未生效**（22 号文档确认：全盘无安装实体、进程未运行，FIVR 降压不生效）。属「待决策材料」。
- `battery-care-win_20260828/` — 电池保养 PowerShell 移植版。

### 03_Linux ⭐ 方案主体 (main solution)
`性能优化方案_20260822/`（253 文件）：
- **活跃文档 (active docs)**：交接手册、SOP、降压实验记录、重建脚本、急救手册
- **脚本 (scripts)**：`优化脚本/`（9）、`测量脚本/`（26，含降压扫描与两个守护）
- **第三方模块源码 (third-party module source)**：`acer-wmi-battery_源码备份/`（含 DKMS 事故复盘）
- **数据 (data)**：`sweep_data/`（8 csv）、`_废弃数据_勿引用/`（3 csv，⛔勿引用）
- **历史存档 (archives)**：`会话备份/`（2 个时间点快照，只读）

### 04_控制台_Win
C# / WinForms **v6.8**（2026-08-28），六页 GUI。源码 5 个 .cs + 编译产物 + 10 个依赖 DLL。`README.md` 标注 v6.8，SELFTEST PASS、test_suite FAIL=0。已知瑕疵：`启动器.bat` 与 `启动控制台.cmd` 内容近似重复（已记录未处理）。

### 05_控制台_Linux ⭐ GTK3 控制台主版本 (main version)
Python3 + GTK3（209 文件）。分层：采集(collector) / 控制(controller) / UI(6×ui_) / 领域(src/core) / 后端(backend)。
- `backend/check_ctl_consistency.sh` — 检出「UI 有控件但后端无分支」的缺陷
- `backend/collect_ground_truth.sh` — 真机真值采集（专治文档互相矛盾）
- `20260821_084408/`、`20260821_100541/` — 系统快照（**两份内容完全相同**，冗余）
- `20260829_135207/` — 08-29 会话备份（含 90MB opencode.db）

### 99_存档_只读 ⛔ (99_Archive_ReadOnly)
**历史存档，不应再改动或引用其结论**：
- `Linux对比_20260812/` — 早期对比实验（注意 `log_T1_..._full.txt` 为 0 字节）
- `PowerSettingsBackup_20260811/` — 0811 实验工作台，75 文件多为一次性胶水脚本，功能已被 v6.8 控制台吸收
- `报告_20260818/` — 早期报告
- `迁移说明_20260825.txt` — 上次重组说明

---

## 六·补 启动控制台（三种方式）/ 6.1 Launching the Console (Three Ways)

| 方式 (Method) | 操作 (Action) |
|---|---|
| **桌面双击 (Desktop double-click)** ⭐ | 桌面「系统控制台」图标 |
| **应用菜单 (App menu)** | 搜索「系统控制台」 |
| **终端 (Terminal)** | `bash ~/桌面/系统控制台/启动控制台.sh` |

### 启动器 `启动控制台.sh`（相比原 `start.sh` 的增强）/ Launcher `启动控制台.sh` (enhanced vs. original `start.sh`)

原 `start.sh` 只有 3 行（`cd` + `exec python3 console.py`），遇到缺依赖/无 DISPLAY 只会抛 Python 回溯。新版启动前**预检 6 项**并给出可操作的修复指引：

1. python3 是否存在
2. GTK3/PyGObject 绑定（`apt install python3-gi gir1.2-gtk-3.0`）
3. DISPLAY/Wayland 显示环境
4. console.py 是否缺失
5. sudoers 白名单（缺失 → 提示监控仍可用，控制不可用）
6. **单实例检查**（已在运行则提示 PID + 如何显示隐藏窗口）

**参数 (Parameters)：**
```bash
bash 启动控制台.sh --check    # 只预检不启动（排障用）| pre-check only, no launch (troubleshooting)
bash 启动控制台.sh --force    # 跳过单实例检查，再开一个 | skip single-instance check, open another
```

**日志 (Log)：** `~/桌面/系统控制台/data/console.log`

**单实例实现（2026-08-31 修正）/ Single-instance (fixed 2026-08-31)：** 原用 `pgrep -fc` 进程名匹配，有两个问题——`pgrep -fc` 会输出多行导致 `[: 需要整数表达式` 报错，且模式过宽易误判。改为**锁文件存 PID + 读 `/proc/<PID>/cmdline` 校验**：PID 不匹配 console.py 或进程已退出则视为陈旧锁，自动忽略并覆盖。

### 桌面入口 `系统控制台.desktop` / Desktop Entry `系统控制台.desktop`

已安装至两处（桌面 + `~/.local/share/applications/`，后者供菜单搜索）：
- `Exec` 指向包装脚本（含预检），而非直接跑 console.py
- `Terminal=false`、`StartupWMClass=console.py`（窗口正确归类）
- 已通过 `desktop-file-validate`（无警告）

> ⚠️ 若程序目录变动（如重命名），需同步更新 `.desktop` 里的 `Exec`/`Path`。

---

## 七、维护规则 / 7. Maintenance Rules

1. **时间戳命名 (Timestamp naming)**：文件夹内容更新时，名称中的时间戳同步改为当日日期。
2. **勿硬编码路径 (No hardcoded paths)**：一律用相对定位或自动探测（见坑 2）。
3. **历史存档不改写 (Never rewrite archives)**：需更正时加取代横幅指向新结论，保留原始记录（时间胶囊）。
4. **废弃数据显式标记 (Explicitly mark deprecated data)**：如 `_废弃数据_勿引用/`，不要默默删除。
5. **新对话入口 (New-conversation entry)**：先读 `03_Linux/性能优化方案_20260822/00_交接手册_重装后启动.md`。
6. **合并副本前逐文件比对 (Compare file-by-file before merging copies)**：切勿按目录名/时间戳判断新旧（见坑 1，已付出代价）。

---

## 八、⚠️ 改代码后必须部署（双副本架构）/ 8. ⚠️ You MUST Deploy After Changing Code (Dual-Copy Architecture)

**归档源码 ≠ 运行程序 (Archived source ≠ running program)。** 两者是不同位置：

| 角色 (Role) | 路径 (Path) |
|---|---|
| **归档主版本 (Archive master, edit here)** | `05_控制台_Linux/系统控制台/` |
| **运行位置 (Runtime location, sudoers whitelist target)** | `~/桌面/系统控制台/` |
| 运行数据落盘 (Runtime data) | `~/桌面/系统控制台/data/` |

**只改归档不会生效 (Editing only the archive has no effect)。** 改完必须执行：

```bash
bash "05_控制台_Linux/系统控制台/deploy.sh"           # 部署 | deploy
bash "05_控制台_Linux/.../deploy.sh" --check                        # 先预览差异 | preview diff first
sudo install -m 0755 ~/桌面/系统控制台/backend/thermal_ctl.sh /usr/local/bin/   # 若改了 thermal_ctl | if thermal_ctl changed
```

`deploy.sh` 会：备份运行数据 → rsync 代码（排除数据/备份/会话记录）→ 部署 thermal_ctl/thermal_guard → 提示重启控制台程序。

**验证部署成功 / Verify successful deployment**：`diff -rq ~/桌面/系统控制台 <归档目录>` 排除数据目录后应无差异。

> 2026-08-31 状态：已完成首次部署，两者代码一致，thermal_ctl 8 分支已就位。

---

## 九、2026-08-31 代码审计修复记录 / 9. 2026-08-31 Code Audit Fix Log

对 Linux 控制台（~7,900 行 Python + ~1,145 行 Shell）穷尽审计，修复 9 项：

| # | 问题 (Issue) | 影响 (Impact) |
|---|---|---|
| 1 | `reboot_system()` 双重 sudo | 两个「立即重启」按钮必失败 |
| 2 | `_on_pl_apply` 孤儿代码引用未定义的 `v` | 每次点 PL 应用都额外弹错误框 |
| 3 | `refresh_cam_state` 尾部孤儿块引用不存在的 `svc_list` | 摄像头操作后 AttributeError |
| 4 | `_read_int` 内嵌 72 行不可达代码 | 性能日志查看器函数头丢失（完整版在维护页） |
| 5 | `_open_scene_config` 尾部挂 80 行功耗排行 | 场景对话框混入无关控件 |
| 6 | 场景保存用 `sudo tee`（不在白名单） | 保存间歇性失败；已改为直接写用户文件 |
| 7 | SERVICES 列表服务名错误（`intel-undervolt`）+ 描述过时 | 维护页永远显示「已停止」 |
| 8 | 导航漏「说明文档」项 | 591 行页面不可达 |

### 8 的后续：补入口引发了启动崩溃（重要教训）/ Aftermath of #8: Adding the Entry Caused a Startup Crash (Key Lesson)

补上导航入口后启动**直接崩溃**：

```
File ".../ui_docs.py", line 152, in _build_overview
    box.pack_start(self._h2("设计原则"))
TypeError: Gtk.Box.pack_start() takes exactly 5 arguments (2 given)
```

**这个页面写的是 GTK4 API**（`pack_start(child)`，GTK4 只需 1 参），而项目用的是 GTK3（需 `(child, expand, fill, padding)`）。它「不可达」的真正原因**不是忘了加导航，而是它本来就跑不起来**。

- 修复：54 处 pack 调用补参数（AST 精确定位 + 单行判定后批量转换）
- ⚠️ **踩坑 (Gotcha)**：AST 的 `col_offset` 是 **UTF-8 字节偏移**，而 `len(line)` 是字符数——中文 3 字节/字导致偏移错位，脚本首次运行 IndexError。改用「行尾最后一个 `)`」定位后成功。

> **教训（已固化到验证流程）/ Lesson (now baked into the verification flow)**：`import` 只检查语法，**不执行构造逻辑**。我此前验证 9 个模块「导入成功」就以为没问题——但 UI 类必须**实例化**才算验证通过。现补充：6 个页面全部做过实例化回归（均 ✅）。

| 9 | `sudo_ok()` 检查的文件与 install.sh 生成物不一致 | 新机器部署后误报「白名单未配置」 |

另：`undervolt` 生态显示改为解析实际配置值（原硬编码 -50mV，改 -80 后永远显示「在配」）；`src/gui/` 805 行死代码移入 `99_存档_只读/移出死代码_20260831/`。

**验证 (Verification)**：22 个 py 全部编译通过 · 9 个页面模块导入成功（含复活的 ui_docs）· 服务清单 10 项与真机对照正确 · 归档与部署副本代码零差异 · 运行数据完整保留 · thermal_ctl 8 分支 + 一致性自检通过。

---

## 十、2026-08-31 动态测试报告 / 10. 2026-08-31 Dynamic Test Report

在真机（AC 满电、基线已记录）上**实际运行**控制台，覆盖采集/渲染/控制三层，测试后系统状态已完全恢复（PL 25W、TCC 2、max_perf 100、powerclamp 0、降压 -80.08mV、MCE 0、USB auto、WiFi on）。

### 通过项 (Passed items)

| 层 (Layer) | 测试 (Test) | 结果 (Result) |
|---|---|---|
| 采集 (Collect) | 完整快照（AC/功耗/CPU 8线程/内存/GPU/电池/参数/生态） | ✅ 全部字段有值 |
| 采集 (Collect) | 电池：100% / Full / 健康 80.5% / phase=full / 30.9°C / 型号 LG K8B41CA | ✅ |
| 采集 (Collect) | 生态：C-state=4、zswap=Y、mx150=suspended、undervolt 配置正确解析 | ✅ |
| 渲染 (Render) | 六页面实例化 + 模拟 tick 刷新 | ✅ 全部成功 |
| 控制 (Control) | PL 功耗墙 25→20→25（写入+回读+恢复） | ✅ rc=0，实测值与目标一致 |
| 控制 (Control) | TCC 2→10→2 | ✅ |
| 控制 (Control) | CPU 频率上限 100→80→100 | ✅ |
| 控制 (Control) | USB 省电开关（3 设备 auto⇄on，可逆） | ✅ |
| 控制 (Control) | WiFi 省电开关（on⇄off，可逆） | ✅ `iwconfig` 回读准确 |
| 控制 (Control) | 只读项：usb_verify / wifi_verify / camera_status / get_active_scene / get_default_scenes / service_states | ✅ |
| 启动 (Startup) | 预检模式、日志落盘、--check | ✅ |
| 启动 (Startup) | 单实例拦截（锁文件 PID 精确匹配 python 进程） | ✅ |

### 测试中发现并修复的 3 个问题 / 3 Issues Found & Fixed During Testing

| # | 问题 (Issue) | 影响 (Impact) | 修复 (Fix) |
|---|---|---|---|
| 1 | **温度源错误**：`collector.py` 读 `thermal_zone0`（机壳 27.8°C）而非 CPU 封装 `thermal_zone2`（59°C） | ①总览页/场景页显示环境温度而非 CPU 温度<br>②**78°C 高温告警永远不触发**（CPU 78°C 时采集值才约 47°C） | 改读 CPU 封装，缺失回退 thermal_zone0 |
| 2 | **单实例失效**：`exec python3 ... \| tee` 的管道使 exec 替换子 shell，锁文件 PID ≠ 实际进程 | 可重复启动多个实例，互相干扰 | 后台 tee + 前台 exec（无管道），PID 与锁文件一致 |
| 3 | **fan_boost 防御不足**：死机 #4 的直接操作，仅靠「UI 不显示」维持，函数可被误调触发 EC 写入 | 违反永久禁用铁律的风险 | 加硬拦截：默认拒绝 + `force=True` 才执行，附安全替代说明 |

### 方法说明 (Method notes)

- 危险功能（GPU 切换、一键重启、摄像头禁用）**未实际执行**，仅验证确认机制存在
- 所有写操作均「测前记录基线 → 测后恢复 → 核对」
- ⚠️ 教训：首次测单实例时我用 `timeout` 启动，进程已终止导致锁陈旧被正确忽略，误判为「拦截失效」。改为让进程真正持续运行后，拦截正常——**测试方法本身要正确**

---

## 十一、2026-08-31 第二轮动态测试（补充上轮未测项）/ 11. 2026-08-31 Second-Round Dynamic Testing (Covering Items Skipped Last Round)

上轮跳过了需重启/影响硬件的功能，本轮在安全边界内补测。测试后系统状态完全恢复（PL 25W、performance/performance、TCC 2、max_perf 100、降压 -80.08mV、MCE 0、uvcvideo 1、场景配置 ac-perf/bat-save），无残留进程。

### 新增通过项 / Newly Passed Items

| 测试 (Test) | 结果 (Result) |
|---|---|
| 摄像头 禁用→启用（uvcvideo 卸载/重载可逆） | ✅ 回读准确，/dev/video0 恢复 |
| 场景参数保存（无 sudo 直写 default_scene） | ✅ 修复确认，写/读/恢复正常 |
| 场景切换 `set_scene` ac-perf⇄ac-bal（governor/EPP/PL 三参数同步） | ✅ |
| 单次基准 `bench_once()` | ✅ 1558.3 万/s（修复后） |
| 完整基准协议 EMP（热身1+正式5+±2σ+中位数） | ✅ 1422.0 万/s，5 样本无离群，耗时 120s |
| M3 只读逻辑（`m3_active()` 判定） | ✅ 未启用时返回 False 正确 |
| 危险项命令构造 vs sudoers 白名单 | ✅ gpu_switch / reboot_system 均精确匹配 |
| 危险项确认机制（GPU 切换 3 处、一键重启 3 处） | ✅ 存在 |

### 本轮发现并修复的 bug / Bugs Found & Fixed This Round

**`bench_once()` 双重 sudo**（与 `reboot_system()` 同类，0831 修 reboot 时遗漏此处）：
```python
_run(["sudo", "-n", SCENE_SCRIPT, "bench"])   # _run 内部再加 sudo
# → 实际执行 sudo -n sudo -n <场景管理.sh> bench，不在白名单 → 报"sudo: 需要密码"，迭代数=0
```
修复后 `bench_once()` 正常（1558.3 万/s）。

> 静态审计时我只逐个扫了 `_run` 里显式写 `reboot` 的调用，没覆盖所有 `_run` 参数——**同类 bug 会分布在不同函数里，必须按调用点逐个核对而非只看关键词**。

### GPU 切换全流程实机验证（2026-08-31，两次重启）/ GPU Switch Full-Flow Real-Hardware Verification (2026-08-31, two reboots)

| 阶段 (Stage) | prime-select | nvidia 模块 | i915 | 降压 (Undervolt) | 判定 (Result) |
|---|---|---|---|---|---|
| 起点 (Start) | intel | 0 | 1 | -80.08mV | — |
| 切 nvidia + 重启 | nvidia | **4** | 1 | -80.08mV | ✅ nvidia 生效 |
| 切回 intel + 重启 | intel | **0** | 1 | -80.08mV | ✅ intel 恢复 |

- `gpu_switch()` 双向工作，重启后各自生效（nvidia 加载 4 模块 / intel 卸载）
- **nvidia 模式正常**：无挂起/黑屏（历史担忧未出现）
- **优化栈跨重启完全保持**：降压/PL/C-state/MCE 均不变
- 佐证定稿：当前实际为 intel 模式（与 0831 已改的定稿表一致）

### M3 进入/退出实机验证（2026-08-31，DC 97%）/ M3 Entry/Exit Real-Hardware Verification (2026-08-31, DC 97%)

| 阶段 (Stage) | EPP | PL1 | Turbo | acdc-profile | m3_active() |
|---|---|---|---|---|---|
| 进入前 (Before) | power（bat-save） | 10W | 关 | active/enabled | False |
| **进入 M3 (Enter M3)** | power | 10W | 关 | **inactive/disabled** | **True** |
| **退出 M3 (Exit M3)** | power | 10W | 关 | **active/enabled** | **False** |

- 进入：rc=0，服务文件创建 + enabled，输出「✅ M3 已生效（EPP=power，acdc-profile 已停，PL1=10W，Turbo 关，重启后保持）」
- 退出：rc=0，服务文件删除、acdc-profile 恢复、场景回 bat-save，输出「✅ 已退出 M3，恢复离电默认场景：bat-save」
- 全程降压 -80.08mV 保持、温度降回 49°C、MCE 0
- **M3 完整闭环验证通过**（含 2026-08-20 的「EPP 写入 EBUSY 重试 5 次」修复逻辑）

---

### 控制台功能测试总结（2026-08-31 三轮动态测试）/ Console Functional Test Summary (2026-08-31, Three Rounds of Dynamic Testing)

✅ **全部实机验证通过 / All verified on real hardware**：采集层 / 六页面渲染刷新 / PL·TCC·maxperf 写读恢复 / USB·WiFi·摄像头 开关可逆 / 场景切换 / 场景参数保存 / 基准测试(单次+EMP协议) / M3 只读+进出 / 启动器(预检/日志/单实例) / **GPU 切换全流程(两次重启)** / 一键重启命令构造

🐛 **累计修复 6 个运行时 bug / 6 runtime bugs fixed in total**：温度源错误 / 单实例 PID 漂移 / fan_boost 无硬拦截 / bench_once 双重 sudo / **充电曲线浮充污染** / （另有 0831 上午审计修复的 9 项代码问题）

### 充电曲线浮充污染修复（2026-08-31）/ Charge-Curve Floating-Charge Contamination Fix (2026-08-31)

**现象 (Symptom)**：电池保养页充电曲线全是 100% 水平线（实测 31 点全 100%）。

**根因 (Root cause)**：`collector.py` 只在 `Full 且 last<95` 时清空周期——「从满电开始充电」的**浮充点**（100%）会无限堆积，污染下一周期的真实充电曲线。

**修复 (Fix)**（`collector.py`）：
- 真实充电（Charging 且 <100%）→ 若之前是浮充态则清空，开新周期
- 满电浮充（100%）→ 只保留最近 `FLOAT_KEEP=60` 个点，不无限堆积
- 新增 `_prev_float` 状态跟踪

**验证 (Verification)**（monkeypatch 真实 `_battery()` 方法）：满电浮充×20 → 56 点（限长）；开始充电 88% → **1 点**（旧浮充被清空）✅

> 注：99% 是正常充电尾声（非浮充），正常追加；浮充判定以 `cap>=100` 为准

---

*重组 (Reorganized): 2026-08-31 | 由原 `电源优化打包_20260825` 三分类改为四象限 + 存档区 | regrouped from the original `电源优化打包_20260825` three categories into four quadrants + archive*
*迁移完整性 (Migration integrity): 780 个文件逐名校验，全部覆盖，零丢失 | 780 files verified one-by-one, fully covered, zero loss | 旧目录已清理 (old dirs cleaned)*

---

## 附：可选的空间回收（约 165 MB）/ Appendix: Optional Space Recovery (~165 MB)

三个冻结的 `opencode.db` 快照（均为只读存档，同内容已有 markdown 可读导出）：

| 文件 (File) | 大小 (Size) | 位置 (Location) |
|---|---|---|
| `opencode.db` | 90.1 MB | `05_控制台_Linux/.../20260829_135207/opencode_data/` |
| `opencode.db` | 54.4 MB | `03_Linux/.../会话备份/20260820_185004/opencode_data/` |
| `opencode.db` | 8.5 MB | `03_Linux/.../会话备份/20260818_133755/opencode_data/` |

各目录下的 `session/opencode_会话导出.md` 已是可读文本版。**需人工确认导出完整后再删。**

---

## 十二、运维工具 GUI 化（2026-08-31）/ 12. Ops Tools GUI-ified (2026-08-31)

把此前仅命令行可用的功能接入控制台：

**系统维护页 · 运维工具区 / System Maintenance Page · Ops Tools Area**：
- 📸 系统快照（Timeshift create/list，铁律 L1/L2 GUI 化）
- 💾 一键会话备份（00_保存会话与日志.sh）
- 🔇 后台降权 / 恢复优先级（quiet/unquiet，基准测试前置）

**高级控制页 · 工具区新增 / Advanced Control Page · New Tools**：
- 🖥 跨机适配向导（adapt_test，重装/换同配置机器后恢复控制台能力）
- 🪟 临时切到 Windows（efibootmgr BootNext，重启进 Win，下次自动回 Linux）
- 🧰 高级工具入口（GRUB 修改/降压应用/降压扫描/DKMS 注册/真值采集的命令行+说明，不提供一键执行——高风险项保持命令行，防误触）

**配套 (Supporting)**：
- sudoers 白名单新增 timeshift / adapt_test / efibootmgr（install.sh 同步）
- controller.py 新增 6 个运维函数（路径自动探测：运行目录→桌面→项目归档）
- 快照 list 修复：timeshift --list 需 root，统一走 sudo -n 免密

**验证 (Verification)**：编译通过 · 双页面实例化 · 路径探测正确 · 快照列表免密可用 · 降权可逆

---

## 十三、快照管理增强 + 目录清理（2026-08-31）/ 13. Snapshot-Management Enhancements + Directory Cleanup (2026-08-31)

### 快照管理增强 / Snapshot enhancements
- **创建快照 (Create snapshot)**：支持选择备份盘（lsblk 列出候选，排除系统分区/EFI/虚拟设备）
- **删除快照 (Delete snapshot)**：列表选择 → 危险确认 → `timeshift --delete`
- 会话备份 GUI 已移除（用户不需要）

### 目录清理（归档 114M → 3.8M，桌面副本 164M → 4.0M）/ Cleanup (archive 114M → 3.8M, desktop copy 164M → 4.0M)
- 归档：__pycache__/pyc、.merge_backup 删除；20260821_* 快照 + 20260829_135207(104M) 移入 99_存档
- 桌面副本：deploy 备份残留自动清理（保留最近 3 个）；20260821_* 快照移入 99_存档
- 桌面副本**不可删除**（sudoers 白名单指向它，是运行位置）

### deploy.sh 改进 / deploy.sh improvements
- 部署时自动清理旧 deploy 备份（保留 3 个），防堆积

---

## 十四、运行位置迁移：桌面 → ~/.local/share（2026-08-31）/ 14. Runtime-Location Migration: Desktop → ~/.local/share (2026-08-31)

**背景 (Background)**：双副本架构（归档 + 桌面副本）造成混乱，用户要求只保留归档。但归档在 **NTFS 数据盘**（丢执行位/权限），**不能作为运行位置**。

**方案 (Solution)**：运行位置从 `~/桌面/系统控制台` 迁移到 `~/.local/share/系统控制台`（btrfs @home，可执行，非桌面）。桌面副本已删除。

**架构（更新后）/ Architecture (updated)**：
```
归档源码真源 (Archive source of truth):  /media/<USER>/WS/acer 性能优化方案/05_控制台_Linux/系统控制台/
运行位置 (Runtime location):      ~/.local/share/系统控制台/        （sudoers/.desktop 指向）
同步 (Sync):          bash <归档>/deploy.sh
启动 (Launch):          桌面图标 / 应用菜单 / bash ~/.local/share/系统控制台/启动控制台.sh
```

**迁移内容 (Migrated)**：
- sudoers 2 文件（system-console / kernel-guard）路径更新 + 备份 .bak_桌面
- .desktop 2 处（桌面 + 应用菜单）Exec/Path 更新
- deploy.sh / snapshot.sh / install.sh / sync_to_ws1.sh 路径更新
- 桌面副本删除（旧实例先停止）

**验证 (Verification)**：新位置启动成功（PID 锁精确）· 场景管理免密调用 rc=0 · 6 页面实例化 · sudo_ok=True

---

## 十五、冻结快照回收（2026-08-31）/ 15. Frozen-Snapshot Recovery (2026-08-31)

回收前**逐 db 验证 markdown 导出完整性**（db 会话数 vs md 会话数）：

| 快照 (Snapshot) | db 会话 (db sessions) | md 导出 (md exports) | 判定 (Result) |
|---|---|---|---|
| 20260818 | 2 | 2 | ✅ 完整 → 已删 db（8.9M）|
| 20260820 | 5 | 5 | ✅ 完整 → 已删 db（57M）|
| 20260821_084408 | 5 | 5 | ✅ 完整 → 已删 db（69.7M）|
| 20260821_100541 | 5 | 5 | ✅ 完整 → 已删 db（70.8M）|
| 20260829 | **13** | **5** | ⚠️ **不完整 → 保留 db（91M）**|

- **释放 207M**（362M → 146M），markdown 导出现为唯一记录，已验证 5 份完整
- **20260829 保守保留**：db 有 13 会话（含 PiliPlus/DeepSeek 等无关会话），md 仅导出 5 个——不确定的删除不做

---

## 十六、关于脱敏 / 16. About Redaction

**English:** This is a **public repository**. Personally identifiable and machine-environment information has been **replaced with placeholders**; replace them with your own values before use:

**中文：** 本仓库为公开仓库，已将**个人可识别信息与运行环境信息**替换为占位符，使用前请替换为你自己的值：

| 占位符 (Placeholder) | 被替换的真实值 (Replaced real value) | 说明 (Note) |
|---|---|---|
| `<USER>` | 原 Linux 用户名 / Windows 用户名 | `/home/<USER>`、`/media/<USER>`、`C:\Users\<USER>` |
| `<HOSTNAME>` | 原主机名 | 已脱敏，替换为你机器的主机名 |
| `<WIN_C_UUID>` | Windows C 盘分区 UUID | 用于 fstab 挂载示例，替换为你的实际 UUID |

> 脱敏范围覆盖 22 个源码/文档/desktop 文件的硬编码路径与标识；`$(hostname)` 等**动态**取值脚本原样保留（运行时会自动获取本机值）。系统日志、`opencode` 会话库、OS 厂商/OEM 产物等一律不进入本仓库（见 `.gitignore`）。

## 十七、未公开内容 / 17. Unpublished Content

**English:** This repo **deliberately does NOT contain** the following items (copyright / license / privacy reasons):

**中文：** 本仓库**刻意不包含**以下内容（版权 / 许可 / 隐私原因）：
- **OEM / 厂商逆向原始产物 (OEM / vendor reverse-engineering originals)**：ACER、微软、NVIDIA 等厂商的闭源二进制、反编译/解包/抓包载荷、固件转储。
- **第三方专有二进制 (Third-party proprietary binaries)**：`*.exe` / `*.dll` / `ThrottleStop` / `PowerSettingsExplorer.exe` 等（请在官方渠道自行获取，见 [THIRDPARTY.md](THIRDPARTY.md)）。
- **系统日志与运行时产物 (System logs & runtime artifacts)**：journalctl/dmesg、`*.log`、快照、`opencode` 数据库、`__pycache__`。
- **个人 / 机器信息 (Personal / machine info)**：用户名、主机名、MAC、串号、真实路径（已按「关于脱敏」替换）。

## 十八、许可 · 安全 · 更新 / 18. License · Security · Updates

- [LICENSE](LICENSE) — 本仓库主代码以 **MIT License** 授权，版权归 **段雪健 (Duan Xuejian)** / Main code is under the **MIT License**, Copyright © **Duan Xuejian**.
- [THIRDPARTY.md](THIRDPARTY.md) — 第三方组件与并行许可清单 / Third-party components & parallel licenses（acer-wmi-battery=GPL-2.0、LibreHardwareMonitorLib=MIT、WinRing0=Modified BSD 等）。
- [CONTRIBUTING.md](CONTRIBUTING.md) — 贡献指南（脱敏/许可边界/禁止提交内容）/ Contribution guide (redaction/licensing boundaries/prohibited content)。
- [.github/SECURITY.md](.github/SECURITY.md) — 安全漏洞报告流程（私有通道）/ Security vulnerability reporting (private channel)。
- [CHANGELOG.md](CHANGELOG.md) — 变更记录 / Change log。

---

## 💰 打赏 / Sponsorship

若本项目对你有帮助，欢迎自愿支持作者。打赏不改变 MIT 的免费许可性质。以下是自愿赞助入口。

> If this project helps you, you are welcome to voluntarily support the author. Donations do not change the MIT free-license nature.

| 微信 (WeChat) | 支付宝 (Alipay) |
|------|------|
| ![微信收款码](assets/donate_wechat.jpg) | ![支付宝收款码](assets/donate_alipay.jpg) |