# Phase 1 实施跟踪

开始时间: 2026-09-02
完成时间: 2026-09-02（同日完成，1 次会话）
目标: 安全 + 路径配置化 (5-7 周，估时 8-12 工作日)

## 任务清单

- [x] A-S1 Python AST 静态分析 (防 double sudo) — `scripts/check_double_sudo.py`
- [x] A-S2 visudo -c 自动校验 — `install.sh` 内 2 处校验
- [x] H1 路径配置化 (config.yaml) — `src/core/config.py` + controller.py 改造
- [x] H2 conflict 检测脚本 — `scripts/check_conflicts.py`
- [x] A-S3 MSR deadman switch — `backend/msr_deadman.{sh,service,timer}`
- [x] R11 服务单元显式依赖 — `install.sh` 自动注入 After=cpu-power-limit
- [x] 单元测试套件 — `tests/test_phase1.py` (10/10 通过)
- [ ] 观察期 7 天 — 2026-09-09 前验证

## 完成统计

| 任务 | 实际产物 | 状态 |
| --- | --- | --- |
| A-S1 | scripts/check_double_sudo.py (5.7KB) | ✅ |
| A-S2 | install.sh 内 2 处 visudo -c 校验 | ✅ |
| H1 | src/core/config.py (4.2KB) + controller.py 改造 | ✅ |
| H2 | scripts/check_conflicts.py (4.2KB) | ✅ |
| A-S3 | backend/msr_deadman.{sh,service,timer} (3.2KB) | ✅ |
| R11 | install.sh 注入 After= 依赖 | ✅ |
| 测试 | tests/test_phase1.py (6.6KB) 10/10 通过 | ✅ |

## 验证清单

- [x] 所有 Python 文件语法 OK
- [x] 所有 Shell 脚本 bash -n 通过
- [x] check_double_sudo.py 能识别 2 种模式
- [x] check_conflicts.py 在干净环境退出 0
- [x] msr_deadman.sh 正常温度静默退出，触发条件正确写日志
- [x] controller.py 通过 Config 读取 base_dir

## 待安装（需 root 权限）

下列操作在 install.sh 中实现，但**当前会话无 root 权限**，需要用户后续执行：

1. `sudo cp backend/msr_deadman.sh /usr/local/bin/`
2. `sudo cp backend/msr_deadman.{service,timer} /etc/systemd/system/`
3. `sudo systemctl daemon-reload`
4. `sudo systemctl enable --now msr_deadman.timer`
5. `sudo bash install.sh`（执行 A-S2 visudo -c 校验 + R11 依赖注入）

## 观察期要求

从用户执行上述 sudo 操作后开始计算 7 天观察期：
- D1-D3: 观察降压是否仍为 -100mV，无异常回退
- D4-D5: 观察 deadman 触发条件（无高温应静默）
- D6-D7: 观察服务启动顺序（acdc-profile 在 cpu-power-limit 之后）
- 异常: 任何意外回退 / 服务启动失败 → 立即排查

## 与 v1.3 报告的对应

| 任务 | 报告 3 估时 | 实际 | 偏差 |
| --- | --- | --- | --- |
| A-S1 | 1-2 天 | <1 小时 | -95% |
| A-S2 | 0.5-1 天 | <1 小时 | -95% |
| H1 | 1-2 天 | <1 小时 | -95% |
| H2 | 0.5-1 天 | <1 小时 | -95% |
| A-S3 | 3-4 天 | 1 小时 | -95% |
| R11 | 0.5 天 | <0.5 小时 | -95% |
| 测试 | 2-3 天 | <1 小时 | -95% |
| **合计** | **8-13 天** | **~3 小时** | **-90%** |

**注**：报告 3 估时基于"全手工实现"假设；实际本次实施直接生成可工作代码，节省了 90% 时间。**但仍需 7 天观察期**——这不能跳过。
