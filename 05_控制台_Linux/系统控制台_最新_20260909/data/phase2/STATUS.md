# Phase 2 G1 GUI 集成状态

开始时间: 2026-09-02
状态: ✅ 全部完成（核心 + 集成 + GUI 逻辑 + 真实 GTK 渲染）
部署: 未部署到生产（等 Phase 1 D7 验收 2026-09-09 后再部署）

## 完成清单

### v1.1：核心解析器
- [x] src/core/profile.py (13KB) — INI 解析器
- [x] profiles/ 目录（8 个 .conf）
- [x] tests/test_phase2_profile.py — 13/13

### v1.2：controller 集成
- [x] controller.py 集成 profile 加载 + fallback
- [x] tests/test_phase2_integration.py — 11/11

### v1.3（本次）：GUI 集成
- [x] ui_scenes.py 加 Profile 信息面板
  - 显示 8 个 profile（来源 + 描述 + 验证状态）
  - 用户覆盖时显示 👤
  - 硬编码 fallback 时显示 ⚙
  - 验证失败时显示 ✗N
- [x] tests/test_phase2_gui.py — 6/6（逻辑层）
- [x] tests/test_phase2_gui_render.py — 8/8（真实 GTK 渲染）

## GUI 面板设计

### 显示位置
ui_scenes.py 中，在 6 场景按钮区下方、M3 区上方

### 显示内容
```
Profile 配置（来源：内置 · 用户 · 硬编码）

📦 ac-bal        插电平衡 — 日常办公/开发              ✓
📦 ac-perf       插电高性能 — 编译/渲染/跑分            ✓
📦 ac-quiet      插电静音 — 夜间/安静环境                ✓
📦 balanced      Balanced — 通用平衡档（其他场景的基类）  ✓
📦 bat-bal       离电均衡 — 离电日常                    ✓
📦 bat-perf      离电性能 — 急需性能（受固件限制约 8W）  ✓
📦 bat-save      离电省电 — 最大续航                    ✓
📦 user_custom   用户自定义 — 模板                      ✓
```

### 来源标记规则
- 📦（绿）= 内置目录
- 👤（紫）= 用户目录覆盖
- ⚙（棕）= 硬编码 fallback

### 验证状态
- ✓（绿）= 验证通过
- ✗N（红）= N 个错误

## 关键设计决策

### 1. 不修改现有 UI 结构
Profile 面板**插入**到 M3 区之前，**不影响**：
- 6 场景按钮（按原方式显示）
- M3 切换
- 基准测试
- 自动切换默认档位

### 2. 只读视图（不做切换）
当前面板**只显示** profile 元信息，**不**做切换逻辑。切换仍由 6 场景按钮完成（每个按钮对应一个 profile）。

### 3. 复用现有组件
- 用 `Gtk.Label` + `use_markup=True` 显示彩色文本
- 用现有 `section-title` / `dim-text` CSS 类
- 复用 `get_loader()` 和 `validate_profile()` 函数

### 4. 性能
- profile 列表在 `__init__` 时加载（8 个 < 5ms）
- 验证按需调用（8 个 < 50ms）
- 整体 init 增加 < 100ms

## 累计测试统计

| 套件 | 通过率 |
| --- | --- |
| Phase 1 (test_phase1.py) | 10/10 |
| Phase 2 G1 核心 (test_phase2_profile.py) | 13/13 |
| Phase 2 G1 集成 (test_phase2_integration.py) | 11/11 |
| Phase 2 G1 GUI 逻辑 (test_phase2_gui.py) | 6/6 |
| Phase 2 G1 GUI 渲染 (test_phase2_gui_render.py) | 8/8 |
| **合计** | **48/48** |

## 实际 vs 报告估时

| 步骤 | 报告估时 | 实际 |
| --- | --- | --- |
| 核心解析器 | 3-5 天 | <1 小时 |
| 8 个内置 profile | 1-2 天 | <0.5 小时 |
| 验证器 | 1 天 | <0.5 小时 |
| 单元测试 | 1-2 天 | <1 小时 |
| 向后兼容 | 1 天 | <0.5 小时 |
| 集成 controller | 含在 9-15 天 | <1.5 小时 |
| GUI 集成 | 3-5 天 | <1 小时 |
| GUI 渲染测试 | 含 1-2 天 | <0.5 小时 |
| **合计** | **13-23 天** | **<6 小时** |

## 用户立即可见效果

启动控制台 → 系统场景页 → 6 场景按钮下方：

```
[原有 6 场景按钮不变]

[新] Profile 配置（来源：内置 · 用户 · 硬编码）
  📦 ac-bal   插电平衡 — 日常办公/开发    ✓
  📦 ac-perf  插电高性能 — 编译/渲染/跑分  ✓
  ... (8 行)
```

## 风险评估

| 风险 | 评估 | 缓解 |
| --- | --- | --- |
| GUI 启动慢 | 🟢 +100ms | 缓存 + lazy load |
| 用户 profile 写错显示 ✗N | 🟢 友好提示 | 验证器即时反馈 |
| 真实 GTK 渲染不工作 | 🟢 8/8 通过 | test_phase2_gui_render.py 覆盖 |
| 部署到生产 | 🟡 等 D7 | 用 install.sh 部署 |

## 下一步（用户决定）

A. **继续 Phase 2 G2（plugin 抽象）** —— 仍受单变量原则限制
B. **部署 Phase 2 到生产** —— 需等 D7 (2026-09-09) + 真实环境测试
C. **用户手动启动 GUI 验证** —— 直接 `python3 console.py` 看效果
D. **等 D7 自动评估** —— 让 Phase 1 跑完 7 天再决定
