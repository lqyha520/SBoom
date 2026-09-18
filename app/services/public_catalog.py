"""Published exercise metadata and membership-gated content for consumer accounts."""

import json
import time
import uuid

from fastapi import HTTPException

from app.db import db
from app.models.catalog import CatalogCreate, CatalogUpdate
from app.mini_schema import index_question_types
from app.services import catalog_access, mini_auth
from app.services import catalog_discovery, catalog_editions, catalog_delivery

COLUMNS = """c.id, c.title, c.description, c.category, c.category_id, c.status, c.featured, c.revision, c.release_number, c.update_note,
    c.download_mode, c.external_url, c.external_code,
    c.created_at, c.updated_at, c.published_at, a.grade, a.subject, a.keyword,
    a.question_count, a.version, a.page_count, a.file_status, a.file_error,
    (SELECT id FROM paper_assets WHERE paper_id = a.id AND kind = 'page' AND page_number = 1) AS thumbnail_id"""
JOIN = "catalog_papers c JOIN paper_archives a ON a.id = c.paper_id"
VISIBLE = "c.status = 'published' AND " + catalog_delivery.availability_sql()
QUESTION_FIELDS = {"id", "type", "stem", "_stemHtml", "_optsHtml", "options", "answer", "analysis",
                   "acceptable_answers", "left_items", "right_items", "left_expr", "right_expr", "top", "left", "right"}


def _missing():
    raise HTTPException(404, detail={"error": "试卷未发布、已下架或不存在"})


def _match(value):
    return "%" + value.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _resolve_category(conn, body, previous=None) -> tuple[str, str]:
    """把发布表单的分类选择收敛成 (category_id, 分类名)。

    分类名冗余存在 catalog_papers 上：列表筛选、关键词搜索都直接命中该列，
    无需 JOIN；改名由 site_content.update_category 统一同步。
    """
    category_id = (body.category_id or "").strip()
    if category_id:
        row = conn.execute("SELECT id, name FROM site_categories WHERE id = ?", (category_id,)).fetchone()
        if not row:
            raise HTTPException(404, detail={"error": "所选分类不存在，请刷新分类列表"})
        return row["id"], row["name"]
    name = (body.category or "").strip()
    if name:
        row = conn.execute("SELECT id FROM site_categories WHERE name = ?", (name,)).fetchone()
        return (row["id"] if row else ""), name
    if previous is not None:
        return previous["category_id"], previous["category"]
    return "", ""


def _order_by_dictionary(conn, kind, values) -> list[str]:
    """按后台字典顺序排列（未收录的值排在最后，再按字面量兜底）。"""
    rank = {row["value"]: row["sort_order"] for row in conn.execute(
        "SELECT value, sort_order FROM site_dictionary WHERE kind = ? AND is_visible = 1", (kind,))}
    return sorted(values, key=lambda value: (rank.get(value, 10 ** 6), value))


def _item(row, admin=False, access=None):
    item = dict(row)
    item["favorite"] = bool(item.get("favorite", False))
    item["featured"] = bool(item["featured"])
    item.update(scope="catalog", source_id="", folder_id=None, folder_name=None,
                group_id="", group_name=item["category"])
    prefix = "/api/v1/admin/catalog" if admin else "/api/v1/catalog"
    item["thumbnail_url"] = (f"{prefix}/papers/{item['id']}/assets/{item['thumbnail_id']}"
                             if item["thumbnail_id"] else None)
    if not admin:
        item["created_at"] = item["published_at"]
        # 网盘模式：有下载权限的用户需要链接信息，PDF模式才移除
        if item["download_mode"] != "external":
            item.pop("external_url", None)
            item.pop("external_code", None)
    if access:
        item.update(access)
        if not item["can_view"]:
            item["thumbnail_url"] = None
            item["thumbnail_id"] = None
    return item


