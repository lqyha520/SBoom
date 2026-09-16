"""Account-scoped feedback, organization and measured usage."""

import json
import time
import uuid
from datetime import datetime, timezone, timedelta

from app.db import db
from app.models.experience import SupportSettings
from app.services import mini_auth, public_catalog as catalog
from app.services.mini_errors import fail
from app.services.mini_messages import notify


def _feedback(row, admin=False):
    item = dict(row)
    if not admin:
        item.pop("internal_note", None)
        item.pop("admin_id", None)
    return item


def create_feedback(user_id, body):
    now, identifier = int(time.time()), uuid.uuid4().hex
    with db(serialized=True) as conn:
        # A database limit is shared by all workers, including when an IP changes.
        count = conn.execute("SELECT COUNT(*) FROM mini_feedback WHERE user_id = ? AND created_at > ?",
                             (user_id, now - 3600)).fetchone()[0]
        if count >= 10:
            fail("反馈提交较频繁，请稍后再试", 429)
        paper = catalog._visible(conn, body.catalog_id) if body.catalog_id else None
        if body.kind in ("correction", "download") and not paper:
            fail("请从对应资料的详情页提交此类反馈", 422)
        conn.execute("INSERT INTO mini_feedback(id, user_id, catalog_id, paper_title, kind, body, created_at, updated_at) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (identifier, user_id, body.catalog_id, paper["title"] if paper else "", body.kind, body.body, now, now))
        return _feedback(conn.execute("SELECT * FROM mini_feedback WHERE id = ?", (identifier,)).fetchone())


def list_feedback(user_id=None, status="", limit=20, offset=0):
    clauses, args = [], []
    if user_id is not None:
        clauses.append("f.user_id = ?")
        args.append(user_id)
    if status:
        clauses.append("f.status = ?")
        args.append(status)
    where = " AND ".join(clauses) or "1=1"
    with db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM mini_feedback f WHERE {where}", args).fetchone()[0]
        rows = conn.execute("SELECT f.*, u.username, u.nickname FROM mini_feedback f JOIN mini_users u ON u.id = f.user_id "
                            f"WHERE {where} ORDER BY f.updated_at DESC, f.id DESC LIMIT ? OFFSET ?", [*args, limit, offset]).fetchall()
    return {"items": [_feedback(row, user_id is None) for row in rows], "total": total, "has_more": offset + len(rows) < total}


def update_feedback(admin_id, identifier, body):
    with db(serialized=True) as conn:
        row = conn.execute("SELECT * FROM mini_feedback WHERE id = ?", (identifier,)).fetchone()
        if not row:
            fail("反馈不存在", 404)
        if row["revision"] != body.revision:
            fail("反馈已经更新，请刷新后重试")
        conn.execute("UPDATE mini_feedback SET status = ?, reply = ?, internal_note = ?, admin_id = ?, "
                     "revision = revision + 1, updated_at = ? WHERE id = ?",
                     (body.status, body.reply, body.internal_note, admin_id, int(time.time()), identifier))
        if body.reply and (body.reply != row["reply"] or body.status != row["status"]):
            notify(conn, row["user_id"], f"feedback:{identifier}:{body.revision + 1}", "feedback", "你的反馈有新回复",
                   body.reply, "feedback", identifier)
        return _feedback(conn.execute("SELECT * FROM mini_feedback WHERE id = ?", (identifier,)).fetchone(), True)


def feedback_detail(user_id, identifier):
    with db() as conn:
        row = conn.execute("SELECT * FROM mini_feedback WHERE id = ? AND user_id = ?", (identifier, user_id)).fetchone()
    if not row:
        fail("反馈记录不存在", 404)
    return _feedback(row)


def support():
    with db() as conn:
        row = conn.execute("SELECT value FROM app_config WHERE key = 'mini_support'").fetchone()
    return json.loads(row[0]) if row else SupportSettings().model_dump()


def save_support(body):
    with db(serialized=True) as conn:
        row = conn.execute("SELECT value FROM app_config WHERE key = 'mini_support'").fetchone()
        previous = json.loads(row[0]) if row else {"revision": 0}
        if previous["revision"] != body.revision:
            fail("联系信息已更新，请刷新后重试")
        value = {**body.model_dump(), "revision": body.revision + 1}
        conn.execute("INSERT INTO app_config(key, value) VALUES ('mini_support', ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (json.dumps(value, ensure_ascii=False),))
    return value


def groups(user_id):
    with db() as conn:
        rows = conn.execute("SELECT g.*, (SELECT COUNT(*) FROM mini_favorite_group_items x "
                            "JOIN catalog_papers c ON c.id = x.catalog_id JOIN paper_archives a ON a.id = c.paper_id "
                            f"WHERE x.group_id = g.id AND {catalog.VISIBLE}) AS paper_count "
                            "FROM mini_favorite_groups g WHERE g.user_id = ? ORDER BY g.created_at, g.id", (user_id,)).fetchall()
    return {"items": [dict(row) for row in rows]}


def save_group(user_id, body, identifier=None):
    with db(serialized=True) as conn:
        existing = conn.execute("SELECT id FROM mini_favorite_groups WHERE user_id = ? AND name = ?", (user_id, body.name)).fetchone()
        if existing and existing[0] != identifier:
            fail("已有同名收藏分组")
        if identifier:
            row = conn.execute("SELECT revision FROM mini_favorite_groups WHERE id = ? AND user_id = ?", (identifier, user_id)).fetchone()
            if not row:
                fail("收藏分组不存在", 404)
            if row[0] != body.revision:
                fail("分组已更新，请刷新")
            conn.execute("UPDATE mini_favorite_groups SET name = ?, revision = revision + 1 WHERE id = ?", (body.name, identifier))
        else:
            if conn.execute("SELECT COUNT(*) FROM mini_favorite_groups WHERE user_id = ?", (user_id,)).fetchone()[0] >= 50:
                fail("最多可创建 50 个收藏分组", 422)
            identifier = uuid.uuid4().hex
            conn.execute("INSERT INTO mini_favorite_groups(id, user_id, name, created_at) VALUES (?, ?, ?, ?)",
                         (identifier, user_id, body.name, int(time.time())))
        return dict(conn.execute("SELECT * FROM mini_favorite_groups WHERE id = ?", (identifier,)).fetchone())


def delete_group(user_id, identifier, revision):
    with db(serialized=True) as conn:
        row = conn.execute("SELECT revision FROM mini_favorite_groups WHERE id = ? AND user_id = ?", (identifier, user_id)).fetchone()
        if not row:
            fail("收藏分组不存在", 404)
        if row[0] != revision:
            fail("分组已更新，请刷新")
        conn.execute("DELETE FROM mini_favorite_groups WHERE id = ?", (identifier,))


def assign_group(user_id, catalog_id, group_id):
    with db(serialized=True) as conn:
        catalog._visible(conn, catalog_id)
        if not conn.execute("SELECT 1 FROM mini_catalog_favorites WHERE user_id = ? AND catalog_id = ?", (user_id, catalog_id)).fetchone():
            fail("请先收藏这份资料", 422)
        if group_id and not conn.execute("SELECT 1 FROM mini_favorite_groups WHERE id = ? AND user_id = ?", (group_id, user_id)).fetchone():
            fail("收藏分组不存在", 404)
        conn.execute("DELETE FROM mini_favorite_group_items WHERE user_id = ? AND catalog_id = ?", (user_id, catalog_id))
        if group_id:
            conn.execute("INSERT INTO mini_favorite_group_items(user_id, catalog_id, group_id) VALUES (?, ?, ?)", (user_id, catalog_id, group_id))
    return {"group_id": group_id}


def record_view(user_id, catalog_id):
    with db(serialized=True) as conn:
        catalog._visible(conn, catalog_id)
        conn.execute("INSERT INTO mini_recent_views(user_id, catalog_id, viewed_at) VALUES (?, ?, ?) "
                     "ON CONFLICT(user_id, catalog_id) DO UPDATE SET viewed_at = excluded.viewed_at", (user_id, catalog_id, int(time.time())))
        conn.execute("DELETE FROM mini_recent_views WHERE user_id = ? AND catalog_id IN "
                     "(SELECT catalog_id FROM mini_recent_views WHERE user_id = ? ORDER BY viewed_at DESC, catalog_id DESC LIMIT 100000 OFFSET 100)",
                     (user_id, user_id))


def clear_history(user_id):
    with db() as conn:
        conn.execute("DELETE FROM mini_recent_views WHERE user_id = ?", (user_id,))


def record_event(user_id, kind, identifier=None, catalog_id=None, detail=""):
    now = int(time.time())
    # One active marker per account/day. Business event identifiers deduplicate network retries.
    event_id = f"active-{user_id}-{(now + 28800) // 86400}" if kind == "active" else f"{user_id}-{identifier or uuid.uuid4().hex}"
    with db(serialized=True) as conn:
        if catalog_id:
            catalog._visible(conn, catalog_id)
        if kind.startswith("download_"):
            if not catalog_id or not conn.execute("SELECT 1 FROM mini_catalog_downloads WHERE user_id = ? AND catalog_id = ? AND requested_at > ?",
                                                 (user_id, catalog_id, now - 3600)).fetchone():
                fail("未找到对应下载请求", 422)
        conn.execute("DELETE FROM mini_usage_events WHERE created_at < ?", (now - 60 * 86400,))
        conn.execute("INSERT INTO mini_usage_events(id, user_id, kind, detail, catalog_id, created_at) VALUES (?, ?, ?, ?, ?, ?) "
                     "ON CONFLICT(id) DO NOTHING", (event_id, user_id, kind, detail[:120], catalog_id, now))


def usage_analytics():
    now = int(time.time())
    zone = timezone(timedelta(hours=8))
    today = datetime.fromtimestamp(now, zone).replace(hour=0, minute=0, second=0)
    start = int((today - timedelta(days=29)).timestamp())
    with db() as conn:
        rows = conn.execute("SELECT user_id, kind, created_at FROM mini_usage_events WHERE created_at >= ?", (start,)).fetchall()
        misses = [dict(row) for row in conn.execute("SELECT detail AS query, COUNT(*) AS total FROM mini_usage_events "
                    "WHERE kind = 'search_miss' AND created_at >= ? GROUP BY detail ORDER BY total DESC, detail LIMIT 20", (start,))]
        failures = [dict(row) for row in conn.execute("SELECT e.catalog_id, c.title, COUNT(*) AS total FROM mini_usage_events e "
                    "LEFT JOIN catalog_papers c ON c.id = e.catalog_id WHERE e.kind = 'download_failed' AND e.created_at >= ? "
                    "GROUP BY e.catalog_id, c.title ORDER BY total DESC LIMIT 20", (start,))]
    days = {}
    week_users, month_users = set(), set()
    for row in rows:
        day = datetime.fromtimestamp(row["created_at"], zone).strftime("%Y-%m-%d")
        point = days.setdefault(day, {"users": set(), "download_ok": 0, "download_failed": 0, "search_miss": 0})
        point["users"].add(row["user_id"])
        month_users.add(row["user_id"])
        if row["created_at"] >= int((today - timedelta(days=6)).timestamp()):
            week_users.add(row["user_id"])
        if row["kind"] in ("download_ok", "download_failed", "search_miss"):
            point[row["kind"]] += 1
    timeline = []
    for offset in range(29, -1, -1):
        key = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        point = days.get(key, {"users": set(), "download_ok": 0, "download_failed": 0, "search_miss": 0})
        timeline.append({"date": key, "active_users": len(point["users"]), **{k: point[k] for k in ("download_ok", "download_failed", "search_miss")}})
    return {"daily_active": timeline[-1]["active_users"], "weekly_active": len(week_users), "monthly_active": len(month_users),
            "timeline": timeline, "search_misses": misses, "download_failures": failures,
            "timezone": "Asia/Shanghai", "retention_days": 60}


def renew_membership(admin_id, user_id, body):
    with db(serialized=True) as conn:
        row = conn.execute("SELECT * FROM mini_users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            fail("小程序用户不存在", 404)
        if row["revision"] != body.revision:
            fail("用户信息已变化，请刷新后续期")
        if row["membership"] == "vip" and row["vip_expires_at"] is None:
            fail("当前为长期会员，无需续期")
        from app.services.membership_ledger import append
        append(conn, row, body.days)
        after = mini_auth._admin_item(conn.execute("SELECT * FROM mini_users WHERE id = ?", (user_id,)).fetchone())
        mini_auth._record_event(conn, admin_id, user_id, mini_auth._admin_item(row), {**after, "renewal_days": body.days, "note": body.note})
    return after


def membership_events(user_id, limit=20, offset=0):
    mini_auth.admin_user(user_id)
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM mini_membership_events WHERE user_id = ?", (user_id,)).fetchone()[0]
        rows = conn.execute("SELECT e.*, u.username AS admin_name FROM mini_membership_events e LEFT JOIN users u ON u.id = e.admin_id "
                            "WHERE e.user_id = ? ORDER BY e.created_at DESC, e.id DESC LIMIT ? OFFSET ?", (user_id, limit, offset)).fetchall()
    return {"items": [{"id": row["id"], "admin_name": row["admin_name"], "created_at": row["created_at"],
                       "before": json.loads(row["before_json"]), "after": json.loads(row["after_json"])} for row in rows],
            "total": total, "has_more": offset + len(rows) < total}
