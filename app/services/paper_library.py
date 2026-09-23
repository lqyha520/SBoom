"""Owned, immutable paper snapshots and atomically published file manifests."""

import hashlib
import json
import logging
import secrets
import time
import uuid

from fastapi import HTTPException

from app.config import get_settings
from app.db import db
from app.models.library import ArchiveCreate, ArchiveUpdate
from app.services.file_retention import enqueue
from app.services.paper_storage import storage_for, thumbnail, unpack_bundle

logger = logging.getLogger(__name__)
UPLOAD_LEASE = 180
SUMMARY_COLUMNS = """a.id, a.source_id, a.version, a.title, a.grade, a.subject, a.keyword,
    a.question_count, a.folder_id, f.name AS folder_name, a.group_id, a.group_name, a.favorite,
    a.file_status, a.file_error, a.upload_started_at, a.page_count, a.created_at, a.updated_at,
    (SELECT id FROM paper_assets WHERE paper_id = a.id AND kind IN ('thumbnail', 'page') AND page_number = 1 ORDER BY CASE WHEN kind = 'thumbnail' THEN 0 ELSE 1 END LIMIT 1) AS thumbnail_id"""


def _missing():
    raise HTTPException(404, detail={"error": "试卷或文件夹不存在"})


def _owned(conn, user_id: int, paper_id: str):
    row = conn.execute("SELECT * FROM paper_archives WHERE id = ? AND user_id = ?", (paper_id, user_id)).fetchone()
    if not row:
        _missing()
    return row


def _folder(conn, user_id: int, folder_id: str | None):
    if folder_id is not None and not conn.execute(
        "SELECT id FROM paper_folders WHERE id = ? AND user_id = ?", (folder_id, user_id)
    ).fetchone():
        _missing()


def _summary(row) -> dict:
    value = dict(row)
    value["favorite"] = bool(value["favorite"])
    if value["file_status"] == "uploading" and value["upload_started_at"] < time.time() - UPLOAD_LEASE:
        value.update(file_status="failed", file_error="上传中断，请从电脑重试文件")
    value.pop("upload_started_at", None)
    value["thumbnail_url"] = f"/api/v1/library/assets/{value['thumbnail_id']}" if value.get("thumbnail_id") else None
    return value


def _assets(conn, paper_id: str):
    rows = conn.execute(
        "SELECT id, kind, page_number, mime_type, byte_size FROM paper_assets WHERE paper_id = ? AND kind <> 'thumbnail' ORDER BY page_number",
        (paper_id,),
    ).fetchall()
    return [{**dict(row), "url": f"/api/v1/library/assets/{row['id']}"} for row in rows]


def get_paper(user_id: int, paper_id: str) -> dict:
    with db() as conn:
        row = conn.execute(
            f"SELECT {SUMMARY_COLUMNS}, a.snapshot_json FROM paper_archives a LEFT JOIN paper_folders f ON f.id = a.folder_id "
            "WHERE a.id = ? AND a.user_id = ?", (paper_id, user_id),
        ).fetchone()
        if not row:
            _missing()
        result = _summary(row)
        result["snapshot"] = json.loads(result.pop("snapshot_json"))
        result["assets"] = _assets(conn, paper_id)
        return result


