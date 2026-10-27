"""按候选配置统计健康状态；数据库行锁保证多 worker 只放行一次恢复探测。"""

import hashlib
import json
import time

from app.config import get_settings
from app.db import db


def identity(candidate: dict) -> tuple[str, str, str] | None:
    kind, identifier = candidate.get("_health_kind"), candidate.get("id")
    if kind not in ("text", "image") or not identifier:
        return None
    # 只持久化不可逆摘要；地址、密钥、提示词和模型正文均不写入健康表。
    fingerprint = hashlib.sha256(json.dumps({k: v for k, v in candidate.items() if k != "_probe_lease"}, sort_keys=True).encode()).hexdigest()
    return kind, identifier, fingerprint


def claim(candidate: dict) -> bool:
    key = identity(candidate)
    if key is None:
        return True
    kind, identifier, fingerprint = key
    now = time.time()
    with db() as conn:
        conn.execute(
            "INSERT INTO provider_health(kind, profile_id, fingerprint, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(kind, profile_id, fingerprint) DO NOTHING", (*key, now))
        # 旧配置的健康数据最多保留一天；在途任务不会污染新配置的统计。
        conn.execute("DELETE FROM provider_health WHERE kind = ? AND profile_id = ? AND fingerprint != ? AND updated_at < ?",
                     (*key, now - 86400))
        row = conn.execute("SELECT * FROM provider_health WHERE kind = ? AND profile_id = ? AND fingerprint = ? FOR UPDATE", key).fetchone()
        if row["cooldown_until"] > now or row["probe_until"] > now:
            return False
        candidate["_probe_lease"] = 0
        if row["consecutive_failures"] >= get_settings().provider_failure_threshold:
            candidate["_probe_lease"] = now + float(candidate["timeout"]) + 10
            conn.execute("UPDATE provider_health SET probe_until = ? WHERE kind = ? AND profile_id = ? AND fingerprint = ?",
                         (candidate["_probe_lease"], *key))
        return True


def record(candidate: dict, seconds: float, *, success: bool, cooling_failure: bool = True, fallback: bool = False) -> None:
    key = identity(candidate)
    if key is None:
        return
    kind, identifier, fingerprint = key
    settings, now = get_settings(), time.time()
    with db() as conn:
        conn.execute(
            "UPDATE provider_health SET successes = successes + ?, failures = failures + ?, fallback_calls = fallback_calls + ?, "
            "total_seconds = total_seconds + ?, last_seconds = ?, last_status = ?, updated_at = ?, "
            "probe_until = CASE WHEN probe_until = ? THEN 0 ELSE probe_until END, "
            "consecutive_failures = CASE WHEN ? THEN 0 WHEN ? THEN consecutive_failures + 1 ELSE consecutive_failures END, "
            "cooldown_until = CASE WHEN ? THEN 0 WHEN ? AND consecutive_failures + 1 >= ? THEN ? ELSE cooldown_until END "
            "WHERE kind = ? AND profile_id = ? AND fingerprint = ?",
            (int(success), int(not success), int(fallback), seconds, seconds, "success" if success else "error", now,
             candidate.get("_probe_lease", 0), success, cooling_failure, success, cooling_failure, settings.provider_failure_threshold,
             now + settings.provider_cooldown_seconds, kind, identifier, fingerprint))


def release(candidate: dict) -> None:
    key = identity(candidate)
    if key is not None:
        with db() as conn:
            conn.execute("UPDATE provider_health SET probe_until = 0 WHERE kind = ? AND profile_id = ? AND fingerprint = ? AND probe_until = ?",
                         (*key, candidate.get("_probe_lease", 0)))


def summary(candidates: list[dict]) -> list[dict]:
    now = time.time()
    result = []
    with db() as conn:
        for candidate in candidates:
            key = identity(candidate)
            row = conn.execute("SELECT * FROM provider_health WHERE kind = ? AND profile_id = ? AND fingerprint = ?", key).fetchone() if key else None
            total = row["successes"] + row["failures"] if row else 0
            result.append({"id": candidate["id"], "state": (
                "cooling" if row and row["cooldown_until"] > now else
                "probing" if row and row["probe_until"] > now else
                "recovering" if row and row["consecutive_failures"] >= get_settings().provider_failure_threshold else
                "healthy" if row and row["last_status"] == "success" else
                "degraded" if row and row["last_status"] == "error" else "unknown"),
                "successes": row["successes"] if row else 0, "failures": row["failures"] if row else 0,
                "fallback_calls": row["fallback_calls"] if row else 0,
                "success_rate": row["successes"] / total if row and total else None,
                "average_seconds": row["total_seconds"] / total if row and total else None,
                "last_seconds": row["last_seconds"] if row else None,
                "retry_after_seconds": max(0, int(row["cooldown_until"] - now + 1)) if row else 0})
    return result
