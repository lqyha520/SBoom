"""小程序运营内容（分类 / Banner / 公告 / 协议文档 / 年级科目字典）的读写与公开视图。

管理端做增删改查 + 排序 + 上下线；小程序端只读，且只能拿到「可见且在有效期内」的数据。
图片沿用试卷库的私有存储（LocalStorage / CosStorage），经由后端鉴权后转发，不暴露直链。
"""

import io
import time
import uuid

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from app.db import db
from app.models.site import (
    BannerInput,
    BannerUpdate,
    CategoryInput,
    CategoryUpdate,
    DictionaryInput,
    DictionaryUpdate,
    DocumentUpdate,
    NoticeInput,
    NoticeUpdate,
)
from app.services.paper_storage import storage_for

MAX_IMAGE_BYTES = 2 * 1024 * 1024
ALLOWED_IMAGE_MIMES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_IMAGE_WIDTH = 2400
MAX_IMAGE_HEIGHT = 1600
DOCUMENT_KEYS = {"agreement", "privacy"}


def _now() -> int:
    return int(time.time())


def _conflict(message: str):
    return HTTPException(409, detail={"error": message})


def _missing(message: str = "内容不存在或已被删除"):
    return HTTPException(404, detail={"error": message})


def _clean(value: str) -> str:
    return value.strip()


def _as_int(value) -> int:
    return 1 if value else 0


# ─── 分类 ───

def _category_row(row) -> dict:
    item = dict(row)
    item["is_visible"] = bool(item["is_visible"])
    return item


def list_categories(include_hidden: bool = True) -> dict:
    where = "" if include_hidden else " WHERE is_visible = 1"
    with db() as conn:
        rows = conn.execute(f"SELECT * FROM site_categories{where} ORDER BY sort_order, name").fetchall()
        counts = {row["category_id"]: row["total"] for row in conn.execute(
            "SELECT category_id, COUNT(*) AS total FROM catalog_papers WHERE category_id <> '' GROUP BY category_id")}
    items = [{**_category_row(row), "paper_count": counts.get(row["id"], 0)} for row in rows]
    return {"items": items}


