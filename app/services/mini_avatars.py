"""Small, normalized user photos. Originals and external URLs are never retained."""

import base64
import binascii
import io
import re
import time
import uuid
import warnings

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

from app.db import db
from app.models.mini import MAX_AVATAR_BYTES, MiniAvatarUpdate
from app.services import mini_auth


def normalize_image(encoded: str) -> str:
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, detail={"error": "头像图片数据无效，请重新选择"}) from exc
    if len(raw) > MAX_AVATAR_BYTES:
        raise HTTPException(413, detail={"error": "头像不能超过 2 MB，请选择较小的图片"})
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"} or getattr(image, "n_frames", 1) != 1:
                    raise HTTPException(415, detail={"error": "请选择 JPG、PNG 或 WebP 静态图片"})
                if max(image.size) > 4096 or image.width * image.height > 16_000_000:
                    raise HTTPException(413, detail={"error": "头像尺寸过大，请选择较小的图片"})
                image.load()
                square = ImageOps.fit(ImageOps.exif_transpose(image).convert("RGBA"), (256, 256), Image.Resampling.LANCZOS)
                # A fresh RGB canvas also drops location, EXIF and other source metadata.
                photo = Image.new("RGB", (256, 256), "white")
                photo.paste(square, mask=square.getchannel("A"))
                output = io.BytesIO()
                photo.save(output, "JPEG", quality=85, optimize=True)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(422, detail={"error": "头像图片无法读取，请重新选择"}) from exc
    return base64.b64encode(output.getvalue()).decode("ascii")


def save(user_id: str, body: MiniAvatarUpdate):
    content = normalize_image(body.image)
    version, now = uuid.uuid4().hex[:24], int(time.time())
    with db(serialized="accounts") as conn:
        user = mini_auth._user(conn, user_id)
        conn.execute("INSERT INTO mini_user_avatars(user_id, version, content_base64, updated_at) VALUES (?, ?, ?, ?) "
                     "ON CONFLICT(user_id) DO UPDATE SET version = excluded.version, content_base64 = excluded.content_base64, updated_at = excluded.updated_at",
                     (user_id, version, content, now))
        conn.execute("UPDATE mini_users SET avatar = ?, nickname = ?, revision = revision + 1, updated_at = ? WHERE id = ?",
                     ("photo:" + version, body.nickname if body.nickname is not None else user.nickname, now, user_id))
        return mini_auth._user(conn, user_id).public()


def read(user_id: str, version: str, admin=False) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{24}", version):
        raise HTTPException(404, detail={"error": "头像不存在"})
    with db() as conn:
        row = conn.execute("SELECT a.content_base64 FROM mini_user_avatars a JOIN mini_users u ON u.id = a.user_id "
                           "WHERE a.user_id = ? AND a.version = ? AND u.avatar = ?" + ("" if admin else " AND u.is_active = 1"),
                           (user_id, version, "photo:" + version)).fetchone()
        if not row:
            raise HTTPException(404, detail={"error": "头像已更新或不存在"})
        return base64.b64decode(row["content_base64"])