def _visible(conn, catalog_id):
    row = conn.execute(f"SELECT c.*, a.file_status FROM {JOIN} WHERE c.id = ? AND {VISIBLE}", (catalog_id,)).fetchone()
    if not row:
        _missing()
    return row


def _snapshot(raw, title):
    source = json.loads(raw)
    original = source["paper"]
    paper = {key: original[key] for key in ("grade", "subject", "keyword", "difficulty")}
    paper["title"] = title
    paper["sections"] = []
    for section in original["sections"]:
        data = {"questions": [{key: value for key, value in question.items() if key in QUESTION_FIELDS}
                               for question in section["data"]["questions"]]}
        if "passage" in section["data"]:
            data["passage"] = section["data"]["passage"]
        paper["sections"].append({"type": section["type"], "name": section.get("name"), "layout": {}, "data": data})
    # Export settings, private folder/group names and arbitrary snapshot extensions are not public metadata.
    return {"schema_version": 1, "paper": paper, "template": {}, "style": {}, "export_options": source["export_options"]}


def list_papers(user_id, q="", grade="", subject="", category="", favorite=False, downloaded=False,
                limit=20, offset=0, admin=False, status="", sort="featured", only_free=False, recent=False, favorite_group="", topic="", textbook="", term="", unit="", knowledge=""):
    if not admin and user_id is None and (favorite or downloaded or recent or favorite_group):
        raise HTTPException(401, detail={"error": "请先登录后查看个人记录", "code": "login_required"})
    clauses, args = ([] if admin else [VISIBLE]), []
    for kind, tag_id in (("textbook", textbook), ("term", term), ("unit", unit), ("knowledge", knowledge)):
        if tag_id:
            clauses.append("EXISTS (SELECT 1 FROM catalog_paper_tags pt JOIN catalog_tags t ON t.id = pt.tag_id WHERE pt.catalog_id = c.id AND t.id = ? AND t.kind = ? AND t.is_visible = 1)")
            args.extend([tag_id, kind])
    if q.strip():
        clauses.append("(LOWER(c.title) LIKE ? ESCAPE '\\' OR LOWER(a.keyword) LIKE ? ESCAPE '\\' "
                       "OR LOWER(c.category) LIKE ? ESCAPE '\\')")
        args.extend([_match(q)] * 3)
    for field, value in (("a.grade", grade), ("a.subject", subject)):
        if value:
            clauses.append(f"{field} = ?")
            args.append(value)
    if category:
        # 分类参数可能是分类 id（新）也可能是历史分类名（旧链接/旧缓存）
        clauses.append("(c.category_id = ? OR c.category = ?)")
        args.extend([category, category])
    if admin and status:
        clauses.append("c.status = ?")
        args.append(status)
    if only_free:
        for action in ("view", "download"):
            policy = f"COALESCE((SELECT p.{action}_access FROM catalog_access p WHERE p.catalog_id = c.id), 'inherit')"
            clauses.append(f"({policy} = 'free' OR ({policy} = 'inherit' AND NOT EXISTS (SELECT 1 FROM catalog_question_types t "
                           f"JOIN catalog_type_rules r ON r.question_type = t.question_type WHERE t.catalog_id = c.id AND r.{action}_access = 'vip')))")
    if recent:
        clauses.append("EXISTS (SELECT 1 FROM mini_recent_views WHERE catalog_id = c.id AND user_id = ?)")
        args.append(user_id)
    if favorite_group:
        clauses.append("EXISTS (SELECT 1 FROM mini_favorite_group_items WHERE catalog_id = c.id AND user_id = ? AND group_id = ?)")
        args.extend([user_id, favorite_group])
    if topic:
        clauses.append("EXISTS (SELECT 1 FROM site_topic_items i JOIN site_topics t ON t.id = i.topic_id "
                       "WHERE i.catalog_id = c.id AND t.id = ? AND t.is_visible = 1)")
        args.append(topic)
    for enabled, table in ((favorite, "mini_catalog_favorites"), (downloaded, "mini_catalog_downloads")):
        if enabled:
            clauses.append(f"EXISTS (SELECT 1 FROM {table} WHERE catalog_id = c.id AND user_id = ?)")
            args.append(user_id)
    where = " AND ".join(clauses) or "1 = 1"
    fields = (", (SELECT COUNT(*) FROM mini_catalog_favorites WHERE catalog_id = c.id) AS favorite_count, "
              "(SELECT COUNT(*) FROM mini_catalog_downloads WHERE catalog_id = c.id) AS download_users" if admin else "")
    activity_table = "mini_recent_views" if recent else "mini_catalog_downloads" if downloaded else "mini_catalog_favorites" if favorite else ""
    activity_params = []
    order = "c.featured DESC, c.published_at DESC, c.created_at DESC, c.id DESC"
    if sort == "latest":
        order = "c.published_at DESC, c.created_at DESC, c.id DESC"
    elif sort == "popular":
        order = "((SELECT COUNT(*) FROM mini_catalog_favorites WHERE catalog_id = c.id) + (SELECT COUNT(*) FROM mini_catalog_downloads WHERE catalog_id = c.id)) DESC, c.published_at DESC, c.id DESC"
    if topic:
        # Validated IDs are still bound parameters, never SQL fragments.
        fields += ", (SELECT sort_order FROM site_topic_items WHERE topic_id = ? AND catalog_id = c.id) AS topic_order"
        activity_params.append(topic)
        order = "topic_order, c.id"
    if activity_table:
        stamp = "viewed_at" if recent else "requested_at" if downloaded else "created_at"
        fields += f", (SELECT {stamp} FROM {activity_table} WHERE catalog_id = c.id AND user_id = ?) AS activity_at"
        activity_params.append(user_id)
        order = "activity_at DESC, c.id DESC"
    with db() as conn:
        user = None if admin or user_id is None else mini_auth._user(conn, user_id)
        total = conn.execute(f"SELECT COUNT(*) FROM {JOIN} WHERE {where}", args).fetchone()[0]
        rows = conn.execute(f"SELECT {COLUMNS}, EXISTS (SELECT 1 FROM mini_catalog_favorites WHERE catalog_id = c.id "
                            f"AND user_id = ?) AS favorite {fields} FROM {JOIN} WHERE {where} "
                            f"ORDER BY {order} LIMIT ? OFFSET ?",
                            [str(user_id) if user_id is not None else None, *activity_params, *args, limit, offset]).fetchall()
        access = catalog_access.access_map(conn, [row["id"] for row in rows], user, admin)
        labels = catalog_discovery.label_map(conn, [row["id"] for row in rows], admin)
    return {"items": [{**_item(row, admin, access[row["id"]]), "tags": labels[row["id"]]} for row in rows], "total": total, "has_more": offset + len(rows) < total}


