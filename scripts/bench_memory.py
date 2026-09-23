"""后端内存行为观测（可重复运行，用于排查"内存一直涨"的疑虑）

用法：
    python scripts/bench_memory.py                      # 只看当前占用（快照）
    python scripts/bench_memory.py --watch 60           # 连续采样 60 秒
    python scripts/bench_memory.py --load 180           # 边压测边采样 180 秒，结束后静置观察

要点（踩过的坑）：
- **不要读 netstat 给出的监听 PID** —— 那是 uvicorn 的 master 进程，只负责监听转发、
  线程只有 2 个、内存恒定不变，读它永远看不到任何变化。真正处理请求的是它的**子进程**。
- 判定泄漏的标准是「RSS 是否随请求数**单调上升且不收敛**」。
  Python 的 pymalloc 不会积极把空闲 arena 还给 OS，所以内存涨到一个水位后**横盘是正常的**，
  线程池（asyncio 默认 max=min(32, 核数+4) 个线程）常驻也属于正常开销。
"""
import argparse
import ctypes
import os
import platform
import subprocess
import sys
import threading
import time

IS_WIN = platform.system() == "Windows"

if IS_WIN:
    import ctypes.wintypes as wt
    # WinDLL 只存在于 Windows。CI 的 mypy 跑在 Linux 上，直接写 ctypes.WinDLL 会报
    # attr-defined；而 pyproject 开了 warn_unused_ignores，平台相关的 type: ignore
    # 又会在 Windows 本机变成"未使用"。故用常量取属性，两个平台判定一致。
    _WinDLL = getattr(ctypes, "WinDLL")  # noqa: B009 — 取属性只为绕过平台差异，理由见上
    _kernel32 = _WinDLL("kernel32")
    _psapi = _WinDLL("psapi")

    class _PMC(ctypes.Structure):
        _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

    class _PE32(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                    ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)), ("th32ModuleID", wt.DWORD),
                    ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
                    ("pcPriClassBase", wt.LONG), ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_char * 260)]


def _all_procs():
    """返回 [(pid, ppid, name, nthreads)]"""
    TH32CS_SNAPPROCESS = 0x00000002
    snap = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    out, pe = [], _PE32()
    pe.dwSize = ctypes.sizeof(_PE32)
    ok = _kernel32.Process32First(snap, ctypes.byref(pe))
    while ok:
        out.append((pe.th32ProcessID, pe.th32ParentProcessID,
                    pe.szExeFile.decode("gbk", "ignore"), pe.cntThreads))
        ok = _kernel32.Process32Next(snap, ctypes.byref(pe))
    _kernel32.CloseHandle(snap)
    return out


def _stat(pid):
    """返回 (工作集bytes, 峰值bytes, 线程数, 句柄数)；失败返回 None"""
    if not IS_WIN:
        try:
            with open(f"/proc/{pid}/status") as fh:
                txt = fh.read()
            rss = next(int(line.split()[1]) * 1024 for line in txt.splitlines() if line.startswith("VmRSS:"))
            peak = next(int(line.split()[1]) * 1024 for line in txt.splitlines() if line.startswith("VmHWM:"))
            th = next(int(line.split()[1]) for line in txt.splitlines() if line.startswith("Threads:"))
            return rss, peak, th, len(os.listdir(f"/proc/{pid}/fd"))
        except Exception:
            return None
    h = _kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
    if not h:
        return None
    try:
        pmc = _PMC()
        pmc.cb = ctypes.sizeof(_PMC)
        _psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
        hd = wt.DWORD()
        _kernel32.GetProcessHandleCount(h, ctypes.byref(hd))
        th = next((n for p, pp, nm, n in _all_procs() if p == pid), 0)
        return pmc.WorkingSetSize, pmc.PeakWorkingSetSize, th, hd.value
    finally:
        _kernel32.CloseHandle(h)


def find_workers(port, cwd):
    """定位 uvicorn master 及其 worker 子进程。返回 (master_pid, [worker_pid...])"""
    out = subprocess.run(["netstat", "-ano"] if IS_WIN else ["ss", "-lptn"],
                         capture_output=True, text=True, errors="ignore").stdout
    master = None
    for line in out.splitlines():
        if f":{port} " in line and ("LISTENING" in line or "LISTEN" in line):
            for tok in line.split():
                if tok.isdigit():
                    master = int(tok)
    if master is None:
        print(f"端口 {port} 上没有监听进程 —— 服务没在跑？")
        sys.exit(1)

    kids = [p for p, pp, nm, n in _all_procs()
            if pp == master and "python" in nm.lower()] if IS_WIN else []
    if not kids and not IS_WIN:
        try:
            with open(f"/proc/{master}/task/{master}/children") as children:
                kids = [int(pid) for pid in children.read().split()]
        except Exception:
            kids = []

    # 交叉验证：从启动日志里的 "Started server process [PID]" 取
    import os
    log_pids = []
    logf = os.path.join(cwd, "server.log")
    if os.path.exists(logf):
        import re
        txt = open(logf, encoding="utf-8", errors="ignore").read()
        log_pids = [int(m) for m in re.findall(r"Started server process \[(\d+)\]", txt)][-8:]

    # Windows 的 PID 会被复用：日志里记录过的 PID 现在可能属于**完全无关的进程**，
    # 只按 PID 读内存会读串。必须校验进程名，且只信 master 的直接子进程。
    if IS_WIN:
        alive_python = {p for p, pp, nm, n in _all_procs() if "python" in nm.lower()}
    else:
        alive_python = set(log_pids)
    # 优先只信 master 的直接子进程；拿不到才退回日志 PID（并限于是 python 进程）
    workers = sorted(kids) if kids else sorted({p for p in log_pids if p in alive_python})
    return master, workers


