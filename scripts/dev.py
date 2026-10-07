"""管理独立 tmpfs 测试库：up / down / test。不会停止或删除日常 db 服务。"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_DSN = "postgresql://postgres:postgres@127.0.0.1:55432/postgres"


def commands(action: str, pytest_args: list[str]) -> list[list[str]]:
    compose = ["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "--profile", "tests"]
    if action == "down":
        return [compose + ["stop", "test-db"]]
    result = [compose + ["up", "-d", "--wait", "test-db"]]
    if action == "test":
        result.append([sys.executable, "-m", "pytest", "-n", "auto", *pytest_args])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["up", "down", "test"])
    parser.add_argument("--dry-run", action="store_true")
    args, extra = parser.parse_known_args()
    if args.action != "test" and extra:
        parser.error("仅 test 接受额外 pytest 参数")
    planned = commands(args.action, extra[1:] if extra[:1] == ["--"] else extra)
    if args.dry_run:
        print(json.dumps({"commands": planned, "test_database": "127.0.0.1:55432/postgres"}, ensure_ascii=False))
        return 0
    environment = dict(os.environ, LC_TEST_PG_ADMIN=TEST_DSN)
    # 测试套件自己创建 lc_test_* 库，不能继承日常业务连接。
    environment.pop("DATABASE_URL", None)
    for command in planned:
        result = subprocess.run(command, cwd=ROOT, env=environment, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
