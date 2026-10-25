"""Private file responses shared by owned archives and published catalog items."""

import io
import re
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response
from PIL import Image

from app.memory_cache import MemoryCache
from app.services.paper_storage import storage_for
from app.services.resource_admission import admitted_media

_previews: MemoryCache[bytes] = MemoryCache(ttl=300, max_entries=128, max_weight=8 * 1024 * 1024, weigh=len)


def limited_preview(asset):
    # 路由先核验实时权限；只缓存派生像素，不缓存账号或授权结果。
    path = storage_for(asset["storage"]).path(asset["storage_key"])
    try:
        stat = path.stat()
        key = (str(path), asset.get("sha256"), stat.st_mtime_ns, stat.st_size)

        def render():
            with admitted_media(), Image.open(path) as source:
                source.thumbnail((480, 720))
                output = io.BytesIO()
                source.convert("RGB").save(output, "JPEG", quality=65)
                return output.getvalue()

        data = _previews.get_or_load(key, render)
    except OSError as exc:
        raise HTTPException(503, detail={"error": "文件暂不可用，请稍后重试或联系管理员"}) from exc
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, no-store", "Vary": "Authorization"})


def asset_response(asset, *, cache_control: str | None = None):
    storage = storage_for(asset["storage"])
    headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
    if cache_control:
        headers["Cache-Control"] = cache_control
        if asset.get("sha256"):
            headers["ETag"] = '"' + asset["sha256"] + '"'
    if asset["kind"] == "pdf":
        title = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', "_", asset["title"])[:120] or "paper"
        headers["Content-Disposition"] = "attachment; filename=paper.pdf; filename*=UTF-8''" + quote(title + ".pdf", safe="")
        headers["Content-Security-Policy"] = "sandbox"
    try:
        path = storage.path(asset["storage_key"])
        if not path.is_file():
            raise FileNotFoundError()
        return FileResponse(path, media_type=asset["mime_type"], headers=headers)
    except Exception as exc:
        raise HTTPException(503, detail={"error": "文件暂不可用，请稍后重试或联系管理员"}) from exc
