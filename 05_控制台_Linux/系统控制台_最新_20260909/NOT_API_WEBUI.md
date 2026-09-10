# 🚫 红线：不加入 API / Web UI

> **决定日期**：2026-09-04
> **决定人**：用户（<USER>）
> **决定**：**本项目的「系统控制台」今后不加入 API（REST/JSON）和 Web UI 功能，也不加入任何网络监听服务。**

---

## 原因

- 保持项目定位为「本地单机 GUI 调优工具」
- 避免引入网络暴露面（安全风险）
- 无远程监控需求
- 保持工具轻量、单机、专注

---

## 禁止的技术

| 类别 | 具体技术 | 说明 |
| --- | --- | --- |
| **REST API** | `/api/status` 等 JSON 端点 | 禁止 |
| **Prometheus** | `/metrics` exporter | 禁止 |
| **Web UI** | Flask / http.server 网页版 | 禁止 |
| **网络服务** | 任何监听端口的 daemon（如 system-console-api） | 禁止 |

---

## 今后新增功能标准

**允许**：
- ✅ 本地 GUI（GTK3）
- ✅ 本地 CLI 工具
- ✅ systemd 本地服务（无网络端口）
- ✅ 本地数据文件（TSV / JSON / sysfs）

**禁止**：
- ❌ 任何监听网络端口的服务
- ❌ 任何对外暴露数据的端点
- ❌ Web 界面 / 浏览器访问

---

## 已删除文件（2026-09-04）

### 项目内
- ✅ `scripts/system_console_api.py`（REST API + Prometheus）
- ✅ `scripts/web_ui.py`（Web UI）
- ✅ `backend/system-console-api.service`（API systemd 单元）
- ✅ `install.sh` 中 `P2-A: REST API 服务` 部署段
- ✅ `install_bash_alias.sh` 中 `syscon-api` 别名

### 系统内（已部署的，sudo 清除）
- ✅ `/etc/systemd/system/system-console-api.service`
- ✅ `/etc/system-console/api-password`
- ✅ `system-console-api` 服务已 disable

---

## 验证状态（2026-09-04）

- ✅ 项目代码零残留（grep 无匹配）
- ✅ 88/88 测试通过（无破坏）
- ✅ install.sh 语法 OK

---

## 参考

- 相关旧报告 `v2.0_P0-P3完成报告.md` 中提到 API/Web UI 的部分**仅作历史参考**，不代表当前功能。
- 本项目当前唯一的网络相关是 `tailscale`（系统级，与项目无关）。