def create_category(body: CategoryInput) -> dict:
    now = _now()
    name = _clean(body.name)
    with db(serialized=True) as conn:
        if conn.execute("SELECT 1 FROM site_categories WHERE name = ?", (name,)).fetchone():
            raise _conflict("已存在同名分类")
        order = body.sort_order or (conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 10 FROM site_categories").fetchone()[0])
        category_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO site_categories(id, name, description, icon, sort_order, is_visible, revision, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (category_id, name, _clean(body.description), _clean(body.icon), order, _as_int(body.is_visible), now, now),
        )
    return _one_category(category_id)


def update_category(category_id: str, body: CategoryUpdate) -> dict:
    now = _now()
    name = _clean(body.name)
    with db(serialized=True) as conn:
        row = conn.execute("SELECT revision FROM site_categories WHERE id = ?", (category_id,)).fetchone()
        if not row:
            raise _missing("分类不存在")
        if row["revision"] != body.revision:
            raise _conflict("分类已被其他操作更新，请刷新后重试")
        clash = conn.execute("SELECT id FROM site_categories WHERE name = ? AND id <> ?", (name, category_id)).fetchone()
        if clash:
            raise _conflict("已存在同名分类")
        conn.execute(
            "UPDATE site_categories SET name = ?, description = ?, icon = ?, sort_order = ?, is_visible = ?, "
            "revision = revision + 1, updated_at = ? WHERE id = ?",
            (name, _clean(body.description), _clean(body.icon), body.sort_order, _as_int(body.is_visible), now, category_id),
        )
        # 分类名冗余存在 catalog_papers 上（列表与搜索直接命中），改名时同步，避免小程序显示旧名
        conn.execute("UPDATE catalog_papers SET category = ?, updated_at = ? WHERE category_id = ?", (name, now, category_id))
    return _one_category(category_id)


def delete_category(category_id: str, revision: int) -> None:
    with db(serialized=True) as conn:
        row = conn.execute("SELECT revision FROM site_categories WHERE id = ?", (category_id,)).fetchone()
        if not row:
            raise _missing("分类不存在")
        if row["revision"] != revision:
            raise _conflict("分类已被其他操作更新，请刷新后重试")
        used = conn.execute("SELECT COUNT(*) FROM catalog_papers WHERE category_id = ?", (category_id,)).fetchone()[0]
        if used:
            raise _conflict(f"还有 {used} 份习题属于该分类，请先调整这些习题的分类")
        conn.execute("DELETE FROM site_categories WHERE id = ?", (category_id,))


def _one_category(category_id: str) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM site_categories WHERE id = ?", (category_id,)).fetchone()
        if not row:
            raise _missing("分类不存在")
        total = conn.execute("SELECT COUNT(*) FROM catalog_papers WHERE category_id = ?", (category_id,)).fetchone()[0]
    return {**_category_row(row), "paper_count": total}


def reorder_categories(ids: list[str]) -> dict:
    now = _now()
    with db(serialized=True) as conn:
        known = {row["id"] for row in conn.execute("SELECT id FROM site_categories")}
        unknown = [item for item in ids if item not in known]
        if unknown:
            raise _missing("排序列表包含不存在的分类")
        for index, category_id in enumerate(ids):
            conn.execute("UPDATE site_categories SET sort_order = ?, revision = revision + 1, updated_at = ? WHERE id = ?",
                         ((index + 1) * 10, now, category_id))
    return list_categories()


# ─── 首页 Banner ───

def _banner_row(row) -> dict:
    item = dict(row)
    item["is_visible"] = bool(item["is_visible"])
    item["image_url"] = f"/api/v1/site/banners/{item['id']}/image" if item["image_key"] else None
    return item


def list_banners() -> dict:
    with db() as conn:
        rows = conn.execute("SELECT * FROM site_banners ORDER BY sort_order, created_at, id").fetchall()
    return {"items": [_banner_row(row) for row in rows]}


def _one_banner(banner_id: str) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM site_banners WHERE id = ?", (banner_id,)).fetchone()
    if not row:
        raise _missing("Banner 不存在")
    return _banner_row(row)


def create_banner(body: BannerInput) -> dict:
    now = _now()
    with db(serialized=True) as conn:
        order = body.sort_order or (conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 10 FROM site_banners").fetchone()[0])
        banner_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO site_banners(id, kicker, title, subtitle, action_label, target_type, target_value, sort_order, "
            "is_visible, revision, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (banner_id, _clean(body.kicker), _clean(body.title), _clean(body.subtitle), _clean(body.action_label),
             body.target_type, _clean(body.target_value), order, _as_int(body.is_visible), now, now),
        )
    return _one_banner(banner_id)


def update_banner(banner_id: str, body: BannerUpdate) -> dict:
    now = _now()
    with db(serialized=True) as conn:
        row = conn.execute("SELECT revision FROM site_banners WHERE id = ?", (banner_id,)).fetchone()
        if not row:
            raise _missing("Banner 不存在")
        if row["revision"] != body.revision:
            raise _conflict("Banner 已被其他操作更新，请刷新后重试")
        conn.execute(
            "UPDATE site_banners SET kicker = ?, title = ?, subtitle = ?, action_label = ?, target_type = ?, target_value = ?, "
            "sort_order = ?, is_visible = ?, revision = revision + 1, updated_at = ? WHERE id = ?",
            (_clean(body.kicker), _clean(body.title), _clean(body.subtitle), _clean(body.action_label), body.target_type,
             _clean(body.target_value), body.sort_order, _as_int(body.is_visible), now, banner_id),
        )
    return _one_banner(banner_id)


def delete_banner(banner_id: str, revision: int) -> None:
    with db(serialized=True) as conn:
        row = conn.execute("SELECT revision, image_key, image_storage FROM site_banners WHERE id = ?", (banner_id,)).fetchone()
        if not row:
            raise _missing("Banner 不存在")
        if row["revision"] != revision:
            raise _conflict("Banner 已被其他操作更新，请刷新后重试")
        conn.execute("DELETE FROM site_banners WHERE id = ?", (banner_id,))
    _drop_image(row["image_key"], row["image_storage"])


def _drop_image(key: str, storage_name: str) -> None:
    if not key:
        return
    try:
        storage_for(storage_name or None).delete(key)
    except Exception:
        # 存储清理失败不应阻塞内容操作：残留文件由运维清理
        pass


def save_banner_image(banner_id: str, content_type: str, data: bytes) -> dict:
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in ALLOWED_IMAGE_MIMES:
        raise HTTPException(415, detail={"error": "Banner 图片仅支持 JPG、PNG 或 WebP"})
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, detail={"error": "Banner 图片不能超过 2 MB"})
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.width, image.height
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(422, detail={"error": "Banner 图片无法解析，请换一张"}) from exc
    if not (1 <= width <= MAX_IMAGE_WIDTH and 1 <= height <= MAX_IMAGE_HEIGHT):
        raise HTTPException(422, detail={"error": f"Banner 图片尺寸需在 {MAX_IMAGE_WIDTH}×{MAX_IMAGE_HEIGHT} 以内"})

    from app.config import get_settings

    storage_name = get_settings().archive_storage
    key = f"site/banners/{uuid.uuid4().hex}.{ALLOWED_IMAGE_MIMES[mime]}"
    with db(serialized=True) as conn:
        row = conn.execute("SELECT revision, image_key, image_storage FROM site_banners WHERE id = ?", (banner_id,)).fetchone()
        if not row:
            raise _missing("Banner 不存在")
        try:
            storage_for(storage_name).put(key, data, mime)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(503, detail={"error": "图片存储不可用，请稍后重试"}) from exc
        conn.execute("UPDATE site_banners SET image_key = ?, image_storage = ?, image_mime = ?, image_bytes = ?, "
                     "revision = revision + 1, updated_at = ? WHERE id = ?",
                     (key, storage_name, mime, len(data), _now(), banner_id))
    _drop_image(row["image_key"], row["image_storage"])
    return _one_banner(banner_id)