def snap(workers, label=None):
    rows = [(p, _stat(p)) for p in workers]
    rows = [(p, s) for p, s in rows if s]
    rss = sum(s[0] for _, s in rows)
    peak = sum(s[1] for _, s in rows)
    th = sum(s[2] for _, s in rows)
    hd = sum(s[3] for _, s in rows)
    if label:
        print(f"  [{label}] RSS {rss/1048576:7.1f} MB | 峰值 {peak/1048576:7.1f} MB | 线程 {th:4d} | 句柄 {hd}")
        for p, s in rows:
            print(f"      PID {p:<7d} RSS {s[0]/1048576:7.1f} MB | 峰值 {s[1]/1048576:7.1f} MB | 线程 {s[2]:3d} | 句柄 {s[3]}")
    return rss, peak, th, hd, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--watch", type=int, default=0, help="纯采样秒数（不打请求）")
    ap.add_argument("--load", type=int, default=0, help="压测秒数（同时采样）")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--settle", type=int, default=90, help="压测后静置观察秒数")
    args = ap.parse_args()

    import os as _os

    import httpx
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        _os.environ.pop(k, None)
    _os.environ["NO_PROXY"] = "*"

    master, workers = find_workers(args.port, _os.getcwd())
    print(f"uvicorn master = {master}（只监听，不处理请求）")
    print(f"真正的 worker  = {workers}\n")
    if not workers:
        print("没找到 worker 子进程，退化为只观测 master（结果不可用）")
        workers = [master]

    rss0, peak0, _, _, _ = snap(workers, "基线")

    if args.watch and not args.load:
        print(f"\n连续采样 {args.watch}s（无额外负载）:")
        samples = []
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < args.watch:
            time.sleep(2)
            s = snap(workers)
            samples.append(s[0] / 1048576)
            print(f"  {time.perf_counter()-t0:4.0f}s  RSS {samples[-1]:7.1f} MB")
        print(f"\n波动: 最低 {min(samples):.1f} / 最高 {max(samples):.1f} MB（幅度 {max(samples)-min(samples):.1f} MB）")
        return

    if not args.load:
        return

    stop, counts = threading.Event(), [0] * args.concurrency
    paths = ["/health", "/openapi.json", "/"]

    def hammer(i):
        with httpx.Client(base_url=args.base, timeout=30) as cli:
            while not stop.is_set():
                try:
                    cli.get(paths[(i + counts[i]) % len(paths)])
                except Exception:
                    pass
                counts[i] += 1

    print(f"\n压测 {args.load}s / {args.concurrency} 并发（只打公开只读端点，不影响数据）:")
    for i in range(args.concurrency):
        threading.Thread(target=hammer, args=(i,), daemon=True).start()

    samples = []
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < args.load:
        time.sleep(2)
        s = snap(workers)
        samples.append(s[0] / 1048576)
        print(f"  {time.perf_counter()-t0:4.0f}s  RSS {samples[-1]:7.1f} MB | 请求 {sum(counts)}")
    stop.set()
    print(f"\n压测结束，总请求 {sum(counts)}")

    time.sleep(3)
    print(f"\n静置 {args.settle}s（看是否归还）:")
    for sample_index in range(max(1, args.settle // 15)):
        time.sleep(15)
        r = snap(workers)[0] / 1048576
        print(f"  +{(sample_index+1)*15:3d}s  RSS {r:7.1f} MB")

    print("\n── 判定 ──")
    n = max(1, len(samples) // 5)
    early, late = sum(samples[:n]) / n, sum(samples[-n:]) / n
    print(f"  前段均值 {early:6.1f} MB → 后段均值 {late:6.1f} MB (Δ{late-early:+.1f} MB)")
    print(f"  全程波动 {max(samples)-min(samples):.1f} MB")
    if late - early > max(5.0, rss0 / 1048576 * 0.15):
        print("  ⚠️ 后段明显高于前段，建议进一步排查（可能是泄漏或分配器水位偏高）")
    else:
        print("  ✅ 未出现单调增长 —— 内存占用收敛，无泄漏迹象")
    print("  （参考：Python 会保留空闲内存块以便复用，涨到水位后横盘属正常）")


if __name__ == "__main__":
    main()
