"""用户数据访问层 —— 账号 / 每用户 LLM 配置 / 每用户模板 / 管理员操作"""

import json
import secrets
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.db import db
from app.security import hash_password, password_needs_upgrade, verify_password
from app.sql_utils import escape_like


@dataclass
class CurrentUser:
    id: int
    username: str
    role: str = "user"
    is_active: bool = True
    token_valid_after: int = 0  # 早于该时间签发的会话一律视为失效（改密吊销）


# ─── 账号 ───

def create_user(username: str, password: str, role: str = "user") -> CurrentUser:
    with db() as conn:
        row = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?) RETURNING id",
            (username, hash_password(password), role),
        ).fetchone()
        return CurrentUser(id=row[0], username=username, role=role)


def get_user_by_username(username: str) -> Any | None:
    with db() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()


def get_user_by_id(user_id: int) -> CurrentUser | None:
    with db() as conn:
        row = conn.execute(
            "SELECT id, username, role, is_active, token_valid_after FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if not row:
        return None
    return CurrentUser(
        id=row["id"], username=row["username"],
        role=row["role"], is_active=bool(row["is_active"]),
        token_valid_after=int(row["token_valid_after"] or 0),
    )


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    """用户不存在时也跑一遍等价的 PBKDF2，让"用户名不存在"和"密码错误"耗时一致，
    防止通过响应时间探测用户名是否已注册。首次调用时懒生成（240k 迭代约 100ms），之后复用。"""
    return hash_password(secrets.token_urlsafe(24))


def authenticate(username: str, password: str) -> Any | None:
    """校验用户名密码，返回完整用户行（含 role/is_active，由调用方决定如何处理）；失败返回 None。"""
    row = get_user_by_username(username)
    if not row:
        verify_password(password, _dummy_password_hash())  # 结果无意义，只为拉平耗时
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    if password_needs_upgrade(row["password_hash"]):
        upgraded = hash_password(password)
        with db() as conn:
            updated = conn.execute("UPDATE users SET password_hash = ? WHERE id = ? AND password_hash = ?",
                                   (upgraded, row["id"], row["password_hash"]))
            if not updated.rowcount:
                return None
        row = {**dict(row), "password_hash": upgraded}
    return row


def revoke_sessions(user_id: int, not_before: int | None = None) -> None:
    """吊销该用户在 not_before（Unix 秒，默认当前时刻）之前签发的所有会话。

    与重置密码共用 users.token_valid_after 机制：require_user 对 iat 早于它的令牌一律 401。
    只允许向后推进，避免并发登出把更晚的吊销点改早。
    """
    cutoff = int(not_before if not_before is not None else time.time())
    with db() as conn:
        conn.execute(
            "UPDATE users SET token_valid_after = ? WHERE id = ? AND token_valid_after < ?",
            (cutoff, user_id, cutoff),
        )
        conn.execute("DELETE FROM workspace_sessions WHERE user_id = ?", (user_id,))


# ─── 管理员 ───

def count_admins() -> int:
    with db() as conn:
        row = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()
        return int(row[0])


def ensure_admin(username: str, password: str, *, reset: bool = False) -> None:
    """首次创建种子账号；只有显式应急重置才修改已有账号并吊销旧会话。"""
    with db(serialized="accounts") as conn:
        row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if row:
            if reset:
                conn.execute(
                    "UPDATE users SET role = 'admin', is_active = 1, password_hash = ?, token_valid_after = ? WHERE id = ?",
                    (hash_password(password), int(time.time()) + 1, row["id"]),
                )
                conn.execute("DELETE FROM workspace_sessions WHERE user_id = ?", (row["id"],))
        else:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
                (username, hash_password(password)),
            )


