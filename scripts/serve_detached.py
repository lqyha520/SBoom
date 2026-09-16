"""后台脱离会话启动服务（Windows / POSIX 通用）。

为什么需要它：
    直接 `python run.py &` 或工具里的后台任务，进程属于当前会话的进程组。
    会话一结束，子进程会被连带回收 —— 表现为"服务莫名挂掉、日志尾部却全是 200"。
    本脚本用 DETACHED_PROCESS（Windows）/ setsid（POSIX）把服务挂到独立进程组，
    使其不受父会话生命周期影响。

用法：
    python scripts/serve_detached.py            # 启动，等待健康检查通过
    python scripts/serve_detached.py --stop     # 按 server.pid 停止
    python scripts/serve_detached.py --status   # 只做健康检查

注意：Windows 上 WORKERS>1 存在端口绑定的竞态（4 worker 时出现过
      OSError [WinError 10022]），多 worker 建议跑在 Linux 容器里。
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PID_FILE = os.path.join(ROOT, "server.pid")
LOG_FILE = os.path.join(ROOT, "server.log")
IS_WIN = os.name == "nt"


def _port() -> int:
    return int(os.environ.get("PORT") or 8000)


def _host() -> str:
    return os.environ.get("HOST") or "127.0.0.1"


def _no_proxy_open(url: str, timeout: float = 5.0):
    """绕过 http_proxy：本地健康检查不该走代理。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(url, timeout=timeout)


def is_listening(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.5)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


def health(host: str, port: int) -> str:
    try:
        with _no_proxy_open(f"http://{host}:{port}/health") as r:
            return f"{r.status} {r.read().decode(errors='ignore')[:120]}"
    except urllib.error.HTTPError as exc:
        return f"HTTPError {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__name__}: {exc}"


def read_pid() -> int | None:
    try:
        with open(PID_FILE, encoding="utf-8") as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


def alive(pid: int) -> bool:
    if IS_WIN:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, errors="ignore",
        )
        return str(pid) in (out.stdout or "")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop() -> int:
    pid = read_pid()
    if not pid:
        print("没有找到 server.pid，跳过停止。")
        return 1
    if not alive(pid):
        print(f"记录的 PID {pid} 已不在运行，清理 pid 文件。")
        os.remove(PID_FILE)
        return 0
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)] if IS_WIN else ["kill", "-TERM", str(pid)],
                   capture_output=True, text=True, errors="ignore")
    for _ in range(20):
        if not alive(pid):
            break
        time.sleep(0.5)
    print(f"已停止 PID {pid}" + ("" if not alive(pid) else "（仍在运行，请手动确认）"))
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
    return 0


def start(wait: float = 40.0) -> int:
    host, port = _host(), _port()
    if is_listening(host, port):
        print(f"端口 {host}:{port} 已有服务在跑，无需重复启动。")
        print("健康检查:", health(host, port))
        return 0

    log = open(LOG_FILE, "a", encoding="utf-8", errors="ignore")
    log.write(f"\n===== serve_detached 启动 @ {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
    log.flush()

    kwargs: dict = {
        "cwd": ROOT,
        "stdout": log,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
        "close_fds": True,
    }
    if IS_WIN:
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen([sys.executable, "run.py"], **kwargs)
    with open(PID_FILE, "w", encoding="utf-8") as fh:
        fh.write(str(proc.pid))
    print(f"已拉起独立进程 PID {proc.pid}（日志 -> server.log，PID -> server.pid）")

    deadline = time.time() + wait
    while time.time() < deadline:
        if proc.poll() is not None:
            print(f"✗ 进程提前退出，returncode={proc.returncode}，请查看 server.log 末尾。")
            return 1
        if is_listening(host, port):
            print(f"✓ 端口 {host}:{port} 已就绪，健康检查: {health(host, port)}")
            return 0
        time.sleep(1.0)
    print(f"✗ 等待 {wait:.0f}s 仍未监听，请查看 server.log。")
    return 1


def status() -> int:
    host, port = _host(), _port()
    pid = read_pid()
    print(f"记录 PID: {pid if pid else '(无)'}" + (f"  存活: {alive(pid)}" if pid else ""))
    print(f"端口监听: {is_listening(host, port)}")
    print("健康检查:", health(host, port))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="脱离会话启动/停止本地服务")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--stop", action="store_true", help="停止 server.pid 记录的进程")
    g.add_argument("--status", action="store_true", help="仅查看状态")
    ap.add_argument("--wait", type=float, default=40.0, help="启动后等待就绪的秒数")
    args = ap.parse_args()
    if args.stop:
        return stop()
    if args.status:
        return status()
    return start(args.wait)


if __name__ == "__main__":
    raise SystemExit(main())
