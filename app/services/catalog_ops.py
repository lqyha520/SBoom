"""Atomic publishing, immutable releases, role previews and ordered collections."""

import time
import uuid
from types import SimpleNamespace

from app.db import db
from app.mini_schema import index_question_types
from app.services import catalog_access, public_catalog as catalog
from app.services.mini_experience import fail
from app.services.mini_messages import notify
from app.services import catalog_editions


def batch(body):
    with db(serialized=True) as conn:
        category = None
        tag_kinds = {}
        if body.action == "category":
            category = conn.execute("SELECT id, name FROM site_categories WHERE id = ?", (body.category_id,)).fetchone()
            if not category:
                fail("所选分类不存在", 404)
        elif body.action == "tags":
            for identifier in body.tag_ids:
                tag = conn.execute("SELECT kind FROM catalog_tags WHERE id = ?", (identifier,)).fetchone()
                if not tag:
                    fail("所选标签已删除，请刷新", 404)
                tag_kinds[identifier] = tag[0]
            for kind in ("textbook", "term", "unit"):
                if sum(1 for kind_ in tag_kinds.values() if kind_ == kind) > 1:
                    fail("教材、学期、单元各只能设置一个", 422)
        rows = []
        for item in body.items:
            row = conn.execute(f"SELECT c.*, a.file_status FROM {catalog.JOIN} WHERE c.id = ?", (item.id,)).fetchone()
            if not row:
                fail("所选资料不存在，请刷新列表", 404)
            if row["revision"] != item.revision:
                fail("部分资料已被其他操作更新，本次未作修改，请刷新后重试")
            if body.action == "published" and row["file_status"] != "ready":
                fail("所选资料中仍有文件未就绪，本次未作修改")
            rows.append(row)
        now = int(time.time())
        for row in rows:
            if category:
                conn.execute("UPDATE catalog_papers SET category_id = ?, category = ? WHERE id = ?", (category["id"], category["name"], row["id"]))
            elif body.action in ("published", "withdrawn"):
                published_at = now if body.action == "published" and row["status"] != "published" else row["published_at"]
                conn.execute("UPDATE catalog_papers SET status = ?, published_at = ? WHERE id = ?", (body.action, published_at, row["id"]))
            elif body.action == "access":
                catalog_access.save_policy(conn, row["id"], body)
            elif body.action == "tags":
                # 合并语义：教材/学期/单元按类型覆盖，知识点追加去重，其余保留
                merged: dict[str, list[str]] = {}
                for item in conn.execute("SELECT p.tag_id, t.kind FROM catalog_paper_tags p JOIN catalog_tags t ON t.id = p.tag_id WHERE p.catalog_id = ?", (row["id"],)).fetchall():
                    merged.setdefault(item["kind"], []).append(item["tag_id"])
                for identifier, kind in tag_kinds.items():
                    if kind == "knowledge":
                        if identifier not in merged.setdefault("knowledge", []):
                            merged["knowledge"].append(identifier)
                    else:
                        merged[kind] = [identifier]
                if len(merged.get("knowledge", [])) > 20:
                    fail("「" + row["title"] + "」合并后知识点将超过 20 个，本次未作修改", 422)
                conn.execute("DELETE FROM catalog_paper_tags WHERE catalog_id = ?", (row["id"],))
                for identifiers in merged.values():
                    for identifier in identifiers:
                        conn.execute("INSERT INTO catalog_paper_tags(catalog_id, tag_id) VALUES (?, ?)", (row["id"], identifier))
            conn.execute("UPDATE catalog_papers SET revision = revision + 1, updated_at = ? WHERE id = ?", (now, row["id"]))
    return {"updated": len(rows)}


def preview(admin_id, catalog_id, membership):
    result = catalog.get_paper(admin_id, catalog_id, admin=True)
    with db() as conn:
        access = catalog_access.access_map(conn, [catalog_id], SimpleNamespace(is_vip=membership == "vip"))[catalog_id]
    result.update(access)
    result["preview_membership"] = membership
    if not access["can_view"]:
        result["snapshot"] = None
        result["thumbnail_id"] = None
        result["thumbnail_url"] = None
    result["assets"] = [item for item in result["assets"] if access["can_download" if item["kind"] == "pdf" else "can_view"]]
    for edition in result.get("editions", []):
        edition.pop("paper_id", None)
        if not access["can_download"]:
            edition.pop("url", None)
    return result


