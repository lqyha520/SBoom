"""用户数据访问层 —— 账号 / 每用户 LLM 配置 / 每用户模板 / 管理员操作"""

import json
import time
from dataclasses import dataclass
from typing import Any, Optional

from app.db import db
from app.security import hash_password, verify_password


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


def get_user_by_username(username: str) -> Optional[Any]:
    with db() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()


def get_user_by_id(user_id: int) -> Optional[CurrentUser]:
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


def authenticate(username: str, password: str) -> Optional[Any]:
    """校验用户名密码，返回完整用户行（含 role/is_active，由调用方决定如何处理）；失败返回 None。"""
    row = get_user_by_username(username)
    if not row or not verify_password(password, row["password_hash"]):
        return None
    return row


# ─── 管理员 ───

def count_admins() -> int:
    with db() as conn:
        return conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]


def ensure_admin(username: str, password: str) -> None:
    """确保存在指定管理员（env 种子）：不存在则创建，存在则对齐角色/状态/密码。"""
    with db() as conn:
        row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if row:
            conn.execute(
                "UPDATE users SET role = 'admin', is_active = 1, password_hash = ? WHERE id = ?",
                (hash_password(password), row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
                (username, hash_password(password)),
            )


def list_users(query: str = "") -> list:
    """管理端用户列表：附带模板数。LIKE 通配符转义，搜索语义与用户输入一致。"""
    with db() as conn:
        safe_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = conn.execute(
            """
            SELECT u.id, u.username, u.role, u.is_active, u.created_at,
                   (SELECT COUNT(*) FROM user_templates t WHERE t.user_id = u.id) AS template_count
            FROM users u
            WHERE u.username LIKE ? ESCAPE '\\'
            ORDER BY u.id DESC
            """,
            (f"%{safe_query}%",),
        ).fetchall()
    return [dict(r) for r in rows]


def update_user(
    user_id: int,
    password: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> bool:
    """管理端更新用户（重置密码/改角色/启停）。返回是否命中。"""
    with db() as conn:
        if not conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone():
            return False
        if password is not None:
            # 重置密码即吊销该用户所有旧会话（早于此刻签发的令牌全部失效）
            conn.execute(
                "UPDATE users SET password_hash = ?, token_valid_after = ? WHERE id = ?",
                (hash_password(password), int(time.time()), user_id),
            )
        if role is not None:
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        if is_active is not None:
            conn.execute(
                "UPDATE users SET is_active = ? WHERE id = ?",
                (1 if is_active else 0, user_id),
            )
    return True


def delete_user(user_id: int) -> bool:
    """删除用户（模板、LLM 配置级联删除）。"""
    with db() as conn:
        cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return cur.rowcount > 0


def admin_stats() -> dict:
    with db() as conn:
        q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
        return {
            "users": q("SELECT COUNT(*) FROM users"),
            "activeUsers": q("SELECT COUNT(*) FROM users WHERE is_active = 1"),
            "admins": q("SELECT COUNT(*) FROM users WHERE role = 'admin'"),
            "templates": q("SELECT COUNT(*) FROM user_templates"),
        }


# ─── 每用户模板 ───

def list_templates(user_id: int) -> list:
    with db() as conn:
        rows = conn.execute(
            "SELECT data FROM user_templates WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    out = []
    for r in rows:
        try:
            out.append(json.loads(r["data"]))
        except json.JSONDecodeError:
            continue
    return out


def upsert_template(user_id: int, name: str, data: dict) -> None:
    payload = json.dumps(data, ensure_ascii=False)
    with db() as conn:
        conn.execute(
            """
            INSERT INTO user_templates (user_id, name, data)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, name) DO UPDATE SET
                data = excluded.data,
                updated_at = datetime('now', 'localtime')
            """,
            (user_id, name, payload),
        )


def bulk_upsert_templates(user_id: int, templates: list) -> int:
    """迁移用：批量 upsert，返回成功条数"""
    n = 0
    with db() as conn:
        for t in templates:
            if not isinstance(t, dict) or not t.get("name"):
                continue
            payload = json.dumps(t, ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO user_templates (user_id, name, data)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, name) DO UPDATE SET
                    data = excluded.data,
                    updated_at = datetime('now', 'localtime')
                """,
                (user_id, t["name"], payload),
            )
            n += 1
    return n


def delete_template(user_id: int, name: str) -> bool:
    with db() as conn:
        cur = conn.execute(
            "DELETE FROM user_templates WHERE user_id = ? AND name = ?",
            (user_id, name),
        )
        return cur.rowcount > 0


# ─── 管理端模板查看 ───

def get_user_by_id_or_none(user_id: int) -> Optional[CurrentUser]:
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


def get_template_for_admin(tpl_id: int, user_id: int) -> Optional[dict]:
    """管理端：取指定用户的模板完整内容（单查询同时校验归属）。返回 dict（无匹配返回 None）。"""
    with db() as conn:
        row = conn.execute(
            "SELECT data FROM user_templates WHERE id = ? AND user_id = ?", (tpl_id, user_id)
        ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["data"])
    except json.JSONDecodeError:
        return {"name": "?", "error": "模板数据损坏（JSON 解析失败）"}
