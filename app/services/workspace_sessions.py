"""工作台独立设备会话；旧令牌兼容到期，新增会话支持空闲过期和单设备退出。"""

import time
import uuid

from fastapi import HTTPException

from app.config import get_settings
from app.db import db

TOUCH_INTERVAL_SECONDS = 60


def migrate(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS workspace_sessions (
        id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at BIGINT NOT NULL, last_seen_at BIGINT NOT NULL, expires_at BIGINT NOT NULL,
        revoked_at BIGINT NOT NULL DEFAULT 0)""")
    conn.execute("CREATE INDEX IF NOT EXISTS workspace_sessions_expiry ON workspace_sessions(expires_at)")
    conn.execute("ALTER TABLE workspace_sessions ADD COLUMN IF NOT EXISTS user_agent TEXT NOT NULL DEFAULT ''")
    conn.execute("ALTER TABLE workspace_sessions ADD COLUMN IF NOT EXISTS client_ip TEXT NOT NULL DEFAULT ''")


def create(user_id: int, *, expected_hash: str | None = None, expected_after: int | None = None,
           user_agent: str = '', client_ip: str = '', mfa_verified: bool = False) -> str:
    identifier, now = uuid.uuid4().hex, int(time.time())
    with db(serialized='accounts') as conn:
        row = conn.execute("SELECT password_hash, token_valid_after, is_active FROM users WHERE id = ? FOR UPDATE", (user_id,)).fetchone()
        if (not row or not row["is_active"] or expected_hash is not None and row["password_hash"] != expected_hash
                or expected_after is not None and row["token_valid_after"] != expected_after):
            raise HTTPException(401, detail={"error": "账号凭证已更新，请重新登录", "code": "credentials_changed"})
        if not mfa_verified and conn.execute('SELECT 1 FROM admin_mfa WHERE user_id=? AND enabled=1', (user_id,)).fetchone():
            raise HTTPException(401, detail={'error': '请重新登录并完成 MFA 验证'})
        conn.execute("INSERT INTO workspace_sessions(id, user_id, created_at, last_seen_at, expires_at, user_agent, client_ip) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (identifier, user_id, now, now, now + 30 * 86400, user_agent[:300], client_ip[:100]))
    return identifier


def valid(identifier: str, user_id: int) -> bool:
    now = int(time.time())
    params = (identifier, user_id, now, now - get_settings().session_idle_seconds)
    condition = "id = ? AND user_id = ? AND revoked_at = 0 AND expires_at > ? AND last_seen_at > ?"
    with db() as conn:
        # 每次请求仍读数据库检查撤销和过期；仅将活跃时间的写入节流到每分钟一次。
        row = conn.execute("SELECT last_seen_at FROM workspace_sessions WHERE " + condition, params).fetchone()
        if row is None:
            return False
        if row['last_seen_at'] > now - TOUCH_INTERVAL_SECONDS:
            return True
        updated = conn.execute("UPDATE workspace_sessions SET last_seen_at = ? WHERE " + condition
                               + " AND last_seen_at <= ? RETURNING id",
                               (now, *params, now - TOUCH_INTERVAL_SECONDS)).fetchone()
        # 等待行锁期间，另一请求可能已更新时间或撤销会话，必须重新判断。
        return updated is not None or conn.execute(
            "SELECT id FROM workspace_sessions WHERE " + condition, params).fetchone() is not None


def revoke(identifier: str, user_id: int) -> None:
    with db() as conn:
        conn.execute("UPDATE workspace_sessions SET revoked_at = ? WHERE id = ? AND user_id = ?", (int(time.time()), identifier, user_id))


def listing(user_id: int, current_session: str = '') -> list[dict]:
    now = int(time.time())
    with db() as conn:
        return [{**dict(row), 'current': row['id'] == current_session} for row in conn.execute(
            "SELECT id, created_at, last_seen_at, expires_at, revoked_at, user_agent, client_ip FROM workspace_sessions "
            "WHERE user_id = ? AND revoked_at=0 AND expires_at>? AND last_seen_at>? ORDER BY last_seen_at DESC LIMIT 100",
            (user_id, now, now - get_settings().session_idle_seconds)
        )]


def revoke_for_admin(identifier: str, actor_id: int) -> bool:
    with db() as conn:
        return bool(conn.execute("UPDATE workspace_sessions SET revoked_at = ? WHERE id = ? AND user_id = (SELECT id FROM users WHERE id = ? AND role = 'admin') AND revoked_at = 0 RETURNING id", (int(time.time()), identifier, actor_id)).fetchone())


def prune() -> None:
    now = int(time.time())
    with db() as conn:
        conn.execute("DELETE FROM workspace_sessions WHERE id IN (SELECT id FROM workspace_sessions WHERE expires_at < ? OR revoked_at > 0 OR last_seen_at < ? LIMIT 500)", (now, now - get_settings().session_idle_seconds))