def get_paper(user_id, catalog_id, admin=False):
    with db() as conn:
        user = None if admin or user_id is None else mini_auth._user(conn, user_id)
        row = conn.execute(f"SELECT {COLUMNS}, a.snapshot_json, a.id AS archive_id, "
                           "EXISTS (SELECT 1 FROM mini_catalog_favorites WHERE catalog_id = c.id AND user_id = ?) AS favorite "
                           f"FROM {JOIN} WHERE c.id = ?" + ("" if admin else f" AND {VISIBLE}"), (str(user_id) if user_id is not None else None, catalog_id)).fetchone()
        if not row:
            _missing()
        access = catalog_access.access_map(conn, [catalog_id], user, admin)[catalog_id]
        result = _item(row, admin, access)
        raw = result.pop("snapshot_json")
        result["snapshot"] = _snapshot(raw, result["title"]) if access["can_view"] else None
        prefix = "/api/v1/admin/catalog" if admin else "/api/v1/catalog"
        rows = conn.execute("SELECT id, kind, page_number, mime_type, byte_size FROM paper_assets WHERE paper_id = ? "
                            "ORDER BY page_number", (result.pop("archive_id"),)).fetchall()
        result["assets"] = [{**dict(asset), "url": f"{prefix}/papers/{catalog_id}/assets/{asset['id']}"} for asset in rows
                            if access["can_download" if asset["kind"] == "pdf" else "can_view"]
                            and (admin or asset["kind"] != "pdf" or result["download_mode"] == "pdf")]
        result["versions"] = [dict(row) for row in conn.execute(
            "SELECT release_number, note, created_at FROM catalog_versions WHERE catalog_id = ? ORDER BY release_number DESC", (catalog_id,))]
        result["tags"] = catalog_discovery.label_map(conn, [catalog_id], admin)[catalog_id]
        result["editions"] = catalog_editions.listing(conn, catalog_id, admin, access["can_download"]) if admin or result["download_mode"] == "pdf" else []
    return result


