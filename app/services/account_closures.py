"""Reviewable account closure with explicit consent and financial settlement checks."""

import time
import uuid

from app.db import db
from app.services import mini_auth, mini_orders
from app.services.mini_errors import fail
from app.services.mini_messages import notify


def current(user_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM mini_account_closures WHERE user_id = ?", (user_id,)).fetchone()
    return {"request": dict(row) if row else None}


def request(user_id, body):
    with db(serialized="accounts") as conn:
        mini_orders.ensure_deletable(conn, user_id)
        user = conn.execute("SELECT username FROM mini_users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            fail("账号不存在", 404)
        row = conn.execute("SELECT * FROM mini_account_closures WHERE user_id = ?", (user_id,)).fetchone()
        if row and row["status"] == "pending":
            return {"request": dict(row)}
        now = int(time.time())
        if row:
            conn.execute("UPDATE mini_account_closures SET status = 'pending', reason = ?, reply = '', revision = revision + 1, updated_at = ?, admin_id = NULL WHERE id = ?", (body.reason, now, row["id"]))
        else:
            conn.execute("INSERT INTO mini_account_closures(id, user_id, account_name, reason, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)", (uuid.uuid4().hex, user_id, user[0], body.reason, now, now))
        return {"request": dict(conn.execute("SELECT * FROM mini_account_closures WHERE user_id = ?", (user_id,)).fetchone())}


def cancel(user_id, revision):
    with db(serialized="accounts") as conn:
        row = conn.execute("SELECT * FROM mini_account_closures WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            fail("注销申请不存在", 404)
        if row["revision"] != revision or row["status"] != "pending":
            fail("申请状态已更新，请刷新后重试")
        conn.execute("UPDATE mini_account_closures SET status = 'cancelled', revision = revision + 1, updated_at = ? WHERE id = ?", (int(time.time()), row["id"]))
    return current(user_id)


def listing(status="", limit=20, offset=0):
    where, args = ("WHERE status = ?", [status]) if status else ("", [])
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM mini_account_closures " + where, args).fetchone()[0]
        items = [dict(row) for row in conn.execute("SELECT * FROM mini_account_closures " + where + " ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?", [*args, limit, offset])]
    return {"items": items, "total": total, "has_more": offset + len(items) < total}


def review(admin_id, identifier, body):
    with db(serialized=("content", "accounts")) as conn:
        row = conn.execute("SELECT * FROM mini_account_closures WHERE id = ?", (identifier,)).fetchone()
        if not row:
            fail("注销申请不存在", 404)
        if row["revision"] != body.revision or row["status"] != "pending" or not row["user_id"]:
            fail("申请已更新，请刷新后重试")
        if body.action == "approve":
            if not body.confirm_deletion:
                fail("请明确确认注销账号及清理个人数据", 422)
            mini_orders.ensure_deletable(conn, row["user_id"])
            conn.execute("UPDATE mini_account_closures SET status = 'completed', account_name = '已注销用户', reason = '', reply = ?, admin_id = ?, revision = revision + 1, updated_at = ? WHERE id = ?",
                         (body.reply, admin_id, int(time.time()), identifier))
            mini_auth.delete_user_data(conn, row["user_id"])
        else:
            conn.execute("UPDATE mini_account_closures SET status = 'rejected', reply = ?, admin_id = ?, revision = revision + 1, updated_at = ? WHERE id = ?", (body.reply, admin_id, int(time.time()), identifier))
            notify(conn, row["user_id"], f"closure:{identifier}:{body.revision + 1}", "closure", "注销申请处理结果", body.reply, "closure", identifier)
        return dict(conn.execute("SELECT * FROM mini_account_closures WHERE id = ?", (identifier,)).fetchone())
