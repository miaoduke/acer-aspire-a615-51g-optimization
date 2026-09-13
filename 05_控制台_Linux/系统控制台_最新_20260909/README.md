# 系统控制台 v2.0

[![Tests](https://github.com/miaoduke/acer-aspire-a615-51g-optimization/actions/workflows/test.yml/badge.svg)](https://github.com/miaoduke/acer-aspire-a615-51g-optimization/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Acer A615-51G (i5-8250U + MX150) 笔记本调优工具 · Python3 + GTK3 + systemd

## ✨ 核心特性

| 功能 | 描述 |
| --- | --- |
| **6 场景一键切换** | AC/DC 各 3 档，含 PL/Turbo/EPP/Governor 完整参数 |
| **profile 配置化** | 8 个内置 + 无限用户自定义 + INI 继承/合并 |
| **plugin 抽象** | 借鉴 TuneD，自动发现 + 错误隔离 + 用户可写 |
| **MSR 降压三重守护** | -100mV（D7 验收通过）：msr_deadman 30s 巡检 + uv-safeguard 异常关机三级判定 + uv-daily-check 每日巡检 |
| **降压 GUI 调节** | 高级页滑块调 core/cache（电气同轨联动）与 GPU 独立域 0~-130mV + 温度墙；原子改 service + 回读校验失败回滚，三重守护基准自动同步，挂起唤醒值同步（2026-09-11） |
| **温度守护** | 85°C 降 PL1，75°C 恢复 |
| **AC/DC 自动切换** | acdc-profile v9，含 GPU GT 频率联动（AC 1100/DC 700MHz） |
| **GRUB 启动菜单时间** | 高级页直接设等待秒数/显示方式，自动同步 RECORDFAIL_TIMEOUT，备份+校验+一键还原（2026-09-11） |
| **进程工具** | PSS 内存精确 + kill/renice + Top 50（两阶段读取优化） |
| **应用功耗排行** | cgroup v2 CPU 差分 + RAPL 功耗分摊（MSR 0x611 回退，内核 7.0 兼容）+ 内存列，过滤会话层级噪音，对话框级 Collector 差分（2026-09-11） |
| **限流时间轴** | 5 类限流原因 + 24h 历史 |
| **中英双语 i18n** | 740+ 词条字典，T() 运行时切换，f-string 模板化动态文案；2026-09-11 穷尽审计 0 漏网 |
| **健康检查** | 13 项（服务/降压/部署物一致性/采样活跃度）+ visudo 校验 + 冲突检测 |
| **一键重装恢复** | install.sh 单脚本全自动：sudoers 别名体系 + 5 服务 + 系统包自动安装（msr-tools/rasdaemon/perl-DBI 系列）+ undervolt 工具 pip 自装 + DKMS 自注册（2026-09-11） |
| **GUI 7 页** | 总览/电源场景/电池/高级/进程/维护/文档（维护页含开机自启开关） |
| **完整测试** | 12 套件 91 用例 + 21 shell 用例 = 112/112 双绿 |

## 📦 安装

> ⚠️ 说明：`aur/PKGBUILD` 为打包**模板**，尚未发布到 AUR；发布前请使用下方 Debian/Ubuntu 源码安装。

### Debian/Ubuntu/Mint
```bash
# 克隆本仓库 + 跑 install.sh
git clone https://github.com/miaoduke/acer-aspire-a615-51g-optimization
cd acer-aspire-a615-51g-optimization/05_控制台_Linux/系统控制台_最新_20260909
sudo bash install.sh
```

### Arch (AUR) — 未来发布后可用
```bash
# 未来发布后可用：
# yay -S system-console
```

### 手动
```bash
# 1. 复制项目到 /opt/system-console
sudo cp -r . /opt/system-console

# 2. 加载 MSR 模块
sudo modprobe msr

# 3. 部署服务
sudo cp backend/msr_deadman.{sh,service,timer} /usr/local/bin /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now msr_deadman.timer

# 4. 配置 sudoers
sudo cp /etc/sudoers.d/system-console{,-thermal} .

# 5. 启动 GUI
python3 console.py
```

## 🚀 使用

```bash
# 启动 GUI（主入口）
python3 console.py

# 健康检查
bash scripts/phase1_health_check.sh

# 完整状态快照
python3 scripts/snapshot_quick.py

# 试创建自定义 profile
bash scripts/try_user_profile.sh
```

## 🏗️ 架构

### 配置系统（profile）
- `~/.config/system-console/profiles/<name>/tuned.conf` — INI 格式
- `[main] include=<parent>` — 继承
- `[cpu] / [gpu] / [battery] / [thermal]` — 各段独立

### Plugin 系统
- `plugins/<name>.py` — 自动发现
- `Plugin` 基类：`_init` / `_apply` / `_undo` 3 钩子
- 用户目录优先：`.config/system-console/plugins/`

### systemd 服务
- `undervolt` — MSR 0x150 写入（-100mV）
- `undervolt-resume` — 挂起恢复重应用
- `acdc-profile` — AC/DC 切换 + GPU GT 频率联动
- `cpu-power-limit` — RAPL PL1/PL2
- `thermal-guard` — 温度守护（≥85°C 降 PL1）
- `msr_deadman.timer` — 30s 巡检（95°C 自动回退）
- `uv-safeguard` — 异常关机三级判定（CLEAN/CRASH_REVERT/WATCH）
- `uv-daily-check.timer` — 每日 10:01 巡检（MCE 权威源 ras-mc-ctl，零误报）

## 📅 2026-09-10/11 更新日志（系统重装恢复 + 功能增强）

### 重装恢复工程（路径含空格 + 部署物丢失两大根因家族）

本机项目路径含空格（`/media/.../acer 性能优化方案/...`），重装系统后暴露并根治了一整族问题：

- **sudoers 无法匹配含空格路径**（语法不支持引号/转义）→ 特权脚本全部走 `/usr/local/bin/sc-*.sh` 无空格别名符号链接，controller 用 `_alias_script()` 解析
- **`_run(["bash", script])` 形式 sudoers 永不匹配**（sudo 记录的是 bash）→ 直接执行脚本本体
- **systemd ExecStart / .desktop Exec 含空格路径被拆词** → 生成时加引号
- **脚本自定位 `dirname $0` 经符号链接启动时算错** → 全部 `readlink -f`
- **config.yaml 默认 base_dir 指向数据目录** → install.sh 生成后 sed 指向代码目录
- **WS 数据盘不自动挂载** → fstab UUID 条目（nofail + 10s 超时，盘缺失不阻塞启动）

### install.sh 升级：一键全自动恢复

[0/7] 新增段实现"重装后只跑一个脚本全恢复"：
- 系统包缺则自动装（msr-tools / rasdaemon / libdbi-perl / libdbd-sqlite3-perl + rasdaemon 环境文件）
- undervolt 工具自动 pip 装入项目 `.venv-tools` 并链接
- undervolt / undervolt-resume 服务缺失时生成（-100mV，resume 从主服务同步值）
- thermal_ctl / thermal_guard 从"前置要求已存在"改为自动部署（原为重装必炸点）
- acer-wmi-battery 源码复制 + DKMS 注册 + modules-load.d 自启

### 新功能

- **MSR 降压调节 GUI**（高级页）：core+cache 联动滑块（电气同轨强制同值）、GPU 独立滑块、温度墙；`uv_set.sh` 白名单落点做范围硬校验（0~-130mV）、原子改 service、应用后回读校验失败自动回滚、`/var/log/uv_set.log` 留痕；三重守护基准随 service 自动同步；**同步 undervolt-resume.service**（修复挂起唤醒后旧值重打的隐患）
- **GRUB 启动菜单时间**（高级页）：秒数 + 显示/隐藏 + RECORDFAIL 同步，改编自《设置GRUB启动时间.sh》工具，原配置备份 `.grubtime.bak`
- **开机自启开关**（维护页）：Gtk.Switch 控制 `~/.config/autostart/system-console.desktop`；install.sh 生成的家目录文件 chown 归还真实用户
- **应用功耗排行增强**：内存 MB 列、过滤 user/session 等层级噪音只留真实应用、对话框级 Collector 复用（修复"永远第一次差分"导致功耗列恒空的缺陷）、RAPL 功耗回退 MSR 0x611（内核 7.0 不再暴露 sysfs energy_uw，且原路径文件名 `energy_uj` 本身有误）

### 修复

- 性能日志回看：`get_perf_history` 文件路径 timestamp 残留 str → `time.localtime()`/`sorted()` 崩溃（`'<' not supported between str and float`）；加载改 `run_async` 异步（7 天档几千行同步遍历冻结主循环，对话框关不掉）；`ui_maintenance` 缺 `import time`
- 快照脚本 `snapshot_quick.py`：任意 cwd 下 `from src.core...` 失败 → 头部 sys.path 注入；undervolt 裸调用（无 sudo）恒失败 → sudo -n 白名单
- `sudo_ok()` 误报"白名单未配置"：optional_any（历史手动件）被写成硬门槛 → 只看核心项
- 服务列表移除幽灵条目 turbo-enable（单元从未存在）；oneshot 服务（uv-safeguard）显示"inactive·预期"不再误导
- modprobe / undervolt / ras-mc-ctl 等白名单补齐；rasdaemon 依赖链（DBI/DBD-SQLite）装齐
- 服务加 `RequiresMountsFor=/media/.../WS`（盘未挂载时 acdc/thermal-guard 必 203/EXEC）
- PPD（power-profiles-daemon）与场景管理 EPP 冲突 → mask（检测器给出）
- 基准测试 `$BENCH` 未加引号被空格拆词 → "测试失败"假象

### i18n

- 穷尽 AST 审计全部 GUI 文件的 `T()` 调用（含隐式字符串拼接）：新增 100+ 英文词条（本次全部新功能 + 历史欠账），**最终审计 0 漏网**
- 语言名"中文/English"按 i18n 惯例保留母语显示

## 🧪 测试

```bash
# 跑全部 12 套件（91 用例）
for t in tests/test_*.py; do
  python3 "$t"
done

# shell 套件（21 用例）
bash tests/test_p1_safeguard.sh
```

| 套件 | 覆盖 |
| --- | --- |
| test_phase1 | 健康检查 / sudoers / 冲突 / 死机守护 |
| test_phase2_profile | 8 个 profile 解析 / 继承 / 验证 |
| test_phase2_integration | controller 用 profile（fallback 硬编码） |
| test_phase2_gui | UI 逻辑 |
| test_phase2_gui_render | 真实 GTK 渲染 |
| test_phase2_plugin | 3 个 plugin 加载 / 用户覆盖 |
| test_phase2_complete | G1-G6 端到端 |
| test_p1_i18n_apply | i18n 字典 / T() 实际应用 |
| test_p2_i18n | 中/英双语 |
| test_e2e_user_view | 7 页 + 性能回归 |
| test_e2e_perf_pipeline | perf 采样管道（P0-A 回归：dataclass 契约 / 落盘 / 异常告警） |
| test_p1_safeguard.sh | safeguard 三级判定（CLEAN/CRASH_REVERT/WATCH） |

> 状态快照（2026-09-07）：112/112 双绿（91 Python + 21 shell）；
> -100mV 降压 D7 观察期验收通过；健康巡检 13 项。

## 📝 设计文档

- `data/phase1/CHECKLIST.md` / `STATUS.md` — Phase 1 部署记录
- `data/phase2/STATUS.md` — Phase 2 完整状态
- `v2.0_部署后状态报告.md` — 部署 + bug 修复全记录

## 🙏 致谢

- [TuneD](https://github.com/redhat-performance/tuned) — profile + plugin 灵感
- [ThrottleStop](https://www.techpowerup.com/download/techpowerup-throttlestop/) — 限流时间轴灵感
- [auto-cpufreq](https://github.com/AdnanHodzic/auto-cpufreq) — 充电阈值灵感
- [Mission Center](https://missioncenter.io/) — 现代 GUI 灵感

## 📄 许可

MIT License