def get_asset(catalog_id, asset_id, admin=False, user_id=None):
    with db() as conn:
        row = conn.execute(f"SELECT s.*, c.title, c.download_mode FROM {JOIN} JOIN paper_assets s ON (s.paper_id = a.id OR "
                           "(s.kind = 'pdf' AND EXISTS (SELECT 1 FROM catalog_print_editions e JOIN paper_archives p ON p.id = e.paper_id WHERE e.catalog_id = c.id AND e.paper_id = s.paper_id AND p.file_status = 'ready'))) "
                           "WHERE c.id = ? AND s.id = ? AND a.file_status = 'ready'" +
                           ("" if admin else " AND c.status = 'published'"), (catalog_id, asset_id)).fetchone()
        if not row:
            _missing()
        if not admin and row["kind"] == "pdf" and row["download_mode"] != "pdf":
            _missing()
        if not admin and user_id is None and row["kind"] == "pdf":
            raise HTTPException(401, detail={"error": "请先登录后下载", "code": "login_required"})
        user = None if admin or user_id is None else mini_auth._user(conn, user_id)
        access = catalog_access.access_map(conn, [catalog_id], user, admin)[catalog_id]
        catalog_access.require_access(access, "download" if row["kind"] == "pdf" else "view")
        return dict(row)


def favorite_paper(user_id, catalog_id, favorite):
    with db(serialized=True) as conn:
        _visible(conn, catalog_id)
        if favorite:
            conn.execute("INSERT INTO mini_catalog_favorites(user_id, catalog_id, created_at) VALUES (?, ?, ?) "
                         "ON CONFLICT(user_id, catalog_id) DO NOTHING", (user_id, catalog_id, int(time.time())))
        else:
            conn.execute("DELETE FROM mini_catalog_favorites WHERE user_id = ? AND catalog_id = ?", (user_id, catalog_id))
    return {"favorite": favorite}


def request_download(user_id, catalog_id, edition="original"):
    with db(serialized=("content", "accounts")) as conn:
        row = _visible(conn, catalog_id)
        user = mini_auth._user(conn, user_id)
        catalog_access.require_access(catalog_access.access_map(conn, [catalog_id], user)[catalog_id], "download")
        if row["download_mode"] == "external":
            result = {"kind": "external", "url": row["external_url"], "extraction_code": row["external_code"]}
        else:
            paper_id = catalog_editions.source_id(conn, catalog_id, row["paper_id"], edition)
            asset = conn.execute("SELECT id, kind, page_number, mime_type, byte_size FROM paper_assets WHERE paper_id = ? AND kind = 'pdf'",
                                 (paper_id,)).fetchone()
            if not asset:
                _missing()
            result = {**dict(asset), "url": f"/api/v1/catalog/papers/{catalog_id}/assets/{asset['id']}"}
        conn.execute("INSERT INTO mini_catalog_downloads(user_id, catalog_id, requested_at) VALUES (?, ?, ?) "
                     "ON CONFLICT(user_id, catalog_id) DO UPDATE SET requested_at = excluded.requested_at",
                     (user_id, catalog_id, int(time.time())))
        return result


