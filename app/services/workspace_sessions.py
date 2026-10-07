"""工作台独立设备会话；旧令牌兼容到期，新增会话支持空闲过期和单设备退出。"""

import time
import uuid

from fastapi import HTTPException

from app.config import get_settings
from app.db import db


def migrate(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS workspace_sessions (
        id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at BIGINT NOT NULL, last_seen_at BIGINT NOT NULL, expires_at BIGINT NOT NULL,
        revoked_at BIGINT NOT NULL DEFAULT 0)""")
    conn.execute("CREATE INDEX IF NOT EXISTS workspace_sessions_expiry ON workspace_sessions(expires_at)")


def create(user_id: int, *, expected_hash: str | None = None, expected_after: int | None = None) -> str:
    identifier, now = uuid.uuid4().hex, int(time.time())
    with db() as conn:
        row = conn.execute("SELECT password_hash, token_valid_after, is_active FROM users WHERE id = ? FOR UPDATE", (user_id,)).fetchone()
        if (not row or not row["is_active"] or expected_hash is not None and row["password_hash"] != expected_hash
                or expected_after is not None and row["token_valid_after"] != expected_after):
            raise HTTPException(401, detail={"error": "账号凭证已更新，请重新登录", "code": "credentials_changed"})
        conn.execute("INSERT INTO workspace_sessions(id, user_id, created_at, last_seen_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                     (identifier, user_id, now, now, now + 30 * 86400))
    return identifier


def valid(identifier: str, user_id: int) -> bool:
    now = int(time.time())
    with db() as conn:
        row = conn.execute("UPDATE workspace_sessions SET last_seen_at = ? WHERE id = ? AND user_id = ? AND revoked_at = 0 "
                           "AND expires_at > ? AND last_seen_at > ? RETURNING id",
                           (now, identifier, user_id, now, now - get_settings().session_idle_seconds)).fetchone()
    return row is not None


def revoke(identifier: str, user_id: int) -> None:
    with db() as conn:
        conn.execute("UPDATE workspace_sessions SET revoked_at = ? WHERE id = ? AND user_id = ?", (int(time.time()), identifier, user_id))


def prune() -> None:
    now = int(time.time())
    with db() as conn:
        conn.execute("DELETE FROM workspace_sessions WHERE id IN (SELECT id FROM workspace_sessions WHERE expires_at < ? OR revoked_at > 0 OR last_seen_at < ? LIMIT 500)", (now, now - get_settings().session_idle_seconds))