def clear_banner_image(banner_id: str, revision: int) -> dict:
    with db(serialized=True) as conn:
        row = conn.execute("SELECT revision, image_key, image_storage FROM site_banners WHERE id = ?", (banner_id,)).fetchone()
        if not row:
            raise _missing("Banner 不存在")
        if row["revision"] != revision:
            raise _conflict("Banner 已被其他操作更新，请刷新后重试")
        conn.execute("UPDATE site_banners SET image_key = '', image_storage = '', image_mime = '', image_bytes = 0, "
                     "revision = revision + 1, updated_at = ? WHERE id = ?", (_now(), banner_id))
    _drop_image(row["image_key"], row["image_storage"])
    return _one_banner(banner_id)


def banner_asset(banner_id: str, require_visible: bool = True) -> dict:
    """给 asset_response 用的资产描述（小程序端需登录后才能取图）。"""
    with db() as conn:
        row = conn.execute("SELECT image_key, image_storage, image_mime, image_bytes, title FROM site_banners "
                           "WHERE id = ?" + (" AND is_visible = 1" if require_visible else ""), (banner_id,)).fetchone()
    if not row or not row["image_key"]:
        raise _missing("Banner 图片不存在")
    return {"storage": row["image_storage"], "storage_key": row["image_key"], "kind": "banner",
            "mime_type": row["image_mime"] or "image/jpeg", "byte_size": row["image_bytes"], "title": row["title"]}


# ─── 公告与弹窗 ───

def _notice_row(row) -> dict:
    item = dict(row)
    item["is_visible"] = bool(item["is_visible"])
    return item


def _notice_state(item: dict, now: int) -> str:
    if not item["is_visible"]:
        return "hidden"
    if item["starts_at"] and now < item["starts_at"]:
        return "scheduled"
    if item["ends_at"] and now > item["ends_at"]:
        return "expired"
    return "active"


def list_notices() -> dict:
    now = _now()
    with db() as conn:
        rows = conn.execute("SELECT * FROM site_notices ORDER BY created_at DESC, id DESC").fetchall()
    items = [{**_notice_row(row), "state": _notice_state(_notice_row(row), now)} for row in rows]
    return {"items": items}


def _one_notice(notice_id: str) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM site_notices WHERE id = ?", (notice_id,)).fetchone()
    if not row:
        raise _missing("公告不存在")
    item = _notice_row(row)
    return {**item, "state": _notice_state(item, _now())}


def create_notice(body: NoticeInput) -> dict:
    now = _now()
    notice_id = uuid.uuid4().hex
    with db(serialized=True) as conn:
        conn.execute(
            "INSERT INTO site_notices(id, title, body, placement, level, starts_at, ends_at, is_visible, revision, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (notice_id, _clean(body.title), body.body.strip(), body.placement, body.level,
             body.starts_at, body.ends_at, _as_int(body.is_visible), now, now),
        )
    return _one_notice(notice_id)


