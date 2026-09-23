"""Private inbox; notifications are committed with the operation they describe."""

import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.db import db

TARGETS = {"paper", "feedback", "membership", "request", "closure", "order", ""}


def notify(conn, user_id, event_key, kind, title, body, target_type="", target_id=""):
    if target_type not in TARGETS or len(target_id) > 64:
        raise ValueError("Invalid inbox destination")
    now = int(time.time())
    identifier = uuid.uuid4().hex
    conn.execute("INSERT INTO mini_notifications(id, user_id, event_key, kind, title, body, target_type, target_id, created_at) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(user_id, event_key) DO NOTHING",
                 (identifier, user_id, event_key, kind, title[:100], body[:1000], target_type, target_id, now))
    # Only new messages use an existing, explicitly requested subscription credit.
    if conn.execute("SELECT 1 FROM mini_notifications WHERE id = ?", (identifier,)).fetchone():
        if conn.execute("SELECT 1 FROM mini_notice_subscriptions WHERE user_id = ? AND credits > 0", (user_id,)).fetchone():
            conn.execute("INSERT INTO mini_notice_deliveries(notification_id, updated_at) VALUES (?, ?)", (identifier, now))
    conn.execute("DELETE FROM mini_notifications WHERE user_id = ? AND created_at < ?", (user_id, now - 180 * 86400))


def expiry_notice(conn, user_id):
    row = conn.execute("SELECT membership, vip_expires_at FROM mini_users WHERE id = ?", (user_id,)).fetchone()
    now = int(time.time())
    if not row or row["membership"] != "vip" or row["vip_expires_at"] is None or row["vip_expires_at"] > now + 7 * 86400:
        return
    expired = row["vip_expires_at"] <= now
    date = datetime.fromtimestamp(row["vip_expires_at"], timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    notify(conn, user_id, f"expiry:{row['vip_expires_at']}:{int(expired)}", "membership",
           "会员已到期" if expired else "会员即将到期", f"会员到期日为 {date}，可在会员服务查看或续期。", "membership")


def unread_count(conn, user_id) -> int:
    """未读数：走 idx_mini_notifications_unread(user_id, read_at) 索引，供 /mini/me 等高频接口复用。"""
    return int(conn.execute("SELECT COUNT(*) FROM mini_notifications WHERE user_id = ? AND read_at IS NULL", (user_id,)).fetchone()[0])


def inbox(user_id, unread=False, limit=20, offset=0):
    # 纯读路径不持 content/accounts 全局锁：expiry_notice→notify 的插入是
    # ON CONFLICT(user_id, event_key) DO NOTHING，并发重复调用也是幂等的。
    with db() as conn:
        expiry_notice(conn, user_id)
        unread_total = unread_count(conn, user_id)
        where = "user_id = ?" + (" AND read_at IS NULL" if unread else "")
        total = conn.execute(f"SELECT COUNT(*) FROM mini_notifications WHERE {where}", (user_id,)).fetchone()[0]
        items = [dict(row) for row in conn.execute(f"SELECT * FROM mini_notifications WHERE {where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?", (user_id, limit, offset))]
    for item in items:
        item.pop("user_id")
        item.pop("event_key")
    return {"items": items, "total": total, "unread": unread_total, "has_more": offset + len(items) < total}


def read(user_id, identifier=None):
    # 只更新本人消息的 read_at（行级 UPDATE，条件里带 user_id），不需要全局锁
    with db() as conn:
        if identifier and not conn.execute("SELECT 1 FROM mini_notifications WHERE id = ? AND user_id = ?", (identifier, user_id)).fetchone():
            raise HTTPException(404, detail={"error": "消息不存在"})
        query = "UPDATE mini_notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL"
        conn.execute(query + (" AND id = ?" if identifier else ""), (int(time.time()), user_id, identifier) if identifier else (int(time.time()), user_id))
        remaining = unread_count(conn, user_id)
    return {"unread": remaining}