def create_paper(user_id: int, request: ArchiveCreate):
    snapshot = request.snapshot.model_dump(exclude_unset=True)
    try:
        payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        encoded = payload.encode("utf-8")
    except (ValueError, TypeError, UnicodeError) as exc:
        raise HTTPException(422, detail={"error": "试卷快照包含无效数据，请检查题目与样式后重试"}) from exc
    if len(encoded) > 2 * 1024 * 1024:
        raise HTTPException(413, detail={"error": "单份试卷内容不能超过 2 MB"})
    fingerprint = hashlib.sha256(encoded).hexdigest()
    paper = snapshot["paper"]
    now = int(time.time())
    with db(serialized=True) as conn:
        replay = conn.execute(
            "SELECT id, source_id, content_hash FROM paper_archives WHERE user_id = ? AND request_id = ?",
            (user_id, request.request_id),
        ).fetchone()
        if replay and (replay["content_hash"] != fingerprint or replay["source_id"] != request.source_id):
            raise HTTPException(409, detail={"error": "保存请求已被使用，请重新保存", "code": "archive_conflict"})
        duplicate = replay or conn.execute(
            "SELECT id FROM paper_archives WHERE user_id = ? AND source_id = ? AND content_hash = ?",
            (user_id, request.source_id, fingerprint),
        ).fetchone()
        if duplicate:
            paper_id = duplicate["id"]
        else:
            _folder(conn, user_id, request.folder_id)
            count = conn.execute("SELECT COUNT(*) FROM paper_archives WHERE user_id = ?", (user_id,)).fetchone()[0]
            if count >= get_settings().archive_max_papers:
                raise HTTPException(409, detail={"error": "试卷库已达到数量上限，请先整理旧试卷"})
            version = conn.execute(
                "INSERT INTO paper_series(user_id, source_id, version) VALUES (?, ?, 1) "
                "ON CONFLICT(user_id, source_id) DO UPDATE SET version = paper_series.version + 1 RETURNING version",
                (user_id, request.source_id),
            ).fetchone()[0]
            paper_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO paper_archives(id, user_id, source_id, request_id, content_hash, version, title, grade, subject, "
                "keyword, question_count, snapshot_json, folder_id, group_id, group_name, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (paper_id, user_id, request.source_id, request.request_id, fingerprint, version,
                 paper["title"].strip() or paper["grade"] + paper["subject"] + "试卷", paper["grade"], paper["subject"],
                 paper["keyword"], sum(len(section["data"]["questions"]) for section in paper["sections"]), payload,
                 request.folder_id, request.group_id, request.group_name.strip(), now, now),
            )
    return get_paper(user_id, paper_id)


def list_papers(user_id: int, q="", grade="", subject="", folder_id=None, favorite=False, limit=20, offset=0):
    clauses, args = ["a.user_id = ?"], [user_id]
    if q.strip():
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = "%" + escaped + "%"
        clauses.append("(LOWER(a.title) LIKE LOWER(?) ESCAPE '\\' OR LOWER(a.keyword) LIKE LOWER(?) ESCAPE '\\' "
                       "OR LOWER(a.group_name) LIKE LOWER(?) ESCAPE '\\')")
        args.extend((pattern, pattern, pattern))
    for key, value in (("grade", grade), ("subject", subject)):
        if value:
            clauses.append(f"a.{key} = ?")
            args.append(value)
    if folder_id == "unfiled":
        clauses.append("a.folder_id IS NULL")
    elif folder_id:
        clauses.append("a.folder_id = ?")
        args.append(folder_id)
    if favorite:
        clauses.append("a.favorite = 1")
    where = " AND ".join(clauses)
    with db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM paper_archives a WHERE {where}", args).fetchone()[0]
        rows = conn.execute(
            f"SELECT {SUMMARY_COLUMNS} FROM paper_archives a LEFT JOIN paper_folders f ON f.id = a.folder_id "
            f"WHERE {where} ORDER BY a.created_at DESC, a.id DESC LIMIT ? OFFSET ?", [*args, limit, offset],
        ).fetchall()
        return {"items": [_summary(row) for row in rows], "total": total, "has_more": offset + len(rows) < total}


def update_paper(user_id: int, paper_id: str, request: ArchiveUpdate):
    # args 同时承载 str（folder_id/title）与 int（favorite），不能由首条 append 推定元素类型
    updates: list[str] = []
    args: list = []
    with db(serialized=True) as conn:
        _owned(conn, user_id, paper_id)
        if "folder_id" in request.model_fields_set:
            _folder(conn, user_id, request.folder_id)
            updates.append("folder_id = ?")
            args.append(request.folder_id)
        if request.favorite is not None:
            updates.append("favorite = ?")
            args.append(int(request.favorite))
        if request.title is not None:
            updates.append("title = ?")
            args.append(request.title)
        if updates:
            conn.execute(f"UPDATE paper_archives SET {', '.join(updates)}, updated_at = ? WHERE id = ? AND user_id = ?",
                         [*args, int(time.time()), paper_id, user_id])
    return get_paper(user_id, paper_id)


def _cleanup(files):
    # Record intent first; process exits and transient disk failures can be retried.
    with db() as conn:
        enqueue(conn, files)
    from app.services.file_retention import drain
    drain()


