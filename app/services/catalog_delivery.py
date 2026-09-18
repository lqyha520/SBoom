"""Download destinations and metadata archives for link-only publications."""

import hashlib
import json
import time
import uuid

from fastapi import HTTPException
from pydantic import ValidationError

from app.config import get_settings
from app.models.catalog import DownloadSettings


def availability_sql(catalog_alias="c", archive_alias="a"):
    return (f"({archive_alias}.file_status = 'ready' OR "
            f"({catalog_alias}.download_mode = 'external' AND {catalog_alias}.external_url <> ''))")


def settings(body, previous=None):
    values = {key: getattr(body, key) if previous is None or key in body.model_fields_set else previous[key]
              for key in ("download_mode", "external_url", "external_code")}
    try:
        result = DownloadSettings.model_validate(values).model_dump()
    except ValidationError as exc:
        raise HTTPException(422, detail={"error": "网盘链接或提取码格式无效"}) from exc
    if result["download_mode"] == "external" and not result["external_url"]:
        raise HTTPException(422, detail={"error": "请填写网盘链接"})
    if result["download_mode"] == "pdf":
        result.update(external_url="", external_code="")
    return result


def metadata_archive(conn, user_id, body):
    """Keep the catalog's immutable source relationship without claiming a PDF exists."""
    if conn.execute("SELECT COUNT(*) FROM paper_archives WHERE user_id = ?", (user_id,)).fetchone()[0] >= get_settings().archive_max_papers:
        raise HTTPException(409, detail={"error": "试卷库已达到数量上限，请先整理旧试卷"})
    identifier, now = uuid.uuid4().hex, int(time.time())
    snapshot = json.dumps({"schema_version": 1,
                          "paper": {"title": body.title.strip(), "grade": body.grade.strip(),
                                    "subject": body.subject.strip(), "keyword": "", "difficulty": "", "sections": []},
                          "template": {}, "style": {}, "export_options": {"mode": "student"}}, ensure_ascii=False)
    conn.execute("INSERT INTO paper_archives(id, user_id, source_id, request_id, content_hash, version, title, grade, subject, "
                 "keyword, question_count, snapshot_json, group_id, group_name, created_at, updated_at) "
                 "VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, '', 0, ?, '', '', ?, ?)",
                 (identifier, user_id, "external-" + identifier, "external-" + identifier,
                  hashlib.sha256(snapshot.encode()).hexdigest(), body.title.strip(), body.grade.strip(), body.subject.strip(), snapshot, now, now))
    return identifier