def update_notice(notice_id: str, body: NoticeUpdate) -> dict:
    now = _now()
    with db(serialized=True) as conn:
        row = conn.execute("SELECT revision FROM site_notices WHERE id = ?", (notice_id,)).fetchone()
        if not row:
            raise _missing("公告不存在")
        if row["revision"] != body.revision:
            raise _conflict("公告已被其他操作更新，请刷新后重试")
        conn.execute(
            "UPDATE site_notices SET title = ?, body = ?, placement = ?, level = ?, starts_at = ?, ends_at = ?, "
            "is_visible = ?, revision = revision + 1, updated_at = ? WHERE id = ?",
            (_clean(body.title), body.body.strip(), body.placement, body.level, body.starts_at, body.ends_at,
             _as_int(body.is_visible), now, notice_id),
        )
    return _one_notice(notice_id)


def delete_notice(notice_id: str, revision: int) -> None:
    with db(serialized=True) as conn:
        row = conn.execute("SELECT revision FROM site_notices WHERE id = ?", (notice_id,)).fetchone()
        if not row:
            raise _missing("公告不存在")
        if row["revision"] != revision:
            raise _conflict("公告已被其他操作更新，请刷新后重试")
        conn.execute("DELETE FROM site_notices WHERE id = ?", (notice_id,))


# ─── 协议与隐私页 ───

def list_documents() -> dict:
    with db() as conn:
        rows = conn.execute("SELECT * FROM site_documents ORDER BY key").fetchall()
    return {"items": [dict(row) for row in rows]}


def get_document(key: str) -> dict:
    if key not in DOCUMENT_KEYS:
        raise _missing("文档不存在")
    with db() as conn:
        row = conn.execute("SELECT * FROM site_documents WHERE key = ?", (key,)).fetchone()
    if not row:
        raise _missing("文档尚未初始化")
    return dict(row)


def update_document(key: str, body: DocumentUpdate) -> dict:
    if key not in DOCUMENT_KEYS:
        raise _missing("文档不存在")
    with db(serialized=True) as conn:
        row = conn.execute("SELECT revision FROM site_documents WHERE key = ?", (key,)).fetchone()
        if not row:
            raise _missing("文档尚未初始化")
        if row["revision"] != body.revision:
            raise _conflict("文档已被其他操作更新，请刷新后重试")
        conn.execute("UPDATE site_documents SET title = ?, body = ?, revision = revision + 1, updated_at = ? WHERE key = ?",
                     (_clean(body.title), body.body.strip(), _now(), key))
    return get_document(key)


# ─── 年级 / 科目字典 ───

def _dictionary_row(row) -> dict:
    item = dict(row)
    item["is_visible"] = bool(item["is_visible"])
    return item


def list_dictionary(kind: str = "") -> dict:
    where, args = "", []
    if kind:
        where, args = " WHERE kind = ?", [kind]
    with db() as conn:
        rows = conn.execute(f"SELECT * FROM site_dictionary{where} ORDER BY kind, sort_order, value", args).fetchall()
    return {"items": [_dictionary_row(row) for row in rows]}


def create_dictionary(body: DictionaryInput) -> dict:
    now = _now()
    value = _clean(body.value)
    with db(serialized=True) as conn:
        if conn.execute("SELECT 1 FROM site_dictionary WHERE kind = ? AND value = ?", (body.kind, value)).fetchone():
            raise _conflict("该取值已在字典中")
        order = body.sort_order or conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 10 FROM site_dictionary WHERE kind = ?", (body.kind,)).fetchone()[0]
        item_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO site_dictionary(id, kind, value, label, sort_order, is_visible, revision, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (item_id, body.kind, value, _clean(body.label), order, _as_int(body.is_visible), now, now),
        )
    return _one_dictionary(item_id)


def _one_dictionary(item_id: str) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM site_dictionary WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise _missing("字典条目不存在")
    return _dictionary_row(row)


def update_dictionary(item_id: str, body: DictionaryUpdate) -> dict:
    now = _now()
    value = _clean(body.value)
    with db(serialized=True) as conn:
        row = conn.execute("SELECT kind, revision FROM site_dictionary WHERE id = ?", (item_id,)).fetchone()
        if not row:
            raise _missing("字典条目不存在")
        if row["revision"] != body.revision:
            raise _conflict("字典条目已被其他操作更新，请刷新后重试")
        clash = conn.execute("SELECT id FROM site_dictionary WHERE kind = ? AND value = ? AND id <> ?",
                             (row["kind"], value, item_id)).fetchone()
        if clash:
            raise _conflict("该取值已在字典中")
        conn.execute("UPDATE site_dictionary SET value = ?, label = ?, sort_order = ?, is_visible = ?, "
                     "revision = revision + 1, updated_at = ? WHERE id = ?",
                     (value, _clean(body.label), body.sort_order, _as_int(body.is_visible), now, item_id))
    return _one_dictionary(item_id)


