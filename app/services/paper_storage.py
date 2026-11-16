"""Private file storage and bounded archive bundle validation."""

import io
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from app.config import get_settings

MAX_PAGES = 40
MAX_EXPANDED_BYTES = 64 * 1024 * 1024


def _key(key: str) -> str:
    path = PurePosixPath(key)
    if path.is_absolute() or ".." in path.parts or "\\" in key or not re.fullmatch(r"[a-zA-Z0-9/_.-]+", key):
        raise ValueError("Invalid private storage key")
    return key


class LocalStorage:
    def path(self, key: str) -> Path:
        configured = get_settings().archive_local_dir
        root = Path(configured) if configured else Path(__file__).resolve().parents[2] / "data" / "paper-files"
        root = root.resolve()
        path = (root / _key(key)).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Private storage path escapes its root")
        return path

    def put(self, key: str, data: bytes, mime: str) -> None:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Each upload has a fresh random prefix; a completed file is never replaced.
        with path.open("xb") as stream:
            stream.write(data)

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)


def storage_for(name: str | None = None) -> LocalStorage:
    """私有文件存储后端。已移除 COS 支持，仅保留本地磁盘存储。"""
    if name not in (None, "", "local"):
        raise ValueError(f"Unsupported storage backend: {name!r}")
    return LocalStorage()


def unpack_bundle(data: bytes | BinaryIO, *, max_pages: int = MAX_PAGES, separate_answers: bool = False) -> list[tuple[str, int, str, bytes]]:
    """Validate in memory; never extract user-provided ZIP paths to the filesystem."""
    try:
        with zipfile.ZipFile(io.BytesIO(data) if isinstance(data, bytes) else data) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            pdf_names = {"paper.pdf", "answers.pdf"} if separate_answers else {"paper.pdf"}
            if not 1 + len(pdf_names) <= len(entries) <= max_pages + len(pdf_names) or len(names) != len(set(names)):
                raise ValueError("Invalid file count")
            page_count = len(entries) - len(pdf_names)
            expected = {*pdf_names, *(f"page-{i}.jpg" for i in range(1, page_count + 1))}
            if set(names) != expected:
                raise ValueError("PDF and consecutive page images are required")
            if sum(entry.file_size for entry in entries) > MAX_EXPANDED_BYTES:
                raise ValueError("Expanded bundle is too large")
            for entry in entries:
                if entry.is_dir() or entry.flag_bits & 1 or entry.file_size <= 0:
                    raise ValueError("Invalid ZIP entry")
                if entry.file_size > (32 * 1024 * 1024 if entry.filename in pdf_names else 3 * 1024 * 1024):
                    raise ValueError("File is too large")
            pdf = archive.read("paper.pdf")
            if not pdf.startswith(b"%PDF-") or not pdf.rstrip().endswith(b"%%EOF"):
                raise ValueError("Invalid PDF")
            files = [("pdf", 0, "application/pdf", pdf)]
            if separate_answers:
                answers = archive.read("answers.pdf")
                if not answers.startswith(b"%PDF-") or not answers.rstrip().endswith(b"%%EOF"):
                    raise ValueError("Invalid answer PDF")
                from app.services.catalog_import import validate_split_pages
                validate_split_pages(pdf, answers, page_count, max_pages)
                files.append(("answers_pdf", 0, "application/pdf", answers))
            for page in range(1, page_count + 1):
                raw = archive.read(f"page-{page}.jpg")
                with Image.open(io.BytesIO(raw)) as image:
                    if image.format != "JPEG" or not (1 <= image.width <= 1200 and 1 <= image.height <= 1800):
                        raise ValueError("Invalid preview dimensions or format")
                    image.verify()
                with Image.open(io.BytesIO(raw)) as image:
                    normalized = io.BytesIO()
                    image.convert("RGB").save(normalized, format="JPEG", quality=90)
                    files.append(("page", page, "image/jpeg", normalized.getvalue()))
            return files
    except (ValueError, OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError, UnidentifiedImageError) as exc:
        label = "学生卷 PDF、答案 PDF 与连续的学生卷 JPEG 页面" if separate_answers else "PDF 与连续的 JPEG 页面"
        raise HTTPException(422, detail={"error": f"文件包无效：需包含{label}，合计最多 {max_pages} 页"}) from exc


def thumbnail(raw: bytes) -> bytes:
    with Image.open(io.BytesIO(raw)) as image:
        image.thumbnail((320, 480), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        image.convert("RGB").save(out, format="JPEG", quality=82, optimize=True)
        return out.getvalue()
