"""Resource requests remain private; operators see aggregate demand and resolve each request."""

import hashlib
import time
import uuid

from app.db import db
from app.services import public_catalog as catalog
from app.services.mini_errors import fail
from app.services.mini_messages import notify


def create(user_id, body):
    now = int(time.time())
    fingerprint = hashlib.sha256("\n".join([body.title.casefold(), body.grade.casefold(), body.subject.casefold()]).encode()).hexdigest()
    with db(serialized=True) as conn:
        existing = conn.execute("SELECT * FROM mini_content_requests WHERE user_id = ? AND fingerprint = ? AND status IN ('pending', 'planned')", (user_id, fingerprint)).fetchone()
        if existing:
            return dict(existing)
        if conn.execute("SELECT COUNT(*) FROM mini_content_requests WHERE user_id = ? AND created_at > ?", (user_id, now - 86400)).fetchone()[0] >= 5:
            fail("每天最多提交 5 条资料需求，请先查看已有需求的处理进度", 429)
        identifier = uuid.uuid4().hex
        conn.execute("INSERT INTO mini_content_requests(id, user_id, fingerprint, title, grade, subject, details, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (identifier, user_id, fingerprint, body.title, body.grade, body.subject, body.details, now, now))
        return dict(conn.execute("SELECT * FROM mini_content_requests WHERE id = ?", (identifier,)).fetchone())


def listing(user_id=None, status="", fingerprint="", limit=20, offset=0, identifier=""):
    clauses, args = [], []
    for field, value in (("r.user_id", user_id), ("r.status", status), ("r.fingerprint", fingerprint), ("r.id", identifier)):
        if value:
            clauses.append(field + " = ?")
            args.append(value)
    where = " AND ".join(clauses) or "1=1"
    with db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM mini_content_requests r WHERE {where}", args).fetchone()[0]
        rows = conn.execute(f"SELECT r.*, u.nickname, u.username, c.title AS paper_title, c.status AS paper_status, a.file_status AS paper_file_status, ({catalog.VISIBLE}) AS paper_visible FROM mini_content_requests r "
                            "JOIN mini_users u ON u.id = r.user_id LEFT JOIN catalog_papers c ON c.id = r.catalog_id LEFT JOIN paper_archives a ON a.id = c.paper_id "
                            f"WHERE {where} ORDER BY r.updated_at DESC, r.id DESC LIMIT ? OFFSET ?", [*args, limit, offset]).fetchall()
        items = [dict(row) for row in rows]
        if user_id:
            for item in items:
                for key in ("user_id", "username", "nickname", "fingerprint"):
                    item.pop(key, None)
                if not item.pop("paper_visible"):
                    item["catalog_id"] = None
                    item["paper_title"] = None
        totals = [] if user_id else [dict(row) for row in conn.execute(
            "SELECT fingerprint, MIN(title) AS title, grade, subject, COUNT(*) AS requests, COUNT(DISTINCT user_id) AS users "
            "FROM mini_content_requests WHERE status IN ('pending', 'planned') GROUP BY fingerprint, grade, subject ORDER BY users DESC, fingerprint LIMIT 30")]
    return {"items": items, "total": total, "has_more": offset + len(items) < total, "demand": totals}


def detail(user_id, identifier):
    result = listing(user_id, identifier=identifier, limit=1)
    if not result["items"]:
        fail("资料需求不存在", 404)
    return result["items"][0]


def resolve(identifier, body):
    now = int(time.time())
    with db(serialized=True) as conn:
        row = conn.execute("SELECT * FROM mini_content_requests WHERE id = ?", (identifier,)).fetchone()
        if not row:
            fail("资料需求不存在", 404)
        if row["revision"] != body.revision:
            fail("需求已被更新，请刷新后重试")
        target = body.catalog_id if body.status == "fulfilled" else None
        if target:
            catalog._visible(conn, target)
        conn.execute("UPDATE mini_content_requests SET status = ?, reply = ?, catalog_id = ?, revision = revision + 1, updated_at = ? WHERE id = ?",
                     (body.status, body.reply, target, now, identifier))
        if body.status != row["status"] or body.reply != row["reply"] or target != row["catalog_id"]:
            labels = {"pending": "已受理", "planned": "已安排", "fulfilled": "资料已补齐", "closed": "处理结果已更新"}
            notify(conn, row["user_id"], f"request:{identifier}:{body.revision + 1}", "request", labels[body.status],
                   body.reply or f"你提交的“{row['title']}”已有新的处理进度。", "request", identifier)
        return dict(conn.execute("SELECT * FROM mini_content_requests WHERE id = ?", (identifier,)).fetchone())