def summary(user_id):
    """小程序首页/筛选器所需的聚合：数量、可筛年级与科目、可筛分类（后台配置）。"""
    with db() as conn:
        count = conn.execute(f"SELECT COUNT(*) FROM {JOIN} WHERE {VISIBLE}").fetchone()[0]
        distinct = {key: [row[0] for row in conn.execute(
            f"SELECT DISTINCT {field} FROM {JOIN} WHERE {VISIBLE} AND {field} <> ''")]
            for key, field in (("grades", "a.grade"), ("subjects", "a.subject"))}
        categories = [{"id": row["id"], "name": row["name"], "description": row["description"], "icon": row["icon"],
                       "paper_count": row["total"]} for row in conn.execute(
            "SELECT c.id, c.name, c.description, c.icon, COUNT(p.id) AS total FROM site_categories c "
            "JOIN catalog_papers p ON p.category_id = c.id JOIN paper_archives a ON a.id = p.paper_id "
            f"WHERE c.is_visible = 1 AND p.status = 'published' AND {catalog_delivery.availability_sql('p')} "
            "GROUP BY c.id, c.name, c.description, c.icon ORDER BY c.sort_order, c.name")]
        result = {
            "papers": count,
            "grades": _order_by_dictionary(conn, "grade", distinct["grades"]),
            "subjects": _order_by_dictionary(conn, "subject", distinct["subjects"]),
            "categories": categories,
        }
        for key, table in (("favorites", "mini_catalog_favorites"), ("downloads", "mini_catalog_downloads")):
            result[key] = conn.execute(f"SELECT COUNT(*) FROM {table} x JOIN catalog_papers c ON c.id = x.catalog_id "
                                       f"JOIN paper_archives a ON a.id = c.paper_id WHERE x.user_id = ? AND {VISIBLE}", (user_id,)).fetchone()[0]
    return result


def admin_summary():
    with db() as conn:
        statuses = {row["status"]: row["count"] for row in conn.execute("SELECT status, COUNT(*) AS count FROM catalog_papers GROUP BY status")}
        return {"total": sum(statuses.values()), **{status: statuses.get(status, 0) for status in ("draft", "published", "withdrawn")},
                "favorites": conn.execute("SELECT COUNT(*) FROM mini_catalog_favorites").fetchone()[0],
                "downloads": conn.execute("SELECT COUNT(*) FROM mini_catalog_downloads").fetchone()[0]}


def list_sources(user_id, q="", limit=20, offset=0):
    where = "a.user_id = ? AND NOT EXISTS (SELECT 1 FROM catalog_papers WHERE paper_id = a.id) AND NOT EXISTS (SELECT 1 FROM catalog_versions WHERE paper_id = a.id)"
    where += " AND NOT EXISTS (SELECT 1 FROM catalog_edition_history WHERE paper_id = a.id)"
    args = [user_id]
    if q.strip():
        where += " AND (LOWER(a.title) LIKE ? ESCAPE '\\' OR LOWER(a.keyword) LIKE ? ESCAPE '\\')"
        args.extend([_match(q)] * 2)
    with db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM paper_archives a WHERE {where}", args).fetchone()[0]
        rows = conn.execute("SELECT a.id, a.title, a.grade, a.subject, a.file_status, a.version, a.question_count "
                            f"FROM paper_archives a WHERE {where} ORDER BY a.created_at DESC, a.id DESC LIMIT ? OFFSET ?",
                            [*args, limit, offset]).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "has_more": offset + len(rows) < total}


