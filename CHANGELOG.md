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