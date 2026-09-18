"""Manually import external PDFs as first-class paper archives.

把管理员手里的现成 PDF（非工作台生成）转成与工作台产出完全同构的
paper_archives + paper_assets，从而复用公共习题发布的全部既有逻辑：
文件校验、存储配额、预览图、缩略图、访问权限都不需要特判。

渲染产物在内存里按 publish_bundle 期望的清单（paper.pdf + page-N.jpg）
打包成 ZIP 交给既有入库管线，保证与工作台导出的文件结构逐字节同规。
"""

import hashlib
import io
import json
import time
import uuid
import zipfile

from fastapi import HTTPException
from PIL import Image

from app.config import get_settings
from app.db import db
from app.services import paper_library
from app.services.paper_storage import MAX_PAGES

MAX_IMPORT_BYTES = 32 * 1024 * 1024  # 与 unpack_bundle 对单份 PDF 的上限一致
RENDER_SCALE = 2  # A4 595pt → 1190px 宽，与工作台导出的预览页观感一致
JPEG_QUALITY = 80


def _render_pages(data: bytes) -> list[bytes]:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:  # pragma: no cover - 依赖清单已固定
        raise HTTPException(503, detail={"error": "服务端暂不支持 PDF 解析，请联系管理员"}) from exc
    try:
        document = pdfium.PdfDocument(data)
    except Exception as exc:
        raise HTTPException(422, detail={"error": "PDF 无法解析，请确认文件未损坏、未加密"}) from exc
    try:
        count = len(document)
        if count < 1:
            raise HTTPException(422, detail={"error": "PDF 里没有页面"})
        if count > MAX_PAGES:
            raise HTTPException(413, detail={"error": f"PDF 最多 {MAX_PAGES} 页，请先拆分文件"})
        pages = []
        for index in range(count):
            page = document[index]
            try:
                width, height = page.get_size()
                if width <= 0 or height <= 0:
                    raise HTTPException(422, detail={"error": "PDF 页面尺寸无效"})
                # Landscape and large pages must fit the same private preview bounds.
                bitmap = page.render(scale=min(RENDER_SCALE, 1200 / width, 1800 / height))
                try:
                    image = bitmap.to_pil().convert("RGB")
                    try:
                        image.thumbnail((1200, 1800), Image.Resampling.LANCZOS)
                        buffer = io.BytesIO()
                        image.save(buffer, "JPEG", quality=JPEG_QUALITY)
                        pages.append(buffer.getvalue())
                    finally:
                        image.close()
                finally:
                    bitmap.close()
            finally:
                page.close()
        return pages
    finally:
        document.close()


def _bundle(pages: list[bytes], data: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("paper.pdf", data)
        for number, page in enumerate(pages, 1):
            archive.writestr(f"page-{number}.jpg", page)
    return buffer.getvalue()


IMPORT_MODES = ("student", "answersOnly", "withAnswers")
MODE_LABELS = {"student": "练习版", "answersOnly": "答案版", "withAnswers": "习题与答案版"}


def import_paper(user_id: int, title: str, grade: str, subject: str, data: bytes, mode: str = "withAnswers") -> dict:
    """把一份 PDF 变成 file_status=ready 的私有试卷归档，返回归档详情。"""
    title = (title or "").strip() or "导入的习题"
    grade, subject = (grade or "").strip(), (subject or "").strip()
    if not grade or not subject:
        raise HTTPException(422, detail={"error": "请选择年级和科目"})
    if mode not in IMPORT_MODES:
        raise HTTPException(422, detail={"error": f"导出模式无效，可选：{'、'.join(MODE_LABELS[m] for m in IMPORT_MODES)}"})
    if not data.startswith(b"%PDF-"):
        raise HTTPException(422, detail={"error": "仅支持 PDF 文件"})
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(413, detail={"error": "PDF 不能超过 32 MB"})
    digest = hashlib.sha256(data).hexdigest()
    pages = _render_pages(data)
    snapshot = json.dumps({
        "schema_version": 1,
        "paper": {"title": title, "grade": grade, "subject": subject, "keyword": "", "difficulty": "", "sections": []},
        "template": {}, "style": {}, "export_options": {"mode": mode},
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    now = int(time.time())
    with db(serialized=True) as conn:
        # 同一管理员重复导入同一份 PDF 时复用既有归档，避免试卷库堆积重复文件
        replay = conn.execute(
            "SELECT id FROM paper_archives WHERE user_id = ? AND source_id = ? AND content_hash = ?",
            (user_id, f"import-{digest[:32]}", digest),
        ).fetchone()
        if replay:
            paper_id = replay["id"]
        else:
            if conn.execute("SELECT COUNT(*) FROM paper_archives WHERE user_id = ?", (user_id,)).fetchone()[0] \
                    >= get_settings().archive_max_papers:
                raise HTTPException(409, detail={"error": "试卷库已达到数量上限，请先整理旧试卷"})
            version = conn.execute(
                "INSERT INTO paper_series(user_id, source_id, version) VALUES (?, ?, 1) "
                "ON CONFLICT(user_id, source_id) DO UPDATE SET version = paper_series.version + 1 RETURNING version",
                (user_id, f"import-{digest[:32]}"),
            ).fetchone()[0]
            paper_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO paper_archives(id, user_id, source_id, request_id, content_hash, version, title, grade, subject, "
                "keyword, question_count, snapshot_json, folder_id, group_id, group_name, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (paper_id, user_id, f"import-{digest[:32]}", f"import-{digest}", digest, version, title, grade, subject,
                 "", 0, snapshot, None, "", "", now, now),
            )
    paper_library.publish_bundle(user_id, paper_id, _bundle(pages, data))
    return paper_library.get_paper(user_id, paper_id)
