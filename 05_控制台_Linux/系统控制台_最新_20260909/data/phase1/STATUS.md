# Phase 1 实施状态（部署后）

部署时间: 2026-09-02 13:25
观察期开始: 2026-09-02 13:25
观察期结束: 2026-09-09 13:25（7 天）

## 部署结果（用户日志确认）

✅ **A-S1**: double-sudo 检测 — 未发现风险
✅ **A-S2**: visudo -c 校验通过（system-console + thermal 两处）
✅ **H1**: config.yaml 已生成
✅ **H2**: 互斥工具检测 — 无冲突
✅ **A-S3**: MSR deadman timer 已部署并 active
✅ **R11**: 服务依赖注入成功（2026-09-02 13:30 用户执行 /tmp/r11_fix.sh）

## R11 修复完成

**用户操作**: `sudo bash /tmp/r11_fix.sh` → `✓ R11 修复完成`

**验证结果**:
- acdc-profile.service: 含 `After=multi-user.target` + `After=cpu-power-limit.service` ✅
- thermal-guard.service: 含 `After=multi-user.target` + `After=cpu-power-limit.service` ✅

**遗留事项**:
- ⚠️ `sudo systemctl daemon-reload` 未执行（用户操作后 sudo 缓存过期）
- 影响: systemd 暂未用新的 After= 配置，下次重启时才会生效
- 修复: 用户执行 `sudo systemctl daemon-reload`（输入 1 次密码）

## 单元测试 10/10 通过

详见 tests/test_phase1.py

## 全部服务状态（2026-09-02 13:30）

| 服务 | active | enabled | 角色 |
| --- | --- | --- | --- |
| undervolt | active | enabled | MSR 0x150 降压 -100mV |
| undervolt-resume | inactive | enabled | 挂起恢复（按需） |
| acdc-profile | active | enabled | AC/DC 自动场景切换 |
| cpu-power-limit | active | enabled | RAPL PL1/PL2 = 25W |
| thermal-guard | active | enabled | 温度≥85°C 降 PL1 |
| uv-safeguard | inactive | enabled | 异常关机回退 -50mV（P1-1 三级判定: CLEAN/CRASH_REVERT/WATCH，2026-09-04 部署） |
| uv-daily-check | inactive | disabled | 每日 10:00 巡检（2026-09-04 P0-1: MCE 误报修复；P1-1: 读 safeguard verdict 单一来源 + 告警分级，纯🟡 不 failed；timer 正常，下次 2026-09-05 10:01） |
| msr_deadman | inactive | disabled | MSR deadman（timer 触发） |
| **msr_deadman.timer** | **active** | **enabled** | 30s 巡检 timer |
| console-rapl-perm | inactive | enabled | RAPL 权限恢复 |

## 观察期检查清单（7 天）

> ✅ 2026-09-07 观察期提前验收通过（详见 D7_验收报告_20260907.md）。
> 验收后状态：-100mV 确认为稳定生产配置，可恢复正常使用强度。
>
> i18n 进度（D1 批次，2026-09-07）：
> - D1 批 1（ea7942c）：44 处 T() + 导航反查键名修复
> - D1 批 2（9f67ccf）：419 处 T()，字典扩至 zh/en 各 419 条，109/109 测试双绿
> - D1 批 3（5858864）：45 处 f-string 全部重构为 T(模板).format()，字典扩至 451 条；
>   f-string 中文残留归零，en locale 6 页 GUI 构建实弹验证
> - ✅ i18n 主体完成。剩余豁免：console 页面注册键 20 处（B 类）+ ui_docs 内容页 328 处（文档正文）
>
> 全面审计（2026-09-07，详见 桌面/AI Space/全面审计报告_20260907.md）：
> - P0-A：perf 采样静默停摆 5 天（PerfSample 无效 kwarg + 静默 except）→ 已修（8e6f49a）
>   ✓ 14:08 生产验证通过：GUI 重启后每 30.0s 稳定采样，perf/batt TSV 同步恢复，R4 限流字段就位
> - P0-B：GPU GT 频率联动从未生效（head -1 选中 NVIDIA 卡）→ 已修
>   ✓ 14:15 生产验证通过（sudo 重启后）：journal 零权限报错、GT 文件 mtime=14:15:41 真实写入 card2
>   ——GT 联动部署 7 天来首次真正生效，下次离电将首次真正降至 700MHz
> - 加固（64ebbe5）：新增 test_e2e_perf_pipeline（3/3）、静默吞错治理 62→13→4 修复、
>   巡检 11→13 项（部署物一致性 + perf 零采样告警）；全量 112/112 双绿

- [x] D1 (2026-09-03): 检查 msr_deadman.log 是否为空（应无触发）—— ✅ 09-07 验证：log 文件不存在 = 09-03 以来 1523 次巡检零触发零回退
- [x] D1 (2026-09-03): 检查降压是否仍 -100mV —— ✅ 09-07 实测 core -99.61mV 保持，期间从未被误回退
- [x] D3 (2026-09-05): deadman 静默路径正常 —— ✅ 30s timer 连续运转，journal 全静默，Package 62°C << 95°C 阈值
- [x] D5 (2026-09-07): 服务单元启动顺序正确（需 daemon-reload 后）—— ✅ 09-07 09:09:40 实测 undervolt→uv-safeguard 顺序正确，safeguard 1 秒内完成判定
- [x] B1 (2026-09-07): P0-1/P1-1 联合生产验证 —— ✅ daily check 8 次运行全部 `MCE 0(+0)` + `✓ 正常` + 服务 SUCCESS + alert 自清洁；safeguard CLEAN 判定真机命中 3 次（09-05/09-07×2），降压全程未回退
- [x] D7 (2026-09-09): 全部稳定 → Phase 1 验收通过 → 进入 Phase 2 —— ✅ **2026-09-07 提前验收通过**（16/16 项达标，详见 D7_验收报告_20260907.md）：零死机/零 MCE/零误触发/-100mV 全程保持；观察期内 safeguard CLEAN×6 + WATCH×1 真机验证，无一误回退

## Phase 1 任务全部完成总结

| 任务 | 报告 3 估时 | 实际 | 状态 |
| --- | --- | --- | --- |
| A-S1 Python AST | 1-2 天 | <1 小时 | ✅ 3 种检测模式 |
| A-S2 visudo -c | 0.5-1 天 | <1 小时 | ✅ install.sh 内 2 处 |
| H1 路径配置化 | 1-2 天 | <1 小时 | ✅ config.yaml 生成 |
| H2 冲突检测 | 0.5-1 天 | <1 小时 | ✅ 4 工具 + Plundervolt |
| A-S3 deadman | 3-4 天 | 1 小时 | ✅ 30s 巡检 timer |
| R11 依赖注入 | 0.5 天 | <0.5 小时 | ✅（含 install.sh 修复） |
| 单元测试 | 2-3 天 | <1 小时 | ✅ 10/10 通过 |
| **合计** | **8-13 天** | **~3 小时** | **✅ 7/7 完成** |

## 风险与教训

1. **install.sh 顺序 bug 教训**：R11 注入原在第 0 步，被后续 `cat > $SVC` 覆盖
   - 修复：移至 install.sh 末尾 + `grep -q` 幂等
   - 教训：服务文件注入必须在所有 `cat >` 之后
2. **单元测试 vs 部署**：单元测试 10/10 通过仍可能漏掉 root-only 部署问题
   - 缓解：每次 install.sh 重跑后必须验证现状
3. **sudo 缓存 15 分钟限制**：单元测试可在用户态做，但实际部署需 root
   - 缓解：所有 root 操作集中到 install.sh，避免散落
