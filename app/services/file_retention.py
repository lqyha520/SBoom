"""Durable deletion retries; grace-aware bounded orphan reconciliation."""
import itertools
import logging
import time

from app.constants import UPLOAD_LEASE
from app.db import db
from app.services.paper_storage import storage_for
from app.storage_registry import MANAGED_KEY, REFERENCES

logger = logging.getLogger(__name__)
_scan = None
_scan_root = None

def enqueue(conn, files):
    conn.executemany("INSERT INTO file_deletions(storage, storage_key, next_attempt) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                     [(storage, key, int(time.time()) + 6 * 3600) for storage, key in files])

def referenced(conn, storage, key):
    # 任一登记表（app/storage_registry.py）引用即视为在用；空后端名与 local 都指本地磁盘
    backends = ("local", "") if storage in ("local", "") else (storage, storage)
    return any(conn.execute(f"SELECT 1 FROM {ref.table} WHERE {ref.storage_column} IN (?, ?) AND {ref.key_column} = ?",
                            (*backends, key)).fetchone() for ref in REFERENCES)

def drain(limit=50):
    now = int(time.time())
    with db() as conn:
        rows = conn.execute("SELECT * FROM file_deletions WHERE next_attempt <= ? ORDER BY next_attempt LIMIT ? FOR UPDATE SKIP LOCKED", (now, limit)).fetchall()
        for row in rows:
            args = (row["storage"], row["storage_key"])
            if referenced(conn, *args):
                conn.execute("DELETE FROM file_deletions WHERE storage = ? AND storage_key = ?", args)
                continue
            try:
                storage_for(row["storage"]).delete(row["storage_key"])
            except Exception:
                attempts = row["attempts"] + 1
                conn.execute("UPDATE file_deletions SET attempts = ?, next_attempt = ? WHERE storage = ? AND storage_key = ?",
                             (attempts, now + min(86400, 60 * 2 ** min(attempts, 10)), *args))
                logger.warning("Private file deletion deferred (attempt %s)", attempts)
            else:
                conn.execute("DELETE FROM file_deletions WHERE storage = ? AND storage_key = ?", args)

def scan_orphans(limit=500):
    global _scan, _scan_root
    root = storage_for().path(".")
    if _scan is None or root != _scan_root:
        _scan_root, _scan = root, root.rglob("*")
    paths = list(itertools.islice(_scan, limit))
    if len(paths) < limit:
        _scan = None
    cutoff = time.time() - 86400  # Beyond every upload and generation lease.
    with db() as conn:
        for path in paths:
            try:
                key = path.relative_to(root).as_posix()
                # 只回收应用自己生成的存储键：目录里的密钥、备份等其他文件再旧也不碰
                if not MANAGED_KEY.fullmatch(key) or path.is_symlink() or not path.is_file() or path.stat().st_mtime >= cutoff:
                    continue
                if not referenced(conn, "local", key):
                    # Active uploads may be writing into an older directory.
                    parts = key.split("/")
                    if len(parts) > 2 and conn.execute("SELECT 1 FROM paper_archives WHERE id = ? AND upload_token = ? AND file_status = 'uploading' AND upload_started_at > ?", (parts[0], parts[1], int(time.time()) - UPLOAD_LEASE)).fetchone():
                        continue
                    enqueue(conn, [("local", key)])
            except FileNotFoundError:
                continue
