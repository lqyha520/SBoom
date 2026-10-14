"""Build both frontends first; this runner starts and always stops a disposable API."""

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SUITES = ("http", "home", "profile", "discovery", "performance")


def run_fixture(suite="http"):
    with socket.socket() as socket_:
        socket_.bind(("127.0.0.1", 0))
        port = socket_.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "LC_TEST_BASE": base, "PYTHONIOENCODING": "utf-8", "HOME_UI_BASE": base, "PROFILE_UI_BASE": base,
           "MINI_UI_BASE": base, "DISCOVERY_UI_BASE": base, "NODE_PATH": str(ROOT / "web" / "node_modules")}
    if suite != "http":
        env.update(LC_WEB_DIST=str(ROOT / "miniprogram" / "dist" / "build" / "h5"), LC_SEED_MINI_FIXTURE="1")
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as log:
        fixture = "tests/profile_ui_fixture.py" if suite in ("profile", "discovery") else "tests/ui_fixture.py"
        process = subprocess.Popen([sys.executable, fixture, "--port", str(port)],
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
            if suite != "http":
                script = {"profile": "tests/profile-membership-ui.cjs", "home": "tests/home-banner-ui.cjs",
                          "discovery": "tests/mini-discovery-ui.cjs", "performance": "tests/mini-performance-ui.mjs"}[suite]
                subprocess.run(["node", script], cwd=ROOT, env=env, check=True)
                if suite == "profile":
                    subprocess.run(["node", "tests/mini-optimization-ui.mjs"], cwd=ROOT,
                                   env={**env, "MINI_UI_BASE": base}, check=True)
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=(*SUITES, "all"), default="http")
    parser.add_argument("--browser", action="store_true", help="Run all suites (legacy alias)")
    args = parser.parse_args()
    for suite in SUITES if args.browser or args.suite == "all" else (args.suite,):
        run_fixture(suite)
