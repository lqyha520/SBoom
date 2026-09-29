"""独立监督进程启动本地服务；launcher.log 单独轮转，停止通过随机令牌控制通道。"""
from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
PID_FILE = ROOT / "server.pid"
LOG_FILE = ROOT / "data" / "logs" / "launcher.log"
IS_WIN = os.name == "nt"


def endpoint() -> tuple[str, int]:
    host = os.environ.get("HOST", "127.0.0.1")
    return ("127.0.0.1" if host in {"0.0.0.0", "::"} else host, int(os.environ.get("PORT", "8000")))


def health(host: str, port: int) -> bool:
    try:
        with build_opener(ProxyHandler({})).open(f"http://{host}:{port}/readyz", timeout=2) as response:
            return bool(response.status == 200)
    except Exception:
        return False


def read_state() -> dict[str, Any] | None:
    try:
        state = json.loads(PID_FILE.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or state.get("root") != str(ROOT) or not isinstance(state.get("token"), str):
            return None
        return state
    except (OSError, ValueError):
        return None


def control(command: str, state: dict[str, Any]) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(state["port"])), timeout=2) as connection:
            connection.sendall(f"{command} {state['token']}\n".encode())
            return connection.recv(16) == b"ok\n"
    except (OSError, KeyError, ValueError):
        return False


def stop() -> int:
    state = read_state()
    if state is None or not control("stop", state):
        print("无法验证本脚本启动的监督进程；未终止任何 PID。旧格式 server.pid 需人工核对。")
        return 1
    for _ in range(80):
        if read_state() != state:
            print("监督进程已关闭。")
            return 0
        time.sleep(0.25)
    print("已请求停止，仍在等待子进程退出。")
    return 1


def supervise() -> int:
    token = os.environ.pop("LC_LAUNCHER_TOKEN", "")
    if len(token) < 32:
        return 1
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024**2, backupCount=3, encoding="utf-8")
    logger = logging.getLogger("launcher")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(2)
        listener.settimeout(0.5)
        state = {"pid": os.getpid(), "port": listener.getsockname()[1], "token": token, "root": str(ROOT)}
        PID_FILE.write_text(json.dumps(state), encoding="utf-8")
        if not IS_WIN:
            PID_FILE.chmod(0o600)
        child = subprocess.Popen([sys.executable, "run.py"], cwd=ROOT, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True,
                                 encoding="utf-8", errors="replace", start_new_session=not IS_WIN,
                                 creationflags=0x08000000 if IS_WIN else 0)

        def forward() -> None:
            stream = child.stdout
            assert stream is not None
            for line in iter(lambda: stream.readline(16384), ""):
                logger.info("%s", line.rstrip())

        reader = threading.Thread(target=forward, daemon=True)
        reader.start()
        logger.info("launcher started pid=%s child=%s", os.getpid(), child.pid)
        try:
            while child.poll() is None and not stopped.is_set():
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue
                with connection:
                    connection.settimeout(1)
                    try:
                        command, supplied = connection.recv(256).decode().strip().split(" ", 1)
                        if command in {"status", "stop"} and secrets.compare_digest(token, supplied):
                            connection.sendall(b"ok\n")
                            if command == "stop":
                                stopped.set()
                    except (OSError, ValueError, UnicodeError):
                        pass
        finally:
            if child.poll() is None:
                # child 仍是此监督进程持有的 Popen 对象，绝不使用过期 pid 文件杀进程。
                if IS_WIN:
                    subprocess.run(["taskkill", "/T", "/F", "/PID", str(child.pid)], capture_output=True, check=False,
                                   creationflags=0x08000000)
                else:
                    os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            reader.join(timeout=2)
            if read_state() == state:
                PID_FILE.unlink(missing_ok=True)
            logger.info("launcher stopped child_exit=%s", child.returncode)
            handler.close()
    return int(child.returncode or 0)


def start(wait: float = 40) -> int:
    host, port = endpoint()
    if health(host, port):
        print(f"{host}:{port} readyz 已通过。")
        return 0
    state = read_state()
    if state and control("status", state):
        print("监督进程已运行，但 readyz 未通过；请查看 data/logs/launcher.log。")
        return 1
    token = secrets.token_urlsafe(32)
    environment = dict(os.environ, LC_LAUNCHER_TOKEN=token, PYTHONUNBUFFERED="1")
    proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--supervise"], cwd=ROOT, env=environment,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            close_fds=True, start_new_session=not IS_WIN,
                            creationflags=0x00000008 | 0x00000200 if IS_WIN else 0)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        if health(host, port):
            print(f"readyz 已通过；监督进程 PID {proc.pid}，日志 data/logs/launcher.log。")
            return 0
        time.sleep(0.5)
    print("readyz 未通过；请查看 data/logs/launcher.log，应用日志在 data/logs/application.log。")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--stop", action="store_true")
    modes.add_argument("--status", action="store_true")
    modes.add_argument("--supervise", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--wait", type=float, default=40)
    args = parser.parse_args()
    if args.stop:
        return stop()
    if args.status:
        state = read_state()
        report = {"supervisor": bool(state and control("status", state)), "ready": health(*endpoint())}
        print(json.dumps(report))
        return 0 if report["ready"] else 1
    return supervise() if args.supervise else start(args.wait)


if __name__ == "__main__":
    raise SystemExit(main())