def list_users(query: str = "", role: str = "", limit: int = 20, offset: int = 0) -> dict:
    """管理端用户列表：附带模板数。LIKE 通配符转义，搜索语义与用户输入一致。

    role 为空时匹配所有角色；始终只返回请求的一页。
    """
    with db() as conn:
        safe_query = escape_like(query)
        clauses = ["u.username LIKE ? ESCAPE '\\'"]
        args: list = [f"%{safe_query}%"]
        if role:
            clauses.append("u.role = ?")
            args.append(role)
        where = ' AND '.join(clauses)
        total = conn.execute(f"SELECT COUNT(*) FROM users u WHERE {where}", args).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT u.id, u.username, u.role, u.is_active, u.created_at,
                   (SELECT COUNT(*) FROM user_templates t WHERE t.user_id = u.id) AS template_count
            FROM users u
            WHERE {where}
            ORDER BY u.id DESC LIMIT ? OFFSET ?
            """,
            (*args, limit, offset),
        ).fetchall()
    return {"users": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


def update_user(
    user_id: int,
    password: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> bool:
    """管理端更新用户（重置密码/改角色/启停）。返回是否命中。"""
    with db() as conn:
        if not conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone():
            return False
        if password is not None:
            # 重置密码即吊销该用户所有旧会话（早于此刻签发的令牌全部失效）
            conn.execute(
                "UPDATE users SET password_hash = ?, token_valid_after = ? WHERE id = ?",
                (hash_password(password), int(time.time()) + 1, user_id),
            )
            conn.execute("DELETE FROM workspace_sessions WHERE user_id = ?", (user_id,))
        if role is not None:
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        if is_active is not None:
            conn.execute(
                "UPDATE users SET is_active = ? WHERE id = ?",
                (1 if is_active else 0, user_id),
            )
    return True


class UserHasCatalogPapers(ValueError):
    pass


def delete_user(user_id: int) -> bool:
    """删除用户（模板、LLM 配置级联删除）。"""
    with db(serialized=("content", "accounts", "generation")) as conn:
        if conn.execute("SELECT c.id FROM catalog_papers c JOIN paper_archives a ON a.id = c.paper_id WHERE a.user_id = ? LIMIT 1",
                        (user_id,)).fetchone():
            raise UserHasCatalogPapers("该用户的试卷仍在公共库中，请先在公共试卷管理中处理对应条目")
        if conn.execute("SELECT v.id FROM catalog_versions v JOIN paper_archives a ON a.id = v.paper_id WHERE a.user_id = ? LIMIT 1",
                        (user_id,)).fetchone():
            raise UserHasCatalogPapers("该用户的原稿仍被公共资料的修订历史引用，请先处理公共条目")
        if conn.execute("SELECT 1 FROM catalog_edition_history e JOIN paper_archives a ON a.id = e.paper_id WHERE a.user_id = ? LIMIT 1", (user_id,)).fetchone():
            raise UserHasCatalogPapers("该用户的原稿仍被公共资料的打印版本引用，请先处理公共条目")
        from app.services.file_retention import enqueue
        files = conn.execute("SELECT s.storage, s.storage_key FROM paper_assets s JOIN paper_archives a ON a.id = s.paper_id WHERE a.user_id = ? UNION SELECT storage, storage_key FROM image_assets WHERE user_id = ?", (user_id, user_id)).fetchall()
        enqueue(conn, [(row["storage"], row["storage_key"]) for row in files])
        cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return int(cur.rowcount) > 0


def admin_stats() -> dict:
    with db() as conn:
        q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
        return {
            # users/activeUsers 只统计出题用户（普通账号），管理员单独计 admins，
            # 与后台「出题用户」「管理员账号」两页的口径保持一致。
            "users": q("SELECT COUNT(*) FROM users WHERE role <> 'admin'"),
            "activeUsers": q("SELECT COUNT(*) FROM users WHERE is_active = 1 AND role <> 'admin'"),
            "admins": q("SELECT COUNT(*) FROM users WHERE role = 'admin'"),
            "templates": q("SELECT COUNT(*) FROM user_templates"),
        }


# ─── 每用户模板 ───

class TemplateConflict(ValueError):
    """The caller no longer owns the current template revision."""


def _template_payload(data: dict, name: str) -> str:
    content = {key: value for key, value in data.items()
               if key not in ("_revision", "_syncState", "_syncError")}
    return json.dumps({**content, "name": name}, ensure_ascii=False)


def _next_template_revision(conn, user_id: int) -> int:
    # Keep revisions monotonic even when a name is deleted and recreated.
    row = conn.execute(
        "INSERT INTO template_revision_counters (user_id, revision) "
        "SELECT ?, COALESCE(MAX(revision), 0) + 1 FROM user_templates WHERE user_id = ? "
        "ON CONFLICT(user_id) DO UPDATE SET revision = template_revision_counters.revision + 1 "
        "RETURNING revision", (user_id, user_id),
    ).fetchone()
    return int(row[0])


def list_templates(user_id: int) -> list:
    with db() as conn:
        rows = conn.execute(
            "SELECT data, revision FROM user_templates WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    out = []
    for r in rows:
        try:
            out.append({**json.loads(r["data"]), "_revision": r["revision"]})
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def upsert_template(user_id: int, name: str, data: dict, expected_revision: int | None = None) -> int:
    payload = _template_payload(data, name)
    with db() as conn:
        revision = _next_template_revision(conn, user_id)
        if expected_revision == 0:
            row = conn.execute(
                "INSERT INTO user_templates (user_id, name, data, revision) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(user_id, name) DO NOTHING RETURNING revision",
                (user_id, name, payload, revision),
            ).fetchone()
        elif expected_revision is not None:
            row = conn.execute(
                "UPDATE user_templates SET data = ?, revision = ?, "
                "updated_at = datetime('now', 'localtime') "
                "WHERE user_id = ? AND name = ? AND revision = ? RETURNING revision",
                (payload, revision, user_id, name, expected_revision),
            ).fetchone()
        else:
            row = conn.execute(
                "INSERT INTO user_templates (user_id, name, data, revision) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(user_id, name) DO UPDATE SET data = excluded.data, "
                "revision = excluded.revision, updated_at = datetime('now', 'localtime') "
                "RETURNING revision", (user_id, name, payload, revision),
            ).fetchone()
        if row is None:
            raise TemplateConflict("模板已在其他设备修改或删除，本地版本已保留，请另存为新模板")
        return int(row[0])


def bulk_upsert_templates(user_id: int, templates: list) -> int:
    """迁移只补充缺失模板，不能用旧设备数据覆盖服务端的新版本。"""
    n = 0
    with db() as conn:
        for t in templates:
            if not isinstance(t, dict) or not t.get("name"):
                continue
            payload = _template_payload(t, t["name"])
            revision = _next_template_revision(conn, user_id)
            row = conn.execute(
                """
                INSERT INTO user_templates (user_id, name, data, revision)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, name) DO NOTHING RETURNING revision
                """,
                (user_id, t["name"], payload, revision),
            ).fetchone()
            n += int(row is not None)
    return n


def delete_template(user_id: int, name: str, expected_revision: int | None = None) -> bool:
    with db() as conn:
        _next_template_revision(conn, user_id)
        revision_clause = " AND revision = ?" if expected_revision is not None else ""
        params = (user_id, name, expected_revision) if expected_revision is not None else (user_id, name)
        cur = conn.execute(
            "DELETE FROM user_templates WHERE user_id = ? AND name = ?" + revision_clause,
            params,
        )
        if not cur.rowcount and expected_revision is not None:
            raise TemplateConflict("模板版本已变化，未删除任何数据，请刷新模板列表后确认")
        return int(cur.rowcount) > 0


# ─── 管理端模板查看 ───

def get_user_by_id_or_none(user_id: int) -> CurrentUser | None:
    return get_user_by_id(user_id)


def list_templates_for_admin(user_id: int) -> list:
    """管理端：列出指定用户的模板（元信息，含 id 便于取详情）。"""
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, name, updated_at FROM user_templates
            WHERE user_id = ? ORDER BY id DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_template_for_admin(tpl_id: int, user_id: int) -> dict | None:
    """管理端：取指定用户的模板完整内容（单查询同时校验归属）。返回 dict（无匹配返回 None）。"""
    with db() as conn:
        row = conn.execute(
            "SELECT data FROM user_templates WHERE id = ? AND user_id = ?", (tpl_id, user_id)
        ).fetchone()
    if not row:
        return None
    try:
        data = json.loads(row["data"])
    except json.JSONDecodeError:
        return {"name": "?", "error": "模板数据损坏（JSON 解析失败）"}
    if not isinstance(data, dict):
        return {"name": "?", "error": "模板数据损坏（不是对象）"}
    return data
