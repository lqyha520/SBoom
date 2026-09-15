"""Private file storage and bounded archive bundle validation."""

import io
import re
import zipfile
from pathlib import Path, PurePosixPath

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

    def put(self, key: str, data: bytes, mime: str):
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Each upload has a fresh random prefix; a completed file is never replaced.
        with path.open("xb") as stream:
            stream.write(data)

    def delete(self, key: str):
        self.path(key).unlink(missing_ok=True)


class CosStorage:
    def __init__(self):
        settings = get_settings()
        if not all((settings.cos_region, settings.cos_bucket, settings.cos_secret_id, settings.cos_secret_key)):
            raise HTTPException(503, detail={"error": "私有文件存储尚未配置，请联系管理员"})
        try:
            from qcloud_cos import CosConfig, CosS3Client
        except ImportError as exc:
            raise HTTPException(503, detail={"error": "COS 存储组件尚未安装，请联系管理员"}) from exc
        self.bucket = settings.cos_bucket
        self.client = CosS3Client(CosConfig(
            Region=settings.cos_region, SecretId=settings.cos_secret_id,
            SecretKey=settings.cos_secret_key, Scheme="https", Timeout=20,
        ))

    def put(self, key: str, data: bytes, mime: str):
        self.client.put_object(Bucket=self.bucket, Key="learn-coach/" + _key(key), Body=data,
                               ContentType=mime, ACL="private", EnableMD5=True)

    def delete(self, key: str):
        self.client.delete_object(Bucket=self.bucket, Key="learn-coach/" + _key(key))

    def stream(self, key: str):
        response = self.client.get_object(Bucket=self.bucket, Key="learn-coach/" + _key(key))
        body = response["Body"].get_raw_stream()

        def chunks():
            try:
                while chunk := body.read(64 * 1024):
                    yield chunk
            finally:
                body.close()

        return chunks()


def storage_for(name: str | None = None):
    name = name or get_settings().archive_storage
    if name == "local":
        return LocalStorage()
    if name == "cos":
        return CosStorage()
    raise ValueError("Unsupported storage backend")


def unpack_bundle(data: bytes) -> list[tuple[str, int, str, bytes]]:
    """Validate in memory; never extract user-provided ZIP paths to the filesystem."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if not 2 <= len(entries) <= MAX_PAGES + 1 or len(names) != len(set(names)):
                raise ValueError("Invalid file count")
            page_count = len(entries) - 1
            expected = {"paper.pdf", *(f"page-{i}.jpg" for i in range(1, page_count + 1))}
            if set(names) != expected:
                raise ValueError("PDF and consecutive page images are required")
            if sum(entry.file_size for entry in entries) > MAX_EXPANDED_BYTES:
                raise ValueError("Expanded bundle is too large")
            for entry in entries:
                if entry.is_dir() or entry.flag_bits & 1 or entry.file_size <= 0:
                    raise ValueError("Invalid ZIP entry")
                if entry.file_size > (32 * 1024 * 1024 if entry.filename == "paper.pdf" else 3 * 1024 * 1024):
                    raise ValueError("File is too large")
            pdf = archive.read("paper.pdf")
            if not pdf.startswith(b"%PDF-") or not pdf.rstrip().endswith(b"%%EOF"):
                raise ValueError("Invalid PDF")
            files = [("pdf", 0, "application/pdf", pdf)]
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
        raise HTTPException(422, detail={"error": "文件包无效：需包含 PDF 与连续的 JPEG 页面，最多 40 页"}) from exc
