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


def run_fixture(browser_only=False):
    with socket.socket() as socket_:
        socket_.bind(("127.0.0.1", 0))
        port = socket_.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "LC_TEST_BASE": base, "PYTHONIOENCODING": "utf-8", "HOME_UI_BASE": base, "NODE_PATH": str(ROOT / "web" / "node_modules")}
    if browser_only:
        env.update(LC_WEB_DIST=str(ROOT / "miniprogram" / "dist" / "build" / "h5"), LC_SEED_MINI_FIXTURE="1")
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
            if browser_only:
                subprocess.run(["node", "tests/home-banner-ui.cjs"], cwd=ROOT, env=env, check=True)
            else:
                subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_ui_contracts.py", "-v"], cwd=ROOT, env=env, check=True)
                subprocess.run([sys.executable, "scripts/admin_console_check.py"], cwd=ROOT, env=env, check=True)
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
    run_fixture()
    if "--browser" in sys.argv:
        run_fixture(browser_only=True)