def delete_paper(user_id: int, paper_id: str):
    with db(serialized=True) as conn:
        _owned(conn, user_id, paper_id)
        if conn.execute("SELECT id FROM catalog_papers WHERE paper_id = ?", (paper_id,)).fetchone():
            raise HTTPException(409, detail={"error": "试卷已加入公共库，请先在管理后台删除对应条目"})
        if conn.execute("SELECT id FROM catalog_versions WHERE paper_id = ?", (paper_id,)).fetchone():
            raise HTTPException(409, detail={"error": "此原稿属于公共资料的修订历史，请先处理公共条目"})
        if conn.execute("SELECT 1 FROM catalog_edition_history WHERE paper_id = ?", (paper_id,)).fetchone():
            raise HTTPException(409, detail={"error": "此原稿属于公共资料的打印版本，请先处理公共条目"})
        assets = conn.execute("SELECT storage, storage_key FROM paper_assets WHERE paper_id = ?", (paper_id,)).fetchall()
        enqueue(conn, [(row["storage"], row["storage_key"]) for row in assets])
        conn.execute("DELETE FROM paper_archives WHERE id = ? AND user_id = ?", (paper_id, user_id))
    _cleanup([(row["storage"], row["storage_key"]) for row in assets])


def publish_bundle(user_id: int, paper_id: str, data: bytes):
    with db() as conn:
        current = _owned(conn, user_id, paper_id)
        ready = current["file_status"] == "ready"
    if ready:
        return get_paper(user_id, paper_id)
    files = unpack_bundle(data)
    first = next(raw for kind, page, mime, raw in files if kind == "page" and page == 1)
    files.append(("thumbnail", 1, "image/jpeg", thumbnail(first)))
    size = sum(len(content) for _, _, _, content in files)
    token, now = secrets.token_hex(16), int(time.time())
    with db(serialized=True) as conn:
        row = _owned(conn, user_id, paper_id)
        if row["file_status"] == "ready":
            ready = True
        else:
            if row["file_status"] == "uploading" and row["upload_started_at"] > now - UPLOAD_LEASE:
                raise HTTPException(409, detail={"error": "文件正在上传，请稍后刷新", "code": "upload_in_progress"})
            used = conn.execute(
                "SELECT COALESCE(SUM(s.byte_size), 0) FROM paper_assets s JOIN paper_archives a ON a.id = s.paper_id WHERE a.user_id = ?",
                (user_id,),
            ).fetchone()[0]
            reserved = conn.execute(
                "SELECT COALESCE(SUM(upload_reserved_bytes), 0) FROM paper_archives WHERE user_id = ? AND file_status = 'uploading' "
                "AND upload_started_at > ? AND id <> ?", (user_id, now - UPLOAD_LEASE, paper_id),
            ).fetchone()[0]
            if used + reserved + size > get_settings().archive_storage_mb * 1024 * 1024:
                raise HTTPException(409, detail={"error": "试卷库文件空间不足；内容已保留，请整理后重试文件"})
            conn.execute("UPDATE paper_archives SET file_status = 'uploading', file_error = '', upload_token = ?, "
                         "upload_started_at = ?, upload_reserved_bytes = ? WHERE id = ?", (token, now, size, paper_id))
    if ready:
        return get_paper(user_id, paper_id)
    backend = "local"
    written = []
    try:
        storage = storage_for(backend)
        manifest = []
        for kind, page, mime, content in files:
            filename = "paper.pdf" if kind == "pdf" else "thumbnail.jpg" if kind == "thumbnail" else f"page-{page}.jpg"
            key = f"{paper_id}/{token}/{filename}"
            written.append((backend, key))
            storage.put(key, content, mime)
            manifest.append((uuid.uuid4().hex, paper_id, kind, page, backend, key, mime, len(content), hashlib.sha256(content).hexdigest()))
        with db(serialized=True) as conn:
            current = _owned(conn, user_id, paper_id)
            if current["upload_token"] != token or current["file_status"] != "uploading":
                raise HTTPException(409, detail={"error": "上传状态已变化，请刷新试卷库"})
            conn.executemany("INSERT INTO paper_assets(id, paper_id, kind, page_number, storage, storage_key, mime_type, byte_size, sha256) "
                             "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", manifest)
            conn.execute("UPDATE paper_archives SET file_status = 'ready', file_error = '', page_count = ?, upload_token = '', "
                         "upload_reserved_bytes = 0, updated_at = ? WHERE id = ?", (sum(kind == "page" for kind, _, _, _ in files), int(time.time()), paper_id))
    except Exception as exc:
        _cleanup(written)
        with db(serialized=True) as conn:
            conn.execute("UPDATE paper_archives SET file_status = 'failed', file_error = ?, upload_reserved_bytes = 0, upload_token = '' "
                         "WHERE id = ? AND user_id = ? AND upload_token = ?",
                         ("内容已保存，文件未完成，请从电脑重试文件", paper_id, user_id, token))
        if isinstance(exc, HTTPException):
            raise
        logger.warning("Paper archive upload failed (%s)", type(exc).__name__)
        raise HTTPException(503, detail={"error": "内容已保存，文件上传失败，可从电脑重试文件"}) from exc
    return get_paper(user_id, paper_id)


