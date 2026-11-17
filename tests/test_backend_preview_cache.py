"""预览保留原始图片字节，受限资源不缓存，文件变化或删除立即生效。"""

import io
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app import library_files
from app.services.paper_storage import LocalStorage


def test_preview_preserves_original_and_observes_file_changes(tmp_path):
    path = tmp_path / "page.jpg"
    Image.new("RGB", (1000, 1400), "white").save(path)
    asset = {"storage": "local", "storage_key": "page.jpg", "kind": "page", "mime_type": "image/jpeg"}
    app = FastAPI()

    @app.get("/preview")
    def preview():
        return library_files.asset_response(asset)

    with patch.object(LocalStorage, "path", return_value=path), TestClient(app) as client:
        first = client.get("/preview")
        assert first.status_code == 200
        assert first.content == path.read_bytes()
        second = client.get("/preview")
        assert first.content == second.content
        assert second.headers["cache-control"] == "private, no-store"
        with Image.open(io.BytesIO(first.content)) as image:
            assert image.size == (1000, 1400)
        Image.new("RGB", (600, 800), "black").save(path)
        changed = client.get("/preview")
        assert changed.content == path.read_bytes() and changed.content != first.content
        path.unlink()
        assert client.get("/preview").status_code == 503