def delete_dictionary(item_id: str, revision: int) -> None:
    with db(serialized=True) as conn:
        row = conn.execute("SELECT revision FROM site_dictionary WHERE id = ?", (item_id,)).fetchone()
        if not row:
            raise _missing("字典条目不存在")
        if row["revision"] != revision:
            raise _conflict("字典条目已被其他操作更新，请刷新后重试")
        conn.execute("DELETE FROM site_dictionary WHERE id = ?", (item_id,))


def unlisted_dictionary() -> dict:
    """历史试卷里出现、但字典中尚未收录的年级/科目 —— 供后台一键收编。"""
    with db() as conn:
        result = {}
        for kind, column in (("grade", "grade"), ("subject", "subject")):
            listed = {row[0] for row in conn.execute("SELECT value FROM site_dictionary WHERE kind = ?", (kind,))}
            seen = {row[0] for row in conn.execute(
                f"SELECT DISTINCT {column} FROM paper_archives WHERE {column} <> ''")}
            result[kind] = sorted(seen - listed)
    return result


def adopt_dictionary(kind: str, values: list[str]) -> dict:
    with db(serialized=True) as conn:
        order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM site_dictionary WHERE kind = ?", (kind,)).fetchone()[0]
        now = _now()
        added = 0
        for value in values:
            value = _clean(value)
            if not value:
                continue
            order += 10
            added += conn.execute(
                "INSERT INTO site_dictionary(id, kind, value, label, sort_order, is_visible, revision, created_at, updated_at) "
                "VALUES (?, ?, ?, '', ?, 1, 1, ?, ?) ON CONFLICT(kind, value) DO NOTHING",
                (uuid.uuid4().hex, kind, value, order, now, now),
            ).rowcount or 0
    return {"added": added, **list_dictionary(kind)}


# ─── 小程序端公开视图 ───

def _active_notices(conn, now: int, placement: str) -> list[dict]:
    rows = conn.execute(
        "SELECT id, title, body, placement, level, starts_at, ends_at FROM site_notices "
        "WHERE is_visible = 1 AND placement = ? AND (starts_at = 0 OR starts_at <= ?) AND (ends_at = 0 OR ends_at >= ?) "
        "ORDER BY created_at DESC, id DESC", (placement, now, now)).fetchall()
    return [dict(row) for row in rows]


def home_payload() -> dict:
    """首页一次请求拿全：Banner、公告、分类、字典。"""
    now = _now()
    with db() as conn:
        banners = [dict(row) for row in conn.execute(
            "SELECT id, kicker, title, subtitle, action_label, target_type, target_value FROM site_banners "
            "WHERE is_visible = 1 ORDER BY sort_order, created_at, id")]
        for banner in banners:
            banner["image_url"] = f"/api/v1/site/banners/{banner['id']}/image"
        # 无图 Banner 交由小程序回退到本地插画，不返回坏链接
        with_image = {row[0] for row in conn.execute("SELECT id FROM site_banners WHERE image_key <> ''")}
        for banner in banners:
            if banner["id"] not in with_image:
                banner["image_url"] = None
        categories = [{"id": row["id"], "name": row["name"], "description": row["description"], "icon": row["icon"]}
                      for row in conn.execute("SELECT id, name, description, icon FROM site_categories "
                                              "WHERE is_visible = 1 ORDER BY sort_order, name")]
        grades = [row["value"] for row in conn.execute(
            "SELECT value FROM site_dictionary WHERE kind = 'grade' AND is_visible = 1 ORDER BY sort_order, value")]
        subjects = [row["value"] for row in conn.execute(
            "SELECT value FROM site_dictionary WHERE kind = 'subject' AND is_visible = 1 ORDER BY sort_order, value")]
        popups = _active_notices(conn, now, "popup")
        strips = _active_notices(conn, now, "banner")
    return {
        "banners": banners,
        "notices": {"popup": popups, "banner": strips},
        "categories": categories,
        "dictionaries": {"grades": grades, "subjects": subjects},
    }


# ─── 内容数据看板 ───

def _category_analytics(conn) -> list[dict]:
    """按分类汇总已发布习题数与互动量。

    刻意拆成三条独立聚合再在 Python 里合并：带关联子查询的写法在 PostgreSQL 上
    会因「子查询引用了外层未分组列」直接报 GroupingError；而多表 JOIN 一次算完
    又会出现行乘积（收藏数被下载数放大）。看板数据量小，分开算最稳。
    """
    def group_by_category(source: str, from_clause: str) -> dict:
        rows = conn.execute(
            f"SELECT COALESCE(NULLIF({source}, ''), '未分类') AS name, COUNT(*) AS total FROM {from_clause} "
            f"GROUP BY COALESCE(NULLIF({source}, ''), '未分类')")
        return {row["name"]: row["total"] for row in rows}

    papers = group_by_category("category", "catalog_papers WHERE status = 'published'")
    activity = {}
    for table in ("mini_catalog_favorites", "mini_catalog_downloads"):
        activity[table] = group_by_category(
            "p.category", f"{table} x JOIN catalog_papers p ON p.id = x.catalog_id WHERE p.status = 'published'")
    return [{"name": name, "papers": total,
             "favorites": activity["mini_catalog_favorites"].get(name, 0),
             "downloads": activity["mini_catalog_downloads"].get(name, 0)}
            for name, total in sorted(papers.items(), key=lambda item: (-item[1], item[0]))]


def admin_analytics() -> dict:
    now = _now()
    day = 86400
    with db() as conn:
        statuses = {row["status"]: row["count"] for row in conn.execute(
            "SELECT status, COUNT(*) AS count FROM catalog_papers GROUP BY status")}
        favorites = conn.execute("SELECT COUNT(*) FROM mini_catalog_favorites").fetchone()[0]
        downloads = conn.execute("SELECT COUNT(*) FROM mini_catalog_downloads").fetchone()[0]
        top_favorites = [dict(row) for row in conn.execute(
            "SELECT c.id, c.title, c.category, COUNT(f.user_id) AS total FROM catalog_papers c "
            "LEFT JOIN mini_catalog_favorites f ON f.catalog_id = c.id WHERE c.status = 'published' "
            "GROUP BY c.id, c.title, c.category ORDER BY total DESC, c.published_at DESC, c.id LIMIT 10")]
        top_downloads = [dict(row) for row in conn.execute(
            "SELECT c.id, c.title, c.category, COUNT(d.user_id) AS total FROM catalog_papers c "
            "LEFT JOIN mini_catalog_downloads d ON d.catalog_id = c.id WHERE c.status = 'published' "
            "GROUP BY c.id, c.title, c.category ORDER BY total DESC, c.published_at DESC, c.id LIMIT 10")]
        by_category = _category_analytics(conn)
        users = conn.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active, "
            "SUM(CASE WHEN membership = 'vip' THEN 1 ELSE 0 END) AS vip, "
            "SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS new_7d, "
            "SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS new_30d FROM mini_users", (now - 7 * day, now - 30 * day)
        ).fetchone()
        daily = [dict(row) for row in conn.execute(
            "SELECT CAST(created_at / 86400 AS INTEGER) AS day_stamp, COUNT(*) AS total FROM mini_users "
            "WHERE created_at >= ? GROUP BY CAST(created_at / 86400 AS INTEGER) ORDER BY day_stamp", (now - 14 * day,))]
        idle = [dict(row) for row in conn.execute(
            "SELECT c.id, c.title, c.category, c.published_at FROM catalog_papers c WHERE c.status = 'published' "
            "AND NOT EXISTS (SELECT 1 FROM mini_catalog_favorites f WHERE f.catalog_id = c.id) "
            "AND NOT EXISTS (SELECT 1 FROM mini_catalog_downloads d WHERE d.catalog_id = c.id) "
            "ORDER BY c.published_at DESC, c.id LIMIT 10")]
        no_category = conn.execute("SELECT COUNT(*) FROM catalog_papers WHERE category_id = ''").fetchone()[0]
    by_day = {row["day_stamp"] * day: row["total"] for row in daily}
    timeline = []
    for offset in range(13, -1, -1):
        stamp = (now // day - offset) * day
        timeline.append({"date": time.strftime("%m-%d", time.localtime(stamp)), "total": by_day.get(stamp, 0)})
    return {
        "papers": {"total": sum(statuses.values()), **{key: statuses.get(key, 0) for key in ("draft", "published", "withdrawn")}},
        "engagement": {"favorites": favorites, "downloads": downloads},
        "top_favorites": top_favorites,
        "top_downloads": top_downloads,
        "by_category": by_category,
        "users": {key: int(users[key] or 0) for key in ("total", "active", "vip", "new_7d", "new_30d")},
        "new_users_timeline": timeline,
        "idle_papers": idle,
        "papers_without_category": no_category,
    }
