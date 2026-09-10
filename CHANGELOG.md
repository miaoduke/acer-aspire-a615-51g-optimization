# Changelog — 变更记录

本仓库记录 Acer A615-51G 电源/性能优化工程的公开版本变更。项目主线结论与重建步骤以 `03_Linux/性能优化方案_20260822/00_交接手册_重装后启动.md` 为单一事实源。

## [未发布] 公开化 2026-08-31

**发布准备（目录重组 + 脱敏 + 合规）**
- 目录四象限重排（`01_通用 / 02_Win / 03_Linux / 04_控制台_Win / 05_控制台_Linux`），旧 `电源优化打包_20260825` 迁移完成、零丢失。
- 全量脱敏：`hackdale→<USER>`、`d6150→<USER>`、主机名→`<HOSTNAME>`、Windows C 盘 UUID→`<WIN_C_UUID>`，涉及 22 个源码/文档/desktop 文件。
- 新增合规文档：`LICENSE`(MIT) / `THIRDPARTY.md` / `.github/SECURITY.md` / `CONTRIBUTING.md` / `.github/FUNDING.yml`。
- `.gitignore` 白名单公开：排除 `_private`、系统日志、`opencode` 会话、OEM/第三方二进制、图表/HTML 转储；放行 `assets/` 捐赠收款码。
- README 增加英文概览、免责声明、双系统能力表与捐赠入口。

**技术定稿（真机实测，继承此前的工程成果）**
- Linux：`-80mV` 降压、PL1/PL2=25W、Turbo 双守护、C-state=max_cstate=4、uv-safeguard/uv-daily-check 自动化。
- Windows：系统控制台 v6.8（EPP AC=40/DC=84、EcoQoS、省电采样、零外部依赖 csc 编译）。
- `Bug修复档案_20260831.md`：9 静态 + 5 动态 bug 修复记录与方法论。

## [主要内容] 控制台 v2.0 同步 2026-09-10

**Linux 控制台 v1 → v2.0（`05_控制台_Linux/系统控制台_最新_20260909/`，替代并移除旧 v1）**
- **降压定稿 -80mV → -100mV**：D7 观察期（2026-09-03→09-07）验收通过，实测 core -99.61mV，16/16 项全过（零 panic/MCE/误触发；PL 25W/25W；63°C max）。
- 新增 **MSR 降压三重守护**：`msr_deadman`(30s 巡检、95°C 自动回退，1523+ 次零误触发) + `uv-safeguard`(异常关机三级判定 CLEAN/CRASH_REVERT/WATCH，D7 CLEAN×6 + WATCH×1) + `uv-daily-check`(ras-mc-ctl 权威 MCE，替代 mcelog/AER 消除误报)。
- 新架构：profile 配置化（8 内置 + 用户自定义 + INI 继承）、plugin 抽象（TuneD 启发）、中英双语 i18n（453 词条、T() 运行时切换）、GUI 7 页、健康检查 13 项。
- AC/DC 自动切换 **acdc-profile v9**：GPU GT 频率联动（AC 1100 / DC 700 MHz），修复 P0-B 首次真正生效。
- 工程化：12 套件 112 用例双绿（91 Python + 21 shell）、`.github/workflows/test.yml` CI(3.10/3.11/3.12)、`aur/PKGBUILD` AUR 打包**模板**、`NOT_API_WEBUI.md` 无网络监听红线。
- 设计红线（`NOT_API_WEBUI.md`）：不加入 REST/JSON API、不打 Web UI、不开网络监听端口，保持本地单机 GUI。

**更新与脱敏**
- 本次同步沿用原脱敏规范，新增/复扫：`hackdale→<USER>`（README/PKGBUILD/controller/desktop/config/sync 脚本等 8 文件），`/media/<USER>/WS1`、`/home/<USER>` 路径占位。
- 清理上次发布误入库的运行时产物：旧控制台 `data/perf/*.tsv`、`charge_curve_*.tsv`、`data/snapshot_log.txt`、`backend/*.bak` 随 v1 目录一并移除。
- **外链处置**：原 `github.com/hackdale/system-console`（虚构、404）与 AUR 徽章已从 README/PKGBUILD 移除，仓库地址改指真实 `miaoduke/acer-aspire-a615-51g-optimization`；AUR 明确标注"尚未发布、请走源码安装"。
- 根 README 双语更新当前定稿、权威入口、目录树、05_控制台_Linux 说明、运行位置/双副本架构注记（遵循"纠错不删除"，-80mV 历史保留）。