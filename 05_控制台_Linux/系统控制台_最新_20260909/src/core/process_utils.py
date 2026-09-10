"""
src/core/process_utils.py — Phase 2 G3 实施: 进程详情 + kill/renice 工具

目的: 提供 per-process 视图（PSS / 命令行 / kill / renice）
       配合 app_power.cgroup 视图，组成完整应用监控

特性:
  - 读 /proc/<pid>/{comm, cmdline, smaps_rollup, stat, status}
  - PSS 精确内存（vs RSS 共享计数）
  - 安全 kill（信号类型可选）
  - renice 调整（-20 ~ 19 范围）
  - 进程树（pstree 风格）
"""
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class ProcessInfo:
    """单个进程信息"""
    pid: int
    name: str           # comm
    cmdline: str        # 完整命令行
    ppid: int           # 父进程 ID
    user: str           # 所有者
    state: str          # R/S/D/Z...
    rss_kb: int         # RSS 内存 KB
    pss_kb: int         # PSS 内存 KB（精确共享内存）
    cpu_pct: float      # CPU 占用 %
    threads: int        # 线程数


# ---------- A1 (2026-09-04): PSS TTL 缓存 ----------
# smaps_rollup 成本 = 内核遍历进程全部 VMA（CherryStudio 100+ VMA 单次 14ms），
# 不可绕过。但 PSS 变化慢（3s 间隔中位数 0 变化，最大 24MB/298MB ≈ 8%），
# GUI 显示单位为 MB 整数 —— 缓存 5s 内足够显示精度。
# 语义: list_processes（列表/高频）走缓存；read_process（单进程详情）仍直读保精确。
_PSS_CACHE: dict = {}          # pid -> (ts, pss_kb)
_PSS_CACHE_TTL = 5.0           # 秒（> GUI 刷新间隔 3s）
_PSS_CACHE_MAX = 512           # 防 pid 复用导致的无限增长


def _pss_cached(pid: int, proc_dir) -> int:
    """带 TTL 缓存的 PSS 读取（smaps_rollup）"""
    import time as _t
    now = _t.monotonic()
    hit = _PSS_CACHE.get(pid)
    if hit and now - hit[0] < _PSS_CACHE_TTL:
        return hit[1]
    pss_kb = 0
    try:
        smaps_rollup = proc_dir / "smaps_rollup"
        if smaps_rollup.exists():
            for line in smaps_rollup.read_text().split("\n"):
                if line.startswith("Pss:"):
                    pss_kb = int(line.split()[1])
                    break
    except (OSError, PermissionError, ValueError):
        return 0
    if len(_PSS_CACHE) >= _PSS_CACHE_MAX:
        _PSS_CACHE.clear()
    _PSS_CACHE[pid] = (now, pss_kb)
    return pss_kb


def list_processes(filter_name: Optional[str] = None, limit: int = 200) -> List[ProcessInfo]:
    """列出进程（按 PSS 降序）

    性能优化（W3 + A1 2026-09-04）: 两阶段读取
      Phase 1: 全量轻扫 comm + statm(RSS)，单项 ~0.05ms/进程
      Phase 2: 只对 RSS top-limit 做完整读取（smaps_rollup 是大头 ~0.5ms/进程）
      实测 378 进程: 511ms → ~60ms（smaps_rollup 读取 378→50 次）
      近似说明: PSS≤RSS 恒成立，预选按 RSS 取 top-N 后再按 PSS 排序，
      尾部边界可能有微小差异（对 GUI Top-50 显示无影响）
      filter_name 时不预选（匹配集小，全量完整读取，与旧行为一致）
    """
    proc_dir = Path("/proc")
    PAGE_KB = os.sysconf("SC_PAGE_SIZE") // 1024

    # ---------- Phase 1: 轻扫（comm + RSS） ----------
    light = []  # [(rss_kb, pid)]
    for entry in os.listdir(proc_dir):
        if not entry.isdigit():
            continue
        pid = int(entry)
        try:
            comm = (proc_dir / str(pid) / "comm").read_text().strip()
        except (OSError, PermissionError):
            continue
        # 过滤（快速命中；comm 不含时读 cmdline 确认）
        if filter_name and filter_name.lower() not in comm.lower():
            try:
                cmdline = (proc_dir / str(pid) / "cmdline").read_bytes()
                cmdline_str = cmdline.replace(b"\x00", b" ").decode("utf-8", "replace")
                if filter_name.lower() not in cmdline_str.lower():
                    continue
            except (OSError, PermissionError):
                continue
        rss_kb = 0
        try:
            statm = (proc_dir / str(pid) / "statm").read_text().split()
            rss_kb = int(statm[1]) * PAGE_KB
        except (OSError, PermissionError, ValueError, IndexError):
            pass
        light.append((rss_kb, pid))

    # ---------- Phase 2: top-N 完整读取（PSS 走缓存，高频刷新不重复踩 VMA） ----------
    # 非过滤模式: 按 RSS 预选 top-(limit+10)（+10 缓冲缓解 RSS/PSS 边界误差）
    if not filter_name and limit and len(light) > limit:
        light.sort(key=lambda x: x[0], reverse=True)
        light = light[:limit + 10]
    procs = []
    for _rss, pid in light:
        info = read_process(pid, use_pss_cache=True)
        if info is not None:
            procs.append(info)
    procs.sort(key=lambda p: p.pss_kb, reverse=True)
    return procs[:limit]


