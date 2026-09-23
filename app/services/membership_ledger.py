"""Append-only membership grants with explicit override epochs and refund reflow."""

import time
import uuid

from app.services.mini_errors import fail


def append(conn, user, days, order_id=None):
    now = int(time.time())
    if user["membership"] == "vip" and user["vip_expires_at"] is None:
        return 0
    start = max(now, user["vip_expires_at"] or 0) if user["membership"] == "vip" else now
    end = start + days * 86400
    if end > 253402300799:
        fail("会员到期日期超出支持范围", 422)
    conn.execute("INSERT INTO mini_membership_grants(id, user_id, order_id, epoch, starts_at, ends_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (uuid.uuid4().hex, user["id"], order_id, user["entitlement_epoch"], start, end, now))
    conn.execute("UPDATE mini_users SET membership = 'vip', vip_expires_at = ?, revision = revision + 1, updated_at = ? WHERE id = ?", (end, now, user["id"]))
    return end


def revoke(conn, order_id):
    grant = conn.execute("SELECT * FROM mini_membership_grants WHERE order_id = ?", (order_id,)).fetchone()
    if not grant or grant["revoked_at"] is not None:
        return 0
    now = int(time.time())
    conn.execute("UPDATE mini_membership_grants SET revoked_at = ? WHERE id = ?", (now, grant["id"]))
    user = conn.execute("SELECT * FROM mini_users WHERE id = ?", (grant["user_id"],)).fetchone()
    if not user or user["entitlement_epoch"] != grant["epoch"] or user["membership"] != "vip" or user["vip_expires_at"] is None:
        return 0
    unused = max(0, grant["ends_at"] - max(now, grant["starts_at"]))
    unused = min(unused, max(0, user["vip_expires_at"] - now))
    if unused:
        # Later purchases/manual renewals move earlier, retaining their full unused duration.
        conn.execute("UPDATE mini_membership_grants SET starts_at = starts_at - ?, ends_at = ends_at - ? "
                     "WHERE user_id = ? AND epoch = ? AND revoked_at IS NULL AND starts_at >= ?",
                     (unused, unused, user["id"], grant["epoch"], grant["ends_at"]))
        conn.execute("UPDATE mini_users SET vip_expires_at = vip_expires_at - ?, revision = revision + 1, updated_at = ? WHERE id = ?", (unused, now, user["id"]))
    return unused
