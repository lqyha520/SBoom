"""保守整理诊断产物：默认 dry-run，备份/密钥/环境/链接永不自动删除。"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC_SUFFIXES = {".txt", ".log", ".py", ".sh", ".ps1", ".cjs", ".mjs", ".js", ".png", ".jpg", ".html"}
PROTECTED_PARTS = {"backups", "backup", "deploy", "release", "releases", ".venv", "venv", "fixes-python", "node_modules", "p1", "p2-p3-2026-09-28"}


def inside(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


def inventory(root: Path, days: float, now: float | None = None) -> list[dict[str, Any]]:
    root = root.resolve(strict=True)
    cutoff = (time.time() if now is None else now) - days * 86400
    result: list[dict[str, Any]] = []
    for directory, directories, files in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in list(directories):
            path = base / name
            if path.is_symlink() or not inside(path, root) or name.lower() in PROTECTED_PARTS or (path / "pyvenv.cfg").exists():
                result.append({"path": str(path.relative_to(root)), "action": "protect", "reason": "environment-backup-evidence-or-link"})
                directories.remove(name)
            elif name.startswith(("p1-", "p2-", "p3-")):
                result.append({"path": str(path.relative_to(root)), "action": "protect", "reason": "review-evidence"})
                directories.remove(name)
        for name in files:
            path = base / name
            relative = path.relative_to(root)
            stat = path.lstat()
            reason = ""
            if path.is_symlink() or not inside(path, root):
                reason = "link-or-outside-root"
            elif name.startswith(".env") or "secret" in name.lower() or "backup" in name.lower() or re.search(r"(?:^|[_-])p[123](?:[_-]|\.)", name, re.I) or path.suffix.lower() not in DIAGNOSTIC_SUFFIXES:
                reason = "potential-backup-secret-or-unclassified"
            elif stat.st_mtime >= cutoff:
                reason = "within-retention"
            result.append({"path": str(relative), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                           "action": "protect" if reason else "candidate", "reason": reason or "expired-diagnostic"})
    return result


def apply_plan(root: Path, plan: list[dict[str, Any]], archive_loose: bool) -> list[str]:
    """逐项重验路径和文件身份；归档不覆盖，删除仅限本次计划中的过期诊断。"""
    root = root.resolve(strict=True)
    changed: list[str] = []
    for item in plan:
        if item["action"] != "candidate":
            continue
        path = root / item["path"]
        if not inside(path, root) or path.is_symlink() or not path.is_file():
            raise ValueError("候选文件已变成链接或离开目标目录")
        stat = path.stat()
        if (stat.st_size, stat.st_mtime_ns) != (item["bytes"], item["mtime_ns"]):
            raise ValueError("候选文件在扫描后被修改，停止整理")
        if archive_loose:
            if path.parent != root:
                continue
            day = time.strftime("%Y-%m-%d", time.localtime(stat.st_mtime))
            destination = root / f"loose-archive-{day}" / path.name
            if not inside(destination, root) or destination.exists():
                raise ValueError("归档目标在目录外或已存在")
            destination.parent.mkdir(exist_ok=True)
            path.rename(destination)
        else:
            path.unlink()
        changed.append(item["path"])
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "artifacts")
    parser.add_argument("--days", type=float, default=30)
    parser.add_argument("--dry-run", action="store_true", help="默认行为；仅打印清单")
    parser.add_argument("--apply", action="store_true", help="显式执行过期诊断清理")
    parser.add_argument("--archive-loose", action="store_true", help="只将过期顶层诊断移入按日期命名的目录，不删除")
    args = parser.parse_args()
    if args.days < 1 or args.apply and args.dry_run:
        parser.error("保留期至少1天，--apply 与 --dry-run 互斥")
    root = args.root.resolve(strict=True)
    if root.name != "artifacts" or root == Path(root.anchor) or args.root.is_symlink():
        parser.error("目标必须是已解析的 artifacts 目录")
    plan = inventory(root, args.days)
    changed = apply_plan(root, plan, args.archive_loose) if args.apply else []
    print(json.dumps({"root": str(root), "dry_run": not args.apply, "days": args.days,
                      "mode": "archive-loose" if args.archive_loose else "delete-expired-diagnostics",
                      "changed": changed, "files": plan}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
