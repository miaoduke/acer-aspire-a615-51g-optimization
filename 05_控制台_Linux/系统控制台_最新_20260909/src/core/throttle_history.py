"""
src/core/throttle_history.py — Phase 2 G6 实施: 限流历史时间轴

目的: 从 perf TSV 文件读限流字段，渲染时间轴图（ASCII + GTK）

特性:
  - 读 perf_YYYYMMDD.tsv 全部行
  - 解析 5 类限流（thermal/power/current/vr_thermal/vr_current）
  - 渲染 24h 时间轴（颜色编码）
  - 统计：总限流时长 / 各类型次数 / 严重时段
"""
import os
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from src.core.i18n import T

# 限流类型 → 颜色代码（ANSI）
THROTTLE_COLORS = {
    "throttle_thermal":    ("🔴", T("热降频")),
    "throttle_power":      ("🟡", T("功耗墙")),
    "throttle_current":    ("🔵", T("电流墙")),
    "throttle_vr_thermal": ("🟣", T("VR 热")),
    "throttle_vr_current": ("🟤", T("VR 电流")),
}

# 限流类型 → CSS 类（GTK）
THROTTLE_CSS = {
    "throttle_thermal":    "throttle-thermal",
    "throttle_power":      "throttle-power",
    "throttle_current":    "throttle-current",
    "throttle_vr_thermal": "throttle-vr-thermal",
    "throttle_vr_current": "throttle-vr-current",
}


def read_perf_log(perf_dir: Path, target_date: Optional[str] = None) -> List[Dict]:
    """读 perf TSV 文件，解析为 dict 列表

    Args:
        perf_dir: data/perf/ 目录
        target_date: 'YYYYMMDD' 或 None（最近一天）

    Returns:
        [{'datetime': 'HH:MM:SS', 'throttle_thermal': int, ...}, ...]
    """
    if target_date is None:
        target_date = datetime.now().strftime("%Y%m%d")

    path = perf_dir / f"perf_{target_date}.tsv"
    if not path.exists():
        return []

    rows = []
    with open(path, 'r', encoding='utf-8') as f:
        header = f.readline().rstrip("\n").split("\t")
        # 找各列索引
        try:
            idx = {col: header.index(col) for col in THROTTLE_COLORS.keys()}
            idx_dt = header.index("datetime")
        except ValueError:
            return []

        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < len(header):
                continue
            row = {"datetime": parts[idx_dt]}
            for col in THROTTLE_COLORS.keys():
                try:
                    row[col] = int(parts[idx[col]])
                except (ValueError, IndexError):
                    row[col] = 0
            rows.append(row)
    return rows


def compute_timeline(rows: List[Dict], hours: int = 24) -> List[Dict]:
    """把限流数据按小时聚合

    Returns:
        [{'hour': 0..23, 'thermal': sum, 'power': sum, ...}, ...]
    """
    timeline = {h: defaultdict(int) for h in range(24)}

    for row in rows:
        try:
            dt = datetime.strptime(row["datetime"], "%H:%M:%S")
            hour = dt.hour
        except ValueError:
            continue
        for col in THROTTLE_COLORS.keys():
            timeline[hour][col] += row.get(col, 0)

    return [{"hour": h, **dict(v)} for h, v in sorted(timeline.items())]


def render_ascii_timeline(timeline: List[Dict], hours: int = 24) -> str:
    """渲染 ASCII 时间轴（终端友好）

    每小时一行，最多显示 5 个限流类型（最严重的优先）
    """
    lines = []
    lines.append("=" * 70)
    lines.append(T("限流时间轴（过去 {} 小时）").format(hours))
    lines.append("=" * 70)
    lines.append("")

    # 收集所有"有数据"的小时
    active_hours = [h for h in timeline if sum(h.get(k, 0) for k in THROTTLE_COLORS) > 0]

    if not active_hours:
        lines.append(T("  🟢 过去 24h 无任何限流事件"))
        return "\n".join(lines)

    # 按小时显示（仅显示有数据的）
    for entry in timeline:
        hour = entry["hour"]
        total = sum(entry.get(k, 0) for k in THROTTLE_COLORS)
        if total == 0:
            continue

        # 按严重度排序
        events = []
        for col in ["throttle_thermal", "throttle_power", "throttle_current",
                    "throttle_vr_thermal", "throttle_vr_current"]:
            n = entry.get(col, 0)
            if n > 0:
                events.append(f"{THROTTLE_COLORS[col][0]}{THROTTLE_COLORS[col][1]}({n})")

        bar = "█" * min(20, total // 10 + 1)
        lines.append(f"  {hour:02d}:00  {bar:<20} {' '.join(events)}")

    # 总结
    total = sum(sum(h.get(k, 0) for k in THROTTLE_COLORS) for h in timeline)
    lines.append("")
    lines.append(f"  合计: {total} 次限流事件（{len(active_hours)} 个小时有数据）")

    return "\n".join(lines)


def render_text_summary(timeline: List[Dict]) -> str:
    """文本摘要（用于 GUI 显示）"""
    total_by_type = defaultdict(int)
    for entry in timeline:
        for col in THROTTLE_COLORS.keys():
            total_by_type[col] += entry.get(col, 0)

    parts = []
    for col, (icon, name) in THROTTLE_COLORS.items():
        n = total_by_type[col]
        if n > 0:
            parts.append(f"{icon}{name}({n})")

    if not parts:
        return "🟢 24h 无限流"
    return " · ".join(parts)


def get_throttle_history(perf_dir: Optional[Path] = None, hours: int = 24):
    """便捷接口：读 + 聚合 + ASCII 渲染"""
    if perf_dir is None:
        from .config import Config
        cfg = Config.get()
        perf_dir = Path(cfg.perf_log_dir)

    rows = read_perf_log(perf_dir)
    timeline = compute_timeline(rows, hours)
    return timeline, render_ascii_timeline(timeline, hours)


# CLI
def main():
    import argparse
    parser = argparse.ArgumentParser(description="限流历史时间轴")
    parser.add_argument("--hours", type=int, default=24, help="回溯小时数")
    parser.add_argument("--date", metavar="YYYYMMDD", help="指定日期（默认今天）")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    args = parser.parse_args()

    try:
        from .config import Config
    except (ImportError, ValueError):
        try:
            from src.core.config import Config
        except ImportError:
            # 兑底：硬编码默认路径
            from pathlib import Path as _P
            perf_dir = _P.home() / '.local/share/系统控制台/data/perf'
            rows = read_perf_log(perf_dir, args.date)
            timeline = compute_timeline(rows, args.hours)
            if args.summary:
                print(render_text_summary(timeline))
            else:
                print(render_ascii_timeline(timeline, args.hours))
            return
    cfg = Config.get()
    perf_dir = Path(cfg.perf_log_dir)

    rows = read_perf_log(perf_dir, args.date)
    timeline = compute_timeline(rows, args.hours)

    if args.summary:
        print(render_text_summary(timeline))
    else:
        print(render_ascii_timeline(timeline, args.hours))


if __name__ == '__main__':
    main()
