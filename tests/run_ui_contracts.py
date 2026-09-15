"""Build both frontends first; this runner starts and always stops a disposable API."""

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    with socket.socket() as socket_:
        socket_.bind(("127.0.0.1", 0))
        port = socket_.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "LC_TEST_BASE": base, "PYTHONIOENCODING": "utf-8"}
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "tests/ui_fixture.py", "--port", str(port)],
                                   cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Disposable service failed to start")
                try:
                    if httpx.get(base + "/health", timeout=1).json().get("fixture") is True:
                        break
                except (httpx.HTTPError, ValueError):
                    pass
                time.sleep(0.2)
            else:
                raise TimeoutError("Disposable service did not become healthy")
            subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_ui_contracts.py", "-v"], cwd=ROOT, env=env, check=True)
            subprocess.run([sys.executable, "test_admin_console.py"], cwd=ROOT, env=env, check=True)
        except Exception:
            log.seek(0)
            print(log.read(), file=sys.stderr)
            raise
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
