"""Independent consumer identities, opaque sessions and live VIP entitlements."""

import hashlib
import json
import logging
import secrets
import time
import uuid
from dataclasses import dataclass

import httpx
from fastapi import HTTPException

from app.config import get_settings
from app.db import db
from app.models.mini import AdminProfileUpdate, MembershipUpdate, MiniPasswordUpdate, MiniProfileUpdate
from app.security import hash_password, verify_password


class _RedactWeChatURL(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple("https://api.weixin.qq.com/sns/jscode2session?[redacted]"
                                if "api.weixin.qq.com/sns/jscode2session" in str(arg) else arg for arg in record.args)
        return True


logging.getLogger("httpx").addFilter(_RedactWeChatURL())

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MiniUser:
    id: str
    username: str
    membership: str
    vip_expires_at: int | None
    avatar: str = ""
    has_password: bool = False

    @property
    def is_vip(self):
        return self.membership == "vip" and (self.vip_expires_at is None or self.vip_expires_at > time.time())

    def public(self):
        return {"id": self.id, "username": self.username, "avatar": self.avatar,
                "has_password": self.has_password, "membership": self.membership,
                "is_vip": self.is_vip, "vip_expires_at": self.vip_expires_at,
                "membership_status": "active" if self.is_vip else "expired" if self.membership == "vip" else "regular"}


def _row_user(row) -> MiniUser:
    return MiniUser(row["id"], row["username"], row["membership"], row["vip_expires_at"],
                    row["avatar"] or "", bool(row["password_hash"]))


def digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _error(message="登录已过期，请重新登录", status=401, code=""):
    raise HTTPException(status, detail={"error": message, **({"code": code} if code else {})})


def _user(conn, user_id):
    row = conn.execute("SELECT * FROM mini_users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        _error()
    if not row["is_active"]:
        _error("账号已被禁用，请联系管理员", 403, "account_disabled")
    return _row_user(row)


def get_user(user_id):
    with db() as conn:
        return _user(conn, user_id)


def _session(conn, user_id):
    user = _user(conn, user_id)
    token, now = "lc_reader_" + secrets.token_urlsafe(32), int(time.time())
    expires = now + get_settings().mini_session_days * 86400
    conn.execute("DELETE FROM mini_user_sessions WHERE expires_at <= ?", (now,))
    conn.execute("INSERT INTO mini_user_sessions(token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                 (digest(token), user_id, now, expires))
    conn.execute("DELETE FROM mini_user_sessions WHERE token_hash IN (SELECT token_hash FROM mini_user_sessions "
                 "WHERE user_id = ? AND token_hash <> ? ORDER BY created_at DESC, token_hash DESC LIMIT 100000 OFFSET 9)",
                 (user_id, digest(token)))
    return {"status": "authenticated", "token": token, "expires_at": expires, "user": user.public()}


def resolve_session(token: str) -> MiniUser:
    if not token.startswith("lc_reader_") or len(token) > 100:
        _error()
    with db() as conn:
        row = conn.execute("SELECT user_id, expires_at FROM mini_user_sessions WHERE token_hash = ?", (digest(token),)).fetchone()
        if not row or row["expires_at"] <= time.time():
            _error()
        return _user(conn, row["user_id"])


def logout(token: str):
    with db() as conn:
        conn.execute("DELETE FROM mini_user_sessions WHERE token_hash = ?", (digest(token),))


def register(username: str, password: str, *, admin=False):
    if not admin and not get_settings().mini_registration_enabled:
        _error("小程序注册暂未开放，请联系管理员", 403)
    password_hash = hash_password(password)
    now, user_id = int(time.time()), uuid.uuid4().hex
    with db(serialized=True) as conn:
        if conn.execute("SELECT id FROM mini_users WHERE username = ?", (username,)).fetchone():
            _error("小程序用户名已被占用", 409)
        conn.execute("INSERT INTO mini_users(id, username, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                     (user_id, username, password_hash, now, now))
        return _session(conn, user_id)


def login_password(username: str, password: str):
    with db() as conn:
        row = conn.execute("SELECT id, password_hash FROM mini_users WHERE username = ?", (username,)).fetchone()
    if not row or not row["password_hash"] or not verify_password(password, row["password_hash"]):
        _error("小程序用户名或密码错误")
    with db(serialized=True) as conn:
        return _session(conn, row["id"])


async def exchange_code(code: str) -> str:
    settings = get_settings()
    if not settings.wechat_app_id or not settings.wechat_app_secret:
        _error("微信登录尚未配置，请联系管理员", 503)
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.get("https://api.weixin.qq.com/sns/jscode2session", params={
                "appid": settings.wechat_app_id, "secret": settings.wechat_app_secret,
                "js_code": code, "grant_type": "authorization_code",
            })
            response.raise_for_status()
            value = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, detail={"error": "微信登录服务暂不可用，请稍后重试"}) from exc
    if not isinstance(value, dict) or value.get("errcode") or not isinstance(value.get("openid"), str) or not 1 <= len(value["openid"]) <= 128:
        _error("微信登录凭证无效，请重新登录")
    return digest(settings.wechat_app_id + ":" + value["openid"])


_NICKNAME_QUALITIES = (
    "认真", "勤奋", "好奇", "专注", "机灵", "勇敢", "踏实", "细心",
    "向阳", "静心", "元气", "乐学", "爱读书", "爱思考",
)
_NICKNAME_SPIRITS = (
    "小海豚", "小松鼠", "小狐狸", "小鹿", "小熊猫", "小企鹅",
    "小刺猬", "小考拉", "小猫头鹰", "小海獭", "小羊驼", "小袋鼠",
)


def _default_username(conn) -> str:
    """Human-friendly default nickname for a brand-new consumer account.

    Callers hold the cross-process transaction lock of ``db(serialized=True)``
    (pg_advisory_xact_lock on PostgreSQL, BEGIN IMMEDIATE on SQLite), so the
    availability check and the following INSERT cannot interleave with another
    worker picking the same nickname.
    """
    for _ in range(20):
        nickname = "%s的%s%d" % (secrets.choice(_NICKNAME_QUALITIES), secrets.choice(_NICKNAME_SPIRITS),
                                 secrets.randbelow(9000) + 1000)
        if not conn.execute("SELECT 1 FROM mini_users WHERE username = ?", (nickname,)).fetchone():
            return nickname
    return "小学员" + secrets.token_hex(4)


def login_public_identity(identity: str):
    with db(serialized=True) as conn:
        account = conn.execute("SELECT id FROM mini_users WHERE wechat_identity = ?", (identity,)).fetchone()
        if account:
            return _session(conn, account["id"])
        if not get_settings().mini_registration_enabled:
            _error("小程序注册暂未开放，请联系管理员", 403)
        user_id, now = uuid.uuid4().hex, int(time.time())
        conn.execute("INSERT INTO mini_users(id, username, wechat_identity, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                     (user_id, _default_username(conn), identity, now, now))
        return _session(conn, user_id)


def update_profile(user_id: str, body: MiniProfileUpdate):
    """用户自助改昵称/头像：只落传上来的字段。

    Callers hold ``db(serialized=True)``，所以昵称查重与随后的 UPDATE 不会被
    另一个 worker 插进来抢同一个昵称（UNIQUE 约束是最后一道防线）。
    """
    with db(serialized=True) as conn:
        row = conn.execute("SELECT * FROM mini_users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            _error()
        if not row["is_active"]:
            _error("账号已被禁用，请联系管理员", 403, "account_disabled")
        fields, args = [], []
        if body.username is not None and body.username != row["username"]:
            if conn.execute("SELECT id FROM mini_users WHERE username = ? AND id <> ?",
                            (body.username, user_id)).fetchone():
                _error("这个昵称已经有人在用了，换一个试试", 409, "nickname_taken")
            fields.append("username = ?")
            args.append(body.username)
        if body.avatar is not None and body.avatar != (row["avatar"] or ""):
            fields.append("avatar = ?")
            args.append(body.avatar)
        if fields:
            now = int(time.time())
            conn.execute("UPDATE mini_users SET " + ", ".join(fields) + ", revision = revision + 1, updated_at = ? "
                         "WHERE id = ?", [*args, now, user_id])
        return _user(conn, user_id).public()


def update_password(user_id: str, body: MiniPasswordUpdate, current_token: str = ""):
    """改密码；微信注册的账号还没有密码时是「首次设置密码」。

    改完吊销该账号的其它会话（当前会话保留），这样密码泄露后改密能立刻把
    别处的登录踢下线，而用户自己不用重新登录。
    """
    with db(serialized=True) as conn:
        row = conn.execute("SELECT * FROM mini_users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            _error()
        if not row["is_active"]:
            _error("账号已被禁用，请联系管理员", 403, "account_disabled")
        if row["password_hash"]:
            if not verify_password(body.current_password, row["password_hash"]):
                _error("当前密码不正确", 400, "password_mismatch")
            if verify_password(body.new_password, row["password_hash"]):
                _error("新密码不能和当前密码相同", 400, "password_reused")
        elif body.current_password:
            _error("当前密码不正确", 400, "password_mismatch")
        conn.execute("UPDATE mini_users SET password_hash = ?, revision = revision + 1, updated_at = ? WHERE id = ?",
                     (hash_password(body.new_password), int(time.time()), user_id))
        if current_token:
            conn.execute("DELETE FROM mini_user_sessions WHERE user_id = ? AND token_hash <> ?",
                         (user_id, digest(current_token)))
        else:
            conn.execute("DELETE FROM mini_user_sessions WHERE user_id = ?", (user_id,))
        return _user(conn, user_id).public()


def _admin_item(row):
    user = _row_user(row)
    return {**user.public(), "is_active": bool(row["is_active"]), "revision": row["revision"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "login_method": "wechat" if row["wechat_identity"] else "password"}


def _record_event(conn, admin_id, user_id, before, after):
    """把管理员对小程序账号的一次改动记进审计表（存改动前后的完整快照）。

    表名沿用 ``mini_membership_events``（历史原因），实际承担的是「后台对小程序
    账号的操作留痕」——会员、状态、资料、密码重置都走这里。
    """
    conn.execute("INSERT INTO mini_membership_events(id, user_id, admin_id, before_json, after_json, created_at) "
                 "VALUES (?, ?, ?, ?, ?, ?)",
                 (uuid.uuid4().hex, user_id, admin_id, json.dumps(before), json.dumps(after), int(time.time())))


def list_users(q="", membership="", limit=20, offset=0):
    clauses, args = [], []
    if q.strip():
        clauses.append("LOWER(username) LIKE ? ESCAPE '\\'")
        args.append("%" + q.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    active_vip = "membership = 'vip' AND (vip_expires_at IS NULL OR vip_expires_at > ?)"
    if membership == "vip":
        clauses.append("(" + active_vip + ")")
        args.append(int(time.time()))
    elif membership == "regular":
        clauses.append("NOT (" + active_vip + ")")
        args.append(int(time.time()))
    where = " AND ".join(clauses) or "1 = 1"
    with db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM mini_users WHERE {where}", args).fetchone()[0]
        rows = conn.execute(f"SELECT * FROM mini_users WHERE {where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                            [*args, limit, offset]).fetchall()
    return {"items": [_admin_item(row) for row in rows], "total": total, "has_more": offset + len(rows) < total}


def admin_user(user_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM mini_users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            _error("小程序用户不存在", 404)
        return _admin_item(row)


def update_membership(admin_id, user_id, body: MembershipUpdate):
    with db(serialized=True) as conn:
        row = conn.execute("SELECT * FROM mini_users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            _error("小程序用户不存在", 404)
        if row["revision"] != body.revision:
            _error("用户信息已更新，请刷新后重试", 409)
        now = int(time.time())
        conn.execute("UPDATE mini_users SET membership = ?, vip_expires_at = ?, is_active = ?, revision = revision + 1, "
                     "updated_at = ? WHERE id = ?", (body.membership, body.vip_expires_at, int(body.is_active), now, user_id))
        if not body.is_active:
            conn.execute("DELETE FROM mini_user_sessions WHERE user_id = ?", (user_id,))
        _record_event(conn, admin_id, user_id, _admin_item(row), _admin_item(
            conn.execute("SELECT * FROM mini_users WHERE id = ?", (user_id,)).fetchone()))
    return admin_user(user_id)


def update_admin_profile(admin_id, user_id, body: AdminProfileUpdate):
    """管理员改小程序用户的昵称 / 头像 / 密码。

    只落传上来的字段；带 ``revision`` 乐观锁，避免两个管理员互相覆盖。
    重置密码会吊销该账号的全部会话——旧密码对应的登录态立刻失效。
    """
    with db(serialized=True) as conn:
        row = conn.execute("SELECT * FROM mini_users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            _error("小程序用户不存在", 404)
        if row["revision"] != body.revision:
            _error("用户信息已更新，请刷新后重试", 409)
        fields, args = [], []
        if body.username is not None and body.username != row["username"]:
            if conn.execute("SELECT id FROM mini_users WHERE username = ? AND id <> ?",
                            (body.username, user_id)).fetchone():
                _error("这个昵称已经有人在用了", 409, "nickname_taken")
            fields.append("username = ?")
            args.append(body.username)
        if body.avatar is not None and body.avatar != (row["avatar"] or ""):
            fields.append("avatar = ?")
            args.append(body.avatar)
        reset_password = body.new_password is not None
        if reset_password:
            fields.append("password_hash = ?")
            args.append(hash_password(body.new_password))
        if not fields:
            return admin_user(user_id)
        conn.execute("UPDATE mini_users SET " + ", ".join(fields) + ", revision = revision + 1, updated_at = ? WHERE id = ?",
                     [*args, int(time.time()), user_id])
        if reset_password:
            conn.execute("DELETE FROM mini_user_sessions WHERE user_id = ?", (user_id,))
        _record_event(conn, admin_id, user_id, _admin_item(row), _admin_item(
            conn.execute("SELECT * FROM mini_users WHERE id = ?", (user_id,)).fetchone()))
    logger.info("管理员 id=%s 更新了小程序账号 id=%s: 昵称=%s 头像=%s 重置密码=%s", admin_id, user_id,
                body.username or "-", body.avatar if body.avatar is not None else "-", reset_password)
    return admin_user(user_id)


#: 删除小程序账号时要一并清理的从表。两张库都声明了 ON DELETE CASCADE（SQLite 连接
#: 也开了 PRAGMA foreign_keys），这里显式删除是为了两库行为完全一致，同时能告诉
#: 管理员究竟清掉了多少条关联数据。
_OWNED_TABLES = ("mini_user_sessions", "mini_catalog_favorites", "mini_catalog_downloads", "mini_membership_events")


def delete_user(admin_id, user_id):
    """彻底删除小程序账号（不可恢复），连带会话、收藏、下载记录与操作留痕。"""
    with db(serialized=True) as conn:
        row = conn.execute("SELECT * FROM mini_users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            _error("小程序用户不存在", 404)
        removed = {table: conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (user_id,)).fetchone()[0]
                   for table in _OWNED_TABLES}
        for table in _OWNED_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM mini_users WHERE id = ?", (user_id,))
    logger.info("管理员 id=%s 删除了小程序账号「%s」(id=%s)，清理 %s", admin_id, row["username"], user_id, removed)
    return {"status": "deleted", "username": row["username"], "removed": removed}