def read_process(pid: int, use_pss_cache: bool = False) -> Optional[ProcessInfo]:
    """读单个进程的完整信息（A1 2026-09-04: 合并重复读取 + 可选 PSS 缓存）
    stat 原来读 2 遍（PPID + CPU）、status 原来读 2 遍（Uid/Threads + VmRSS），
    各并成 1 遍；实测 50 进程全字段 164ms（原 ~400ms）
    use_pss_cache=True 时 PSS 走 5s TTL 缓存（列表高频刷新用；
    默认 False 直读保精确，供详情页）"""
    proc_dir = Path(f"/proc/{pid}")
    if not proc_dir.exists():
        return None

    # comm
    try:
        name = (proc_dir / "comm").read_text().strip()
    except (OSError, PermissionError):
        return None

    # cmdline
    try:
        cmdline_raw = (proc_dir / "cmdline").read_bytes()
        cmdline = cmdline_raw.replace(b"\x00", b" ").decode("utf-8", "replace").strip()
        if not cmdline:
            cmdline = f"[{name}]"
    except (OSError, PermissionError):
        cmdline = f"[{name}]"

    # stat ×1 —— 同时取 state/ppid/utime+stime（原来读 2 遍）
    state = "?"
    ppid = 0
    utime = stime = 0
    try:
        stat = (proc_dir / "stat").read_text()
        # stat 格式复杂，PPID 在第 4 个字段
        # 注意: name 可能含空格，要找最后一个 ')'
        rpar = stat.rfind(")")
        if rpar > 0:
            fields = stat[rpar+1:].split()
            # fields[0]=state, fields[1]=ppid, fields[2]=pgrp, ...
            if len(fields) > 0:
                state = fields[0]
            if len(fields) > 1:
                ppid = int(fields[1])
            # utime+stime 在 fields[11]+fields[12]
            if len(fields) > 12:
                utime = int(fields[11])
                stime = int(fields[12])
    except (OSError, PermissionError, ValueError):
        pass

    # status ×1 —— 同时取 Uid/Threads/VmRSS（原来读 2 遍）
    user = "?"
    threads = 0
    rss_kb = 0
    try:
        for line in (proc_dir / "status").read_text().split("\n"):
            if line.startswith("Uid:"):
                real_uid = int(line.split()[1])
                user = uid_to_username(real_uid)
            elif line.startswith("Threads:"):
                threads = int(line.split()[1])
            elif line.startswith("VmRSS:"):
                rss_kb = int(line.split()[1])
    except (OSError, PermissionError, ValueError):
        pass

    # PSS（精确共享内存）—— A1: use_pss_cache 时走 5s TTL 缓存
    if use_pss_cache:
        pss_kb = _pss_cached(pid, proc_dir)
    else:
        pss_kb = 0
        try:
            smaps_rollup = proc_dir / "smaps_rollup"
            if smaps_rollup.exists():
                for line in smaps_rollup.read_text().split("\n"):
                    if line.startswith("Pss:"):
                        pss_kb = int(line.split()[1])
                        break
        except (OSError, PermissionError, ValueError):
            pss_kb = rss_kb  # fallback

    # CPU 占用（粗略）—— A1: 复用上面 stat 已取的 utime/stime，不再重读 stat
    # 简化: 假定时钟频率 100
    total_ticks = utime + stime
    cpu_pct = min(100.0, total_ticks / 100.0)

    return ProcessInfo(
        pid=pid, name=name, cmdline=cmdline[:200], ppid=ppid,
        user=user, state=state, rss_kb=rss_kb, pss_kb=pss_kb,
        cpu_pct=cpu_pct, threads=threads,
    )