def create_paper(user_id, body: CatalogCreate):
    now, catalog_id = int(time.time()), uuid.uuid4().hex
    with db(serialized=True) as conn:
        delivery = catalog_delivery.settings(body)
        paper_id = body.paper_id or catalog_delivery.metadata_archive(conn, user_id, body)
        paper = conn.execute("SELECT title, snapshot_json FROM paper_archives WHERE id = ? AND user_id = ?", (paper_id, user_id)).fetchone()
        if not paper:
            raise HTTPException(404, detail={"error": "只能选择当前管理员自己保存的试卷"})
        if conn.execute("SELECT id FROM catalog_papers WHERE paper_id = ?", (paper_id,)).fetchone():
            raise HTTPException(409, detail={"error": "该版本已加入公共库，请编辑已有条目"})
        if conn.execute("SELECT 1 FROM catalog_versions WHERE paper_id = ?", (paper_id,)).fetchone():
            raise HTTPException(409, detail={"error": "该原稿属于修订历史，请另存新的归档版本"})
        if catalog_editions.referenced(conn, paper_id):
            raise HTTPException(409, detail={"error": "该原稿属于公共资料的打印版本，请另存新的归档"})
        category_id, category_name = _resolve_category(conn, body)
        conn.execute("INSERT INTO catalog_papers(id, paper_id, publisher_id, title, description, category, category_id, created_at, updated_at, download_mode, external_url, external_code) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (catalog_id, paper_id, user_id, body.title.strip() or paper["title"], body.description.strip(),
                      category_name, category_id, now, now, delivery["download_mode"], delivery["external_url"], delivery["external_code"]))
        index_question_types(conn, catalog_id, paper["snapshot_json"])
        catalog_access.save_policy(conn, catalog_id, body)
    return get_paper(user_id, catalog_id, admin=True)


def update_paper(user_id, catalog_id, body: CatalogUpdate):
    with db(serialized=True) as conn:
        row = conn.execute(f"SELECT c.*, a.file_status FROM {JOIN} WHERE c.id = ?", (catalog_id,)).fetchone()
        if not row:
            _missing()
        if row["revision"] != body.revision:
            raise HTTPException(409, detail={"error": "条目已被其他操作更新，请刷新后重试"})
        delivery = catalog_delivery.settings(body, row)
        if delivery["download_mode"] == "pdf" and row["download_mode"] == "external" and row["file_status"] != "ready":
            raise HTTPException(409, detail={"error": "尚无 PDF 文件，请先通过修订原稿关联已就绪的 PDF，再切换下载方式"})
        if body.status == "published":
            if delivery["download_mode"] == "pdf" and row["file_status"] != "ready":
                raise HTTPException(409, detail={"error": "PDF 与预览图尚未完成，请先在工作台补齐文件"})
            if row["status"] != "published" and not body.confirm_publication:
                raise HTTPException(422, detail={"error": "请确认习题、答案和文件可按所设权限提供给小程序用户"})
        published_at = int(time.time()) if body.status == "published" and row["status"] != "published" else row["published_at"]
        category_id, category_name = _resolve_category(conn, body, previous=row)
        conn.execute("UPDATE catalog_papers SET title = ?, description = ?, category = ?, category_id = ?, status = ?, featured = ?, "
                     "revision = revision + 1, published_at = ?, updated_at = ?, download_mode = ?, external_url = ?, external_code = ? WHERE id = ?",
                     (body.title, body.description.strip(), category_name, category_id, body.status, int(body.featured),
                      published_at, int(time.time()), delivery["download_mode"], delivery["external_url"], delivery["external_code"], catalog_id))
        catalog_access.save_policy(conn, catalog_id, body, preserve_missing=True)
    return get_paper(user_id, catalog_id, admin=True)


def delete_paper(catalog_id, revision):
    with db(serialized=True) as conn:
        row = conn.execute("SELECT revision FROM catalog_papers WHERE id = ?", (catalog_id,)).fetchone()
        if not row:
            _missing()
        if row["revision"] != revision:
            raise HTTPException(409, detail={"error": "条目已被其他操作更新，请刷新后重试"})
        conn.execute("DELETE FROM catalog_papers WHERE id = ?", (catalog_id,))
