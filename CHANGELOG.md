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
- **根 README 完整性复扫补漏（2026-09-10）**：修正 7 处 v1 残留——日志路径改为 v2.0 运行位置 `~/.local/share/系统控制台/data/console.log`；坑 1 加更正横幅（两 v1 目录已删，v2.0 为唯一主版本）；`.desktop` 安装「两处」→「三处」（桌面/菜单/程序目录自引用，`APP_DIR` 动态生成）；部署命令改为 `sudo bash install.sh`（v2.0 无 `--check` 参数）；脱敏文件计数 22 → 23（复扫结果）；目录树标注 `99_存档_只读` 与 `系统控制台_latest` 仅本地未入库；「第 4、8 行」→「第 4、8 节」。

## [主要内容] 重装恢复同步 2026-09-13

**Linux 重装后恢复工程回灌归档（`05_控制台_Linux/系统控制台_最新_20260909/`，+885 行/27 文件修改 + 3 新增）**

**重装恢复工程（根因：项目路径含空格 + 重装部署物丢失）**
- sudoers 无法匹配含空格路径 → 全部特权脚本走 `/usr/local/bin/sc-*.sh` 无空格别名符号链接，controller `_alias_script()` 解析（缺失/陈旧回退原路径）。
- 脚本自定位 `dirname $0` 经符号链接算错 → 全部 `readlink -f`；服务/`.desktop` 的 Exec 含空格加引号。
- `install.sh` [0/7] 一键全自动恢复：系统包缺则自装（msr-tools/rasdaemon/perl-DBI 系列）+ `/etc/default/rasdaemon` 环境文件 + undervolt 工具 pip 自装入 `.venv-tools` + undervolt/undervolt-resume 服务缺失生成（保留现值，uv_set.sh GUI 调节不覆盖）+ thermal_ctl/thermal_guard 自动部署 + acer-wmi-battery DKMS 自注册。
- `sudo_ok()` 误报修复（optional_any 历史手动件不再作为硬门槛）；服务清单移除幽灵条目 turbo-enable。

**新功能**
- **MSR 降压 GUI 调节**（`backend/uv_set.sh` + ui_advanced 滑块）：core/cache 电气同轨联动、GPU 独立域、温度墙；范围硬校验 0~-130mV、原子改 service、应用后回读校验失败自动回滚、`undervolt-resume.service` 同步（修复挂起唤醒旧值重打）、三重守护基准随 service 自动同步、`/var/log/uv_set.log` 留痕。
- **GRUB 启动菜单时间**（`backend/grub_timeout.sh`）：秒数 + menu/hidden + RECORDFAIL_TIMEOUT 同步，备份 `.grubtime.bak` + update-grub + cfg 校验。
- **开机自启开关**（维护页 Gtk.Switch，`~/.config/autostart/system-console.desktop`）。
- **应用功耗排行增强**：内存 MB 列（cgroup v2 memory.current）、过滤 session 层级噪音、对话框级 Collector 差分（修复首次差分功耗列恒空）、RAPL 回退 MSR 0x611（内核 7.0 不再暴露 sysfs energy_uw，32bit 回绕补偿）。
- **MSR 限流读取升级**（09-13）：免密白名单下 `read_all` 单次全核读，缓存 60s→10s，熔断改 60s 半程自动恢复，dashboard 加熔断角标。

**-100mV 重装后复验收（2026-09-13）**
- 45h 观察期（09-11 14:19 应用 → 09-13 11:27，4 次成功应用记录）+ 满载复验收：360,446,487 迭代 / 1802.2 万次/秒（超历史全部记录），MCE/Memory/PCIe AER/Extlog 四类零错误，满载包温 71°C。
- **安全网 SAFE_MV 50 → 80**（`uv_safeguard.sh`：回退目标改为「上一已知稳定档」语义）。

**i18n**
- 穷尽 AST 清查新增 85+ 词条（2026-09 全部新功能 + 历史欠账），总词条 453 → **740+**，最终审计 0 漏网。

**同步治理（本次提交执行）**
- **重新脱敏 9 文件 20 处回退**（Linux 重装后从真机生产副本回灌，与上次 v1→v2.0 同步同源）：`hackdale→<USER>`（controller/config/NOT_API_WEBUI/sync 脚本/install.sh DKMS 段改用动态 `$REAL_USER`/`$REAL_HOME`）、`.desktop` 恢复运行位置占位、PKGBUILD/README 恢复真实仓库地址与占位维护者、AUR 恢复「尚未发布」声明与注释化 `yay` 示例。
- **CI 工作流提升至仓库根** `.github/workflows/test.yml`（嵌套目录内 Actions 不执行）：`working-directory` 适配 + `python`→`python3` 修正，Actions 现已真实运行。
- **CI run#1 审计修复（提升后首次运行即暴露两处继承缺陷）**：① `setup-python` 的 `cache:'pip'` 在无 requirements.txt 的仓库会立即失败（三个 matrix job 全部倒在 Set up Python 亚秒级）→ 移除该行；② `gi`(PyGObject) 无 wheel、apt 的 `python3-gi` 只对系统 Python 生效，setup-python 解释器装不上 → 工作流按实际依赖重构为三 job：`test`（纯 Python 矩阵 3.10/3.11/3.12：profile/integration/plugin/complete/i18n + shellcheck + safeguard 回归）、`test-gui`（系统 Python + python3-gi + Xvfb：GUI 逻辑/渲染/user-view/perf-pipeline e2e）、`lint`（run#1 已全绿验证）。
- 嵌套 `.gitignore` 补 `.venv-tools/` 与 `data/hardware_profile.json`（adapt_test.sh 探测产物）。
- 根 README 双语更新：09-13 重装恢复通告、定稿表（内核 31、-100mV 复验收、SAFE_MV 80、降压 GUI 节）、第 6 节新特性清单。