def revise(admin_id, catalog_id, body):
    now = int(time.time())
    with db(serialized=True) as conn:
        row = conn.execute("SELECT * FROM catalog_papers WHERE id = ?", (catalog_id,)).fetchone()
        if not row:
            fail("公共资料不存在", 404)
        if row["revision"] != body.revision:
            fail("条目已更新，请刷新后重试")
        if row["status"] == "published" and not body.confirm_publication:
            fail("请确认修订稿内容及权限后更新已发布资料", 422)
        source = conn.execute("SELECT * FROM paper_archives WHERE id = ? AND user_id = ?", (body.paper_id, admin_id)).fetchone()
        if not source:
            fail("只能选择自己保存的修订稿", 404)
        if source["file_status"] != "ready":
            fail("修订稿的 PDF 与预览图尚未完成")
        if row["paper_id"] == body.paper_id or conn.execute("SELECT 1 FROM catalog_papers WHERE paper_id = ?", (body.paper_id,)).fetchone():
            fail("这个原稿版本已在公共库中使用，请选择新的归档")
        if conn.execute("SELECT 1 FROM catalog_versions WHERE paper_id = ?", (body.paper_id,)).fetchone():
            fail("该原稿已属于修订历史，请另存新的归档版本")
        if catalog_editions.referenced(conn, body.paper_id):
            fail("该原稿已作为打印版本使用，请另存新的修订稿")
        conn.execute("INSERT INTO catalog_versions(id, catalog_id, paper_id, release_number, note, created_at) "
                     "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(catalog_id, release_number) DO NOTHING",
                     (uuid.uuid4().hex, catalog_id, row["paper_id"], row["release_number"], row["update_note"], row["published_at"] or row["created_at"]))
        release = row["release_number"] + 1
        conn.execute("INSERT INTO catalog_versions(id, catalog_id, paper_id, release_number, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                     (uuid.uuid4().hex, catalog_id, body.paper_id, release, body.note, now))
        conn.execute("UPDATE catalog_papers SET paper_id = ?, release_number = ?, update_note = ?, revision = revision + 1, "
                     "updated_at = ? WHERE id = ?", (body.paper_id, release, body.note, now, catalog_id))
        conn.execute("DELETE FROM catalog_question_types WHERE catalog_id = ?", (catalog_id,))
        index_question_types(conn, catalog_id, source["snapshot_json"])
        conn.execute("DELETE FROM catalog_print_editions WHERE catalog_id = ?", (catalog_id,))
        if row["status"] == "published":
            recipients = conn.execute("SELECT user_id FROM mini_catalog_favorites WHERE catalog_id = ?", (catalog_id,)).fetchall()
            for recipient in recipients:
                notify(conn, recipient[0], f"paper:{catalog_id}:{release}", "paper", "收藏的资料有更新", row["title"] + "：" + body.note, "paper", catalog_id)
    return catalog.get_paper(admin_id, catalog_id, admin=True)


def topics(admin=False):
    with db() as conn:
        rows = conn.execute("SELECT * FROM site_topics" + ("" if admin else " WHERE is_visible = 1") + " ORDER BY sort_order, created_at DESC, id").fetchall()
        result = []
        for row in rows:
            items = conn.execute("SELECT i.catalog_id, c.title, c.status, a.file_status FROM site_topic_items i "
                                 "JOIN catalog_papers c ON c.id = i.catalog_id JOIN paper_archives a ON a.id = c.paper_id WHERE i.topic_id = ? "
                                 + ("" if admin else f"AND {catalog.VISIBLE} ") + "ORDER BY i.sort_order, i.catalog_id", (row["id"],)).fetchall()
            result.append({**dict(row), "is_visible": bool(row["is_visible"]), "paper_count": len(items),
                           "paper_ids": [item["catalog_id"] for item in items], "papers": [dict(item) for item in items]})
    return {"items": result}


def save_topic(body, identifier=None):
    now = int(time.time())
    with db(serialized=True) as conn:
        if identifier:
            row = conn.execute("SELECT revision FROM site_topics WHERE id = ?", (identifier,)).fetchone()
            if not row:
                fail("专题不存在", 404)
            if row[0] != body.revision:
                fail("专题已更新，请刷新后重试")
        else:
            if conn.execute("SELECT COUNT(*) FROM site_topics").fetchone()[0] >= 200:
                fail("专题数量已达 200，请先整理旧专题", 422)
        for paper_id in body.paper_ids:
            if not conn.execute("SELECT 1 FROM catalog_papers WHERE id = ?", (paper_id,)).fetchone():
                fail("专题中有资料已删除，请刷新资料列表", 404)
        if not identifier:
            identifier = uuid.uuid4().hex
            conn.execute("INSERT INTO site_topics(id, title, description, is_visible, sort_order, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (identifier, body.title, body.description, int(body.is_visible), body.sort_order, now, now))
        else:
            conn.execute("UPDATE site_topics SET title = ?, description = ?, is_visible = ?, sort_order = ?, revision = revision + 1, updated_at = ? WHERE id = ?",
                         (body.title, body.description, int(body.is_visible), body.sort_order, now, identifier))
        conn.execute("DELETE FROM site_topic_items WHERE topic_id = ?", (identifier,))
        for index, paper_id in enumerate(body.paper_ids):
            conn.execute("INSERT INTO site_topic_items(topic_id, catalog_id, sort_order) VALUES (?, ?, ?)", (identifier, paper_id, index))
        return dict(conn.execute("SELECT * FROM site_topics WHERE id = ?", (identifier,)).fetchone())


def delete_topic(identifier, revision):
    with db(serialized=True) as conn:
        row = conn.execute("SELECT revision FROM site_topics WHERE id = ?", (identifier,)).fetchone()
        if not row:
            fail("专题不存在", 404)
        if row[0] != revision:
            fail("专题已更新，请刷新")
        conn.execute("DELETE FROM site_topics WHERE id = ?", (identifier,))
