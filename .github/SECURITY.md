# Security Policy — 安全策略

## Supported / 支持范围

本项目为开源业余研究项目（MIT），**不提供任何安全相关的支持、补丁或 SLA**。以下仅为本项目的安全报告流程。

## Reporting a Vulnerability / 报告漏洞

若你在本仓库中发现安全漏洞（如敏感信息泄露、脚本注入、提权、依赖漏洞等）：

1. **优先私有渠道**：请通过 GitHub 私有途径（`Security → Report a vulnerability`）提交，**不要**在公开 Issue 中贴出漏洞细节（含任何疑似凭据/密钥/MAC/IP/真实用户名）。
2. 提交时请附带：影响文件/行、复现步骤、影响评估、建议修复（可选）。
3. 维护者会在**尽力而为**的时间窗口内评估并处理；因本项目为个人业余项目，**不承诺**具体修复时间线。

## 已存在的已知限制 / Known Limitations

- **本仓库刻意不含明文凭据**；文档中的 `<USER>`、`<HOSTNAME>`、`<WIN_C_UUID>` 等占位符需替换为你自己的值后才可使用（见 README「关于脱敏」）。
- 降压（intel-undervolt）、功耗墙、EC-WMI 写入等操作**可能损坏硬件或导致系统不稳定**，请谨慎在非测试机应用。

## Private data / 私有数据

`_private`、系统日志、`opencode` 会话库、OS 原厂商/OEM 产物等**不应**提交到本仓库；此类内容已被 `.gitignore` 排除。如需提交涉及逆向/受版权保护的内容，请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。