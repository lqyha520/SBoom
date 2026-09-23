"""Private image files with per-owner quota and expiring metadata."""
import base64
import time
import uuid

from fastapi import HTTPException

from app.config import get_settings
from app.db import db
from app.services.file_retention import enqueue
from app.services.paper_storage import storage_for

MAX_IMAGE_BYTES = 12 * 1024 * 1024

def admit(conn, user_id):
    used = conn.execute("SELECT COALESCE(SUM(byte_size), 0) FROM image_assets WHERE user_id = ?", (user_id,)).fetchone()[0]
    running = conn.execute("SELECT COUNT(*) FROM generation_requests WHERE user_id = ? AND kind = 'image' AND status = 'running' AND created_at >= ?",
                           (user_id, int(time.time()) - get_settings().generation_lease_seconds)).fetchone()[0]
    if used + (running + 1) * MAX_IMAGE_BYTES > get_settings().image_storage_mb * 1024 * 1024:
        raise HTTPException(409, detail={"error": "生图文件空间不足，请等待历史图片过期清理后再生成", "code": "image_storage_quota"})

def persist(user_id, request_id, result):
    if not result.get("b64_json"):
        return result
    raw = base64.b64decode(result["b64_json"], validate=True)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Image exceeds reserved storage")
    asset_id = uuid.uuid4().hex
    key = f"images/{user_id}/{asset_id}.png"
    expires = int(time.time()) + get_settings().generation_result_days * 86400
    try:
        storage_for().put(key, raw, "image/png")
        with db(serialized="generation") as conn:
            conn.execute("INSERT INTO image_assets(id, user_id, request_id, storage, storage_key, byte_size, width, height, expires_at) VALUES (?, ?, ?, 'local', ?, ?, ?, ?, ?)",
                         (asset_id, user_id, request_id, key, len(raw), result["width"], result["height"], expires))
    except BaseException:
        with db() as conn:
            enqueue(conn, [("local", key)])
        raise
    return {**{k: v for k, v in result.items() if k != "b64_json"}, "asset_id": asset_id,
            "url": f"/api/v1/image-generation/assets/{asset_id}", "byte_size": len(raw), "expires_at": expires}

def owned(user_id, asset_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM image_assets WHERE id = ? AND user_id = ?", (asset_id, user_id)).fetchone()
    if not row:
        raise HTTPException(404, detail={"error": "图片不存在"})
    if row["expires_at"] <= time.time():
        raise HTTPException(410, detail={"error": "图片已过期，请使用已下载的本机副本"})
    return {**dict(row), "kind": "image", "mime_type": "image/png"}
