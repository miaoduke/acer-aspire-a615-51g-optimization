"""
i18n_messages.py — 翻译字典（程序生成）

用途: UI 可翻译串索引（检查某中文串是否已收录）
  正确用法: from src.core.i18n import T; T("总览")  # → "总览"(zh) / "Overview"(en)
  （注意: 不要 T(M["总览"])——M 的值是英文键名，嵌套会双键失配，2026-09-07 实测修正）
"""

M = {
    '总览': 'Overview',  # 总览
    '电源场景': 'PowerScenes',  # 电源场景
    '电池保养': 'BatteryCare',  # 电池保养
    '高级控制': 'AdvancedControl',  # 高级控制
    '进程详情': 'Processes',  # 进程详情
    '系统维护': 'Maintenance',  # 系统维护
    '说明文档': 'Documentation',  # 说明文档
    '进入 M3（省电持久化）': 'EnterM3',  # 进入 M3（省电持久化）
    '退出 M3（恢复自动）': 'ExitM3',  # 退出 M3（恢复自动）
    '保存默认档位': 'SaveDefaults',  # 保存默认档位
    '运行基准测试（插电，约 2 分钟）': 'RunBenchmark',  # 运行基准测试（插电，约 2 分钟）
    '一键提权': 'Authorize',  # 一键提权
    '一键安装/修复': 'Install',  # 一键安装/修复
    '关闭': 'Close',  # 关闭
    '确定': 'OK',  # 确定
    '取消': 'Cancel',  # 取消
    'Profile 配置（来源：内置 · 用户 · 硬编码）': 'ProfilePanelTitle',  # Profile 配置（来源：内置 · 用户 · 硬编码）
    '内置': 'Builtin',  # 内置
    '用户': 'User',  # 用户
    '硬编码': 'Hardcoded',  # 硬编码
    '场景': 'Scene',  # 场景
    '电源': 'Power',  # 电源
    '电池': 'Battery',  # 电池
    '温度': 'Temperature',  # 温度
    '限流状态': 'Throttling',  # 限流状态
    'CPU': 'CPU',  # CPU
    'GPU': 'GPU',  # GPU
    'M3 离电效能模式：': 'M3Label',  # M3 离电效能模式：
    '保存': 'Save',  # 保存
    '● M3 生效中（PPD=power-saver 持久化，acdc 自动切换已停）': 'M3Active',  # ● M3 生效中（PPD=power-saver 持久化，acdc 自动切换已停）
    '○ M3 未启用': 'M3Inactive',  # ○ M3 未启用
    '当前默认：': 'CurrentDefault',  # 当前默认：
    '插电 → ': 'ACDefault',  # 插电 → 
    '离电 → ': 'DCDefault',  # 离电 → 
    '（插拔电自动应用，也可手动切换任意场景）': 'AutoSwitchHint',  # （插拔电自动应用，也可手动切换任意场景）
}
