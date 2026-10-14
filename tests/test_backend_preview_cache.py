"""派生预览缓存只复用像素，文件变化或删除立即生效。"""

import io
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from PIL import Image

from app import library_files
from app.services.paper_storage import LocalStorage


def test_preview_reuses_encoding_but_observes_file_changes(tmp_path):
    path = tmp_path / "page.jpg"
    Image.new("RGB", (1000, 1400), "white").save(path)
    asset = {"storage": "local", "storage_key": "page.jpg", "sha256": "revision-one"}
    library_files._previews.clear()
    with patch.object(LocalStorage, "path", return_value=path):
        first = library_files.limited_preview(asset)
        with patch.object(library_files.Image, "open", side_effect=AssertionError("缓存命中不应解码")):
            second = library_files.limited_preview(asset)
        assert first.body == second.body
        assert second.headers["cache-control"] == "private, no-store"
        with Image.open(io.BytesIO(first.body)) as image:
            assert image.width <= 480 and image.height <= 720
        Image.new("RGB", (600, 800), "black").save(path)
        assert library_files.limited_preview(asset).body != first.body
        path.unlink()
        with pytest.raises(HTTPException) as error:
            library_files.limited_preview(asset)
        assert error.value.status_code == 503
