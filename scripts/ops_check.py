"""只读检查就绪、磁盘、TLS、异地备份回执和维护失败增量；输出 JSON，失败返回 1。"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import socket
import ssl
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener


def fetch(url: str, timeout: float = 5, limit: int = 2 * 1024 * 1024) -> bytes:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("检查地址必须是无凭证的 HTTP(S) 地址")
    with build_opener(ProxyHandler({})).open(url, timeout=timeout) as response:
        if response.status != 200:
            raise ValueError("健康接口未返回 200")
        body = bytes(response.read(limit + 1))
    if len(body) > limit:
        raise ValueError("检查响应过大")
    return body


def backup_age(path: Path, now: float, max_hours: float) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("verified") is not True or data.get("offsite") is not True:
        raise ValueError("回执必须证明异地上传与完整性检查成功")
    stamp = float(data["completed_at"])
    if not math.isfinite(stamp) or stamp < 0 or stamp > now + 300:
        raise ValueError("备份回执时间在未来")
    age = max(0, now - stamp) / 3600
    return {"ok": age <= max_hours, "age_hours": round(age, 2), "max_hours": max_hours}


def maintenance_count(body: bytes) -> float:
    matches = re.findall(rb"^maintenance_failures_total(?:\{[^\n]*\})?\s+([\d.eE+-]+)\s*$", body, re.M)
    if not matches:
        raise ValueError("指标中缺少 maintenance_failures_total")
    count = sum(float(value) for value in matches)
    if count < 0 or not count < float("inf"):
        raise ValueError("维护指标不是有效计数")
    return count


def maintenance_delta(current: float, previous: float | None) -> float:
    # 计数下降说明进程重启；新进程中已经出现的失败仍应告警。
    return current if previous is None else max(0, current - previous if current >= previous else current)


def tls_days(host: str, port: int, now: float) -> float:
    context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=5) as connection:
        with context.wrap_socket(connection, server_hostname=host) as secured:
            certificate = secured.getpeercert()
            if not certificate or "notAfter" not in certificate:
                raise ValueError("TLS 证书缺少到期时间")
            expiry = certificate["notAfter"]
    return (ssl.cert_time_to_seconds(str(expiry)) - now) / 86400


def check(args: argparse.Namespace) -> dict[str, Any]:
    now = time.time()
    checks: dict[str, dict[str, Any]] = {}

    def run(name: str, operation: Any) -> None:
        try:
            checks[name] = operation()
        except Exception as exc:
            # 不回显地址、响应体或底层异常，避免查询参数和密钥进入日志。
            checks[name] = {"ok": False, "error": type(exc).__name__}

    run("readyz", lambda: {"ok": bool(fetch(args.ready_url, limit=65536))})

    def disk() -> dict[str, Any]:
        usage = shutil.disk_usage(args.disk_path)
        free_percent = usage.free * 100 / usage.total
        return {"ok": usage.free >= args.min_free_gib * 1024**3 and free_percent >= args.min_free_percent,
                "free_gib": round(usage.free / 1024**3, 2), "free_percent": round(free_percent, 2)}

    run("disk", disk)
    if args.backup_status:
        run("backup", lambda: backup_age(Path(args.backup_status), now, args.max_backup_hours))
    else:
        checks["backup"] = {"ok": False, "error": "OPS_BACKUP_STATUS 未配置"}
    host = args.tls_host or (urlsplit(args.ready_url).hostname if args.ready_url.startswith("https:") else None)
    if host:
        def certificate() -> dict[str, Any]:
            days = tls_days(host, args.tls_port, now)
            return {"ok": days >= args.min_tls_days, "days_left": round(days, 1)}
        run("tls", certificate)
    else:
        checks["tls"] = {"ok": True, "skipped": "本机 HTTP；生产应配置 HTTPS readyz 或 OPS_TLS_HOST"}

    def metrics() -> dict[str, Any]:
        current = maintenance_count(fetch(args.metrics_url))
        previous = None
        state = Path(args.state_file) if args.state_file else None
        if state and state.exists():
            previous = float(json.loads(state.read_text(encoding="utf-8"))["maintenance_failures"])
            if not math.isfinite(previous) or previous < 0:
                raise ValueError("维护计数基线无效")
        delta = maintenance_delta(current, previous)
        if state:
            state.parent.mkdir(parents=True, exist_ok=True)
            temporary = state.with_suffix(state.suffix + ".tmp")
            temporary.write_text(json.dumps({"maintenance_failures": current, "checked_at": now}), encoding="utf-8")
            temporary.replace(state)
        return {"ok": delta == 0, "total": current, "new_failures": delta,
                "baseline": previous is None, "persistent_baseline": state is not None}

    run("maintenance", metrics)
    return {"ok": all(item["ok"] for item in checks.values()), "checked_at": int(now), "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ready-url", default=os.environ.get("OPS_READY_URL", "http://127.0.0.1:8000/readyz"))
    parser.add_argument("--metrics-url", default=os.environ.get("OPS_METRICS_URL", "http://127.0.0.1:9090/metrics"))
    parser.add_argument("--disk-path", type=Path, default=Path(os.environ.get("OPS_DISK_PATH", ".")))
    parser.add_argument("--backup-status", default=os.environ.get("OPS_BACKUP_STATUS"))
    parser.add_argument("--max-backup-hours", type=float, default=27)
    parser.add_argument("--min-free-gib", type=float, default=5)
    parser.add_argument("--min-free-percent", type=float, default=15)
    parser.add_argument("--tls-host", default=os.environ.get("OPS_TLS_HOST"))
    parser.add_argument("--tls-port", type=int, default=443)
    parser.add_argument("--min-tls-days", type=float, default=14)
    parser.add_argument("--state-file", default=os.environ.get("OPS_STATE_FILE"), help="显式设置后保存维护计数基线；不配置时不写文件")
    args = parser.parse_args()
    thresholds = (args.max_backup_hours, args.min_free_gib, args.min_free_percent, args.min_tls_days)
    if any(not math.isfinite(value) or value < 0 for value in thresholds) or args.min_free_percent > 100 or not 0 < args.tls_port < 65536:
        parser.error("阈值必须是非负有限数，磁盘百分比不超过100，TLS端口为1–65535")
    report = check(args)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
