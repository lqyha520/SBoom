"""General maintenance, independent of optional payment integrations."""
import hashlib
import logging
import time
import uuid

from app.config import get_settings
from app.constants import MAINTENANCE_LOCK, UPLOAD_LEASE
from app.db import db
from app.services.file_retention import drain, enqueue, scan_orphans
from app.services.paper_storage import storage_for, thumbnail

logger = logging.getLogger(__name__)

def backfill_thumbnails(limit=5):
    # 一轮扫描结束后隔一天重新检查低于游标的新 UUID 或失败项，避免每分钟空转。
    with db() as conn:
        next_scan = conn.execute("SELECT value FROM app_config WHERE key = 'thumbnail_backfill_next'").fetchone()
        if next_scan and float(next_scan[0]) > time.time():
            return
    with db() as conn:
        cursor = conn.execute("SELECT value FROM app_config WHERE key = 'thumbnail_backfill_cursor'").fetchone()
        rows = conn.execute("SELECT s.*, a.user_id FROM paper_assets s JOIN paper_archives a ON a.id = s.paper_id WHERE a.id > ? AND s.kind = 'page' AND s.page_number = 1 AND a.file_status = 'ready' AND NOT EXISTS (SELECT 1 FROM paper_assets t WHERE t.paper_id = s.paper_id AND t.kind = 'thumbnail') ORDER BY a.id LIMIT ?", (cursor[0] if cursor else "", limit)).fetchall()
        conn.execute("INSERT INTO app_config(key, value) VALUES ('thumbnail_backfill_cursor', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (rows[-1]["paper_id"] if len(rows) == limit else "",))
    if len(rows) < limit:
        with db() as conn:
            conn.execute("INSERT INTO app_config(key, value) VALUES ('thumbnail_backfill_next', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (str(int(time.time()) + 86400),))
    for row in rows:
        try:
            _backfill_one(row)
        except Exception:
            from app.metrics import maintenance_failures
            maintenance_failures.inc()
            logger.warning("Thumbnail backfill deferred for archive %s", row["paper_id"])

def _backfill_one(row):
    raw = thumbnail(storage_for(row["storage"]).path(row["storage_key"]).read_bytes())
    key = f"{row['paper_id']}/{uuid.uuid4().hex}/thumbnail.jpg"
    # Recheck under the publication lock before committing a small derivative.
    with db(serialized=True) as conn:
        if not conn.execute("SELECT 1 FROM paper_assets WHERE id = ?", (row["id"],)).fetchone():
            return
        if conn.execute("SELECT 1 FROM paper_assets WHERE paper_id = ? AND kind = 'thumbnail'", (row["paper_id"],)).fetchone():
            return
        used = conn.execute("SELECT COALESCE(SUM(s.byte_size), 0) FROM paper_assets s JOIN paper_archives a ON a.id = s.paper_id WHERE a.user_id = ?", (row["user_id"],)).fetchone()[0]
        reserved = conn.execute("SELECT COALESCE(SUM(upload_reserved_bytes), 0) FROM paper_archives WHERE user_id = ? AND file_status = 'uploading' AND upload_started_at > ?", (row["user_id"], int(time.time()) - UPLOAD_LEASE)).fetchone()[0]
        if used + reserved + len(raw) > get_settings().archive_storage_mb * 1024 * 1024:
            return
        storage_for().put(key, raw, "image/jpeg")
        conn.execute("INSERT INTO paper_assets(id, paper_id, kind, page_number, storage, storage_key, mime_type, byte_size, sha256) VALUES (?, ?, 'thumbnail', 1, 'local', ?, 'image/jpeg', ?, ?)",
                     (uuid.uuid4().hex, row["paper_id"], key, len(raw), hashlib.sha256(raw).hexdigest()))

def tick():
    # Only one process does storage reconciliation. This is a separate lock domain.
    with db() as lease:
        if not lease.execute("SELECT pg_try_advisory_lock(?)", (MAINTENANCE_LOCK,)).fetchone()[0]:
            return
        lease.commit()  # 会话锁保留，耗时文件操作期间不维持空闲事务。
        try:
            now, settings = int(time.time()), get_settings()
            with db() as conn:
                conn.execute("DELETE FROM mini_usage_events WHERE id IN (SELECT id FROM mini_usage_events WHERE created_at < ? ORDER BY created_at LIMIT 500)", (now - 60 * 86400,))
                conn.execute("UPDATE generation_requests SET result_json = '' WHERE (user_id, request_id) IN (SELECT user_id, request_id FROM generation_requests WHERE result_json <> '' AND finished_at < ? ORDER BY finished_at LIMIT 100)", (now - settings.generation_result_days * 86400,))
                conn.execute("UPDATE generation_requests SET status = 'unknown', finished_at = ? WHERE (user_id, request_id) IN (SELECT user_id, request_id FROM generation_requests WHERE status = 'running' AND COALESCE(NULLIF(lease_expires_at, 0), created_at + 90) < ? ORDER BY created_at LIMIT 100)", (now, now))
                conn.execute("INSERT INTO generation_tombstones(user_id, request_id) SELECT user_id, request_id FROM generation_requests WHERE status <> 'running' AND finished_at < ? ORDER BY finished_at LIMIT 500 ON CONFLICT DO NOTHING", (now - 90 * 86400,))
                conn.execute("DELETE FROM generation_requests WHERE (user_id, request_id) IN (SELECT user_id, request_id FROM generation_requests WHERE status <> 'running' AND finished_at < ? ORDER BY finished_at LIMIT 500)", (now - 90 * 86400,))
                conn.execute("DELETE FROM mini_notifications WHERE id IN (SELECT id FROM mini_notifications WHERE created_at < ? ORDER BY created_at LIMIT 500)", (now - 180 * 86400,))
                expired = conn.execute("SELECT id, storage, storage_key FROM image_assets WHERE expires_at < ? ORDER BY expires_at LIMIT 50 FOR UPDATE SKIP LOCKED", (now,)).fetchall()
                enqueue(conn, [(r["storage"], r["storage_key"]) for r in expired])
                for row in expired:
                    conn.execute("DELETE FROM image_assets WHERE id = ?", (row["id"],))
            from app.services.workspace_sessions import prune
            prune()
            scan_orphans()
            drain()
            backfill_thumbnails()
        finally:
            lease.execute("SELECT pg_advisory_unlock(?)", (MAINTENANCE_LOCK,))
            lease.commit()

if __name__ == "__main__":
    from app.db import close_pg_pool, init_db
    try:
        init_db()
        tick()
    finally:
        close_pg_pool()