def owned_asset(user_id: int, asset_id: str):
    with db() as conn:
        row = conn.execute("SELECT s.*, a.title FROM paper_assets s JOIN paper_archives a ON a.id = s.paper_id "
                           "WHERE s.id = ? AND a.user_id = ? AND a.file_status = 'ready'", (asset_id, user_id)).fetchone()
        if not row:
            _missing()
        return dict(row)


def list_folders(user_id: int):
    with db() as conn:
        rows = conn.execute("SELECT f.id, f.name, f.created_at, COUNT(a.id) AS paper_count FROM paper_folders f "
                            "LEFT JOIN paper_archives a ON a.folder_id = f.id AND a.user_id = f.user_id WHERE f.user_id = ? "
                            "GROUP BY f.id, f.name, f.created_at ORDER BY f.created_at DESC, f.id", (user_id,)).fetchall()
        return {"items": [dict(row) for row in rows]}


def save_folder(user_id: int, name: str, folder_id: str | None = None):
    with db(serialized=True) as conn:
        if folder_id:
            _folder(conn, user_id, folder_id)
        duplicate = conn.execute("SELECT id FROM paper_folders WHERE user_id = ? AND name = ?", (user_id, name)).fetchone()
        if duplicate and duplicate["id"] != folder_id:
            raise HTTPException(409, detail={"error": "已有同名文件夹"})
        if folder_id:
            conn.execute("UPDATE paper_folders SET name = ? WHERE id = ? AND user_id = ?", (name, folder_id, user_id))
        else:
            if conn.execute("SELECT COUNT(*) FROM paper_folders WHERE user_id = ?", (user_id,)).fetchone()[0] >= 100:
                raise HTTPException(409, detail={"error": "最多创建 100 个文件夹"})
            folder_id = uuid.uuid4().hex
            conn.execute("INSERT INTO paper_folders(id, user_id, name, created_at) VALUES (?, ?, ?, ?)",
                         (folder_id, user_id, name, int(time.time())))
    return {"id": folder_id, "name": name}


def delete_folder(user_id: int, folder_id: str):
    with db(serialized=True) as conn:
        _folder(conn, user_id, folder_id)
        conn.execute("DELETE FROM paper_folders WHERE id = ? AND user_id = ?", (folder_id, user_id))


def library_summary(user_id: int):
    with db() as conn:
        counts = conn.execute("SELECT COUNT(*) AS papers, COALESCE(SUM(favorite), 0) AS favorites, "
                              "COALESCE(SUM(CASE WHEN folder_id IS NULL THEN 1 ELSE 0 END), 0) AS unfiled "
                              "FROM paper_archives WHERE user_id = ?", (user_id,)).fetchone()
        used = conn.execute("SELECT COALESCE(SUM(s.byte_size), 0) FROM paper_assets s JOIN paper_archives a ON a.id = s.paper_id "
                            "WHERE a.user_id = ?", (user_id,)).fetchone()[0]
        grades = conn.execute("SELECT DISTINCT grade FROM paper_archives WHERE user_id = ? ORDER BY grade", (user_id,)).fetchall()
        subjects = conn.execute("SELECT DISTINCT subject FROM paper_archives WHERE user_id = ? ORDER BY subject", (user_id,)).fetchall()
        return {**dict(counts), "storage_bytes": used, "storage_limit_bytes": get_settings().archive_storage_mb * 1024 * 1024,
                "paper_limit": get_settings().archive_max_papers, "grades": [row[0] for row in grades], "subjects": [row[0] for row in subjects]}