def uid_to_username(uid: int) -> str:
    try:
        import pwd
        return pwd.getpwuid(uid).pw_name
    except (KeyError, ImportError):
        return str(uid)


def kill_process(pid: int, signal: int = 15) -> tuple:
    """杀进程

    Args:
        pid: 进程 ID
        signal: 15=TERM (默认), 9=KILL, 1=HUP

    Returns:
        (returncode, stderr)
    """
    sig_name = {15: "TERM", 9: "KILL", 1: "HUP"}.get(signal, str(signal))
    try:
        if pid in (os.getpid(), 1, 0):
            return (1, f"拒绝自杀式操作 (pid={pid})")
        # 优先 sudo（避免权限问题）
        r = subprocess.run(
            ["sudo", "-n", "kill", f"-{sig_name}", str(pid)],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode != 0 and "需要密码" in r.stderr:
            return (1, "需要 sudo 授权（请在 UI 中点击一键提权）")
        return (r.returncode, r.stderr.strip())
    except Exception as e:
        return (-1, str(e))


def renice_process(pid: int, priority: int) -> tuple:
    """调整进程优先级

    Args:
        pid: 进程 ID
        priority: -20 (最高) ~ 19 (最低)

    Returns:
        (returncode, stderr)
    """
    if priority < -20 or priority > 19:
        return (1, f"priority 越界: {priority}（应在 -20 ~ 19）")
    try:
        r = subprocess.run(
            ["sudo", "-n", "renice", str(priority), "-p", str(pid)],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode != 0 and "需要密码" in r.stderr:
            return (1, "需要 sudo 授权")
        return (r.returncode, r.stderr.strip())
    except Exception as e:
        return (-1, str(e))


# CLI
def main():
    import argparse
    parser = argparse.ArgumentParser(description="进程详情 + kill/renice")
    parser.add_argument("--list", action="store_true", help="列出所有进程")
    parser.add_argument("--filter", metavar="NAME", help="过滤进程名")
    parser.add_argument("--pid", type=int, metavar="PID", help="查看单个进程")
    parser.add_argument("--kill", type=int, metavar="PID", help="杀进程 (TERM)")
    parser.add_argument("--kill-9", type=int, metavar="PID", help="强杀 (KILL)")
    parser.add_argument("--renice", type=int, nargs=2, metavar=("PID", "PRIORITY"),
                        help="调整优先级 -20~19")
    args = parser.parse_args()

    if args.list or args.filter:
        procs = list_processes(args.filter, limit=50)
        print(f"{'PID':>7} {'USER':<10} {'PSS(KB)':>10} {'CPU%':>6} {'NAME':<20} CMD")
        for p in procs:
            print(f"{p.pid:>7} {p.user:<10} {p.pss_kb:>10} {p.cpu_pct:>6.1f} {p.name:<20} {p.cmdline[:50]}")
        return 0

    if args.pid:
        p = read_process(args.pid)
        if p is None:
            print(f"❌ 进程 {args.pid} 不存在或无权限")
            return 1
        print(f"PID:      {p.pid}")
        print(f"Name:     {p.name}")
        print(f"PPID:     {p.ppid}")
        print(f"User:     {p.user}")
        print(f"State:    {p.state}")
        print(f"Threads:  {p.threads}")
        print(f"RSS:      {p.rss_kb} KB")
        print(f"PSS:      {p.pss_kb} KB")
        print(f"CPU:      {p.cpu_pct:.1f}%")
        print(f"Cmdline:  {p.cmdline}")
        return 0

    if args.kill or getattr(args, 'kill_9', None):
        pid = args.kill or args.kill_9
        sig = 9 if args.kill_9 else 15
        rc, err = kill_process(pid, sig)
        if rc == 0:
            print(f"✅ 已发信号给 PID {pid} (signal {sig})")
            return 0
        else:
            print(f"❌ kill 失败: {err}")
            return 1

    if args.renice:
        pid, prio = args.renice
        rc, err = renice_process(pid, prio)
        if rc == 0:
            print(f"✅ PID {pid} 优先级已设为 {prio}")
            return 0
        else:
            print(f"❌ renice 失败: {err}")
            return 1

    parser.print_help()
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
