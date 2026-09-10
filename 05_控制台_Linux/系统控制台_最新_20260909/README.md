# 系统控制台 v2.0

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Acer A615-51G (i5-8250U + MX150) 笔记本调优工具 · Python3 + GTK3 + systemd

## ✨ 核心特性

| 功能 | 描述 |
| --- | --- |
| **6 场景一键切换** | AC/DC 各 3 档，含 PL/Turbo/EPP/Governor 完整参数 |
| **profile 配置化** | 8 个内置 + 无限用户自定义 + INI 继承/合并 |
| **plugin 抽象** | 借鉴 TuneD，自动发现 + 错误隔离 + 用户可写 |
| **MSR 降压三重守护** | -100mV（D7 验收通过）：msr_deadman 30s 巡检 + uv-safeguard 异常关机三级判定 + uv-daily-check 每日巡检 |
| **温度守护** | 85°C 降 PL1，75°C 恢复 |
| **AC/DC 自动切换** | acdc-profile v9，含 GPU GT 频率联动（AC 1100/DC 700MHz） |
| **进程工具** | PSS 内存精确 + kill/renice + Top 50（两阶段读取优化） |
| **限流时间轴** | 5 类限流原因 + 24h 历史 |
| **中英双语 i18n** | 453 词条字典，T() 运行时切换，f-string 模板化动态文案 |
| **健康检查** | 13 项（服务/降压/部署物一致性/采样活跃度）+ visudo 校验 + 冲突检测 |
| **GUI 7 页** | 总览/电源场景/电池/高级/进程/维护/文档 |
| **完整测试** | 12 套件 91 用例 + 21 shell 用例 = 112/112 双绿 |

## 📦 安装

### Debian/Ubuntu/Mint
```bash
# 克隆本仓库 + 跑 install.sh
git clone https://github.com/miaoduke/acer-aspire-a615-51g-optimization
cd acer-aspire-a615-51g-optimization/05_控制台_Linux/系统控制台_最新_20260909
sudo bash install.sh
```

### Arch (AUR)
> 说明：`aur/PKGBUILD` 为打包模板，尚未发布到 AUR；发布前请使用上方源码安装。
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
