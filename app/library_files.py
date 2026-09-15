"""Private file responses shared by owned archives and published catalog items."""

import re
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from app.services.paper_storage import LocalStorage, storage_for


def asset_response(asset):
    storage = storage_for(asset["storage"])
    headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
    if asset["kind"] == "pdf":
        title = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', "_", asset["title"])[:120] or "paper"
        headers["Content-Disposition"] = "attachment; filename=paper.pdf; filename*=UTF-8''" + quote(title + ".pdf", safe="")
        headers["Content-Security-Policy"] = "sandbox"
    try:
        if isinstance(storage, LocalStorage):
            path = storage.path(asset["storage_key"])
            if not path.is_file():
                raise FileNotFoundError()
            return FileResponse(path, media_type=asset["mime_type"], headers=headers)
        stream = storage.stream(asset["storage_key"])
        headers["Content-Length"] = str(asset["byte_size"])
        return StreamingResponse(stream, media_type=asset["mime_type"], headers=headers)
    except Exception as exc:
        raise HTTPException(503, detail={"error": "文件暂不可用，请稍后重试或联系管理员"}) from exc
