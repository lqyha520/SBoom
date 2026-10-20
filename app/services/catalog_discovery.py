"""Operator-controlled curriculum tags and combined catalog filters."""

import uuid

from app.db import db
from app.public_cache import cached_public
from app.services.catalog_delivery import availability_sql
from app.services.mini_errors import fail

KINDS = ("textbook", "term", "unit", "knowledge")


def tags(admin=False):
    return _tags(True) if admin else _public_tags()


@cached_public
def _public_tags():
    return _tags(False)


def _tags(admin=False):
    with db() as conn:
        rows = conn.execute("SELECT t.*, (SELECT COUNT(*) FROM catalog_paper_tags p JOIN catalog_papers c ON c.id = p.catalog_id "
                            f"JOIN paper_archives a ON a.id = c.paper_id WHERE p.tag_id = t.id AND c.status = 'published' AND {availability_sql()}) AS paper_count "
                            "FROM catalog_tags t " + ("" if admin else "WHERE t.is_visible = 1 ") + "ORDER BY t.kind, t.sort_order, t.name, t.id").fetchall()
    return {"items": [{**dict(row), "is_visible": bool(row["is_visible"])} for row in rows]}


def save(body, identifier=None):
    with db(serialized=True) as conn:
        if conn.execute("SELECT 1 FROM catalog_tags WHERE kind = ? AND name = ? AND id <> ?", (body.kind, body.name, identifier or "")).fetchone():
            fail("此类型已有同名标签")
        if identifier:
            row = conn.execute("SELECT * FROM catalog_tags WHERE id = ?", (identifier,)).fetchone()
            if not row:
                fail("标签不存在", 404)
            if row["revision"] != body.revision:
                fail("标签已更新，请刷新")
            if body.kind != row["kind"]:
                fail("已创建标签的类型不能修改，请新建正确类型的标签", 422)
            conn.execute("UPDATE catalog_tags SET name = ?, is_visible = ?, sort_order = ?, revision = revision + 1 WHERE id = ?",
                         (body.name, int(body.is_visible), body.sort_order, identifier))
        else:
            if conn.execute("SELECT COUNT(*) FROM catalog_tags").fetchone()[0] >= 3000:
                fail("标签数量已达上限，请先整理旧标签", 422)
            identifier = uuid.uuid4().hex
            conn.execute("INSERT INTO catalog_tags(id, kind, name, is_visible, sort_order) VALUES (?, ?, ?, ?, ?)",
                         (identifier, body.kind, body.name, int(body.is_visible), body.sort_order))
        return dict(conn.execute("SELECT * FROM catalog_tags WHERE id = ?", (identifier,)).fetchone())


def remove(identifier, revision):
    with db(serialized=True) as conn:
        row = conn.execute("SELECT revision FROM catalog_tags WHERE id = ?", (identifier,)).fetchone()
        if not row:
            fail("标签不存在", 404)
        if row[0] != revision:
            fail("标签已更新，请刷新")
        if conn.execute("SELECT 1 FROM catalog_paper_tags WHERE tag_id = ?", (identifier,)).fetchone():
            fail("标签已关联资料，可先隐藏或解除关联后删除", 422)
        conn.execute("DELETE FROM catalog_tags WHERE id = ?", (identifier,))


def label_map(conn, identifiers, admin=False):
    result: dict[str, list[dict]] = {identifier: [] for identifier in identifiers}
    if not identifiers:
        return result
    marks = ",".join("?" for _ in identifiers)
    rows = conn.execute(f"SELECT p.catalog_id, t.id, t.kind, t.name FROM catalog_paper_tags p JOIN catalog_tags t ON t.id = p.tag_id WHERE p.catalog_id IN ({marks}) "
                        + ("" if admin else "AND t.is_visible = 1 ") + "ORDER BY t.kind, t.sort_order, t.name", identifiers)
    for row in rows:
        result[row["catalog_id"]].append({key: row[key] for key in ("id", "kind", "name")})
    return result


def assign(catalog_id, body):
    with db(serialized=True) as conn:
        row = conn.execute("SELECT revision FROM catalog_papers WHERE id = ?", (catalog_id,)).fetchone()
        if not row:
            fail("资料不存在", 404)
        if row[0] != body.revision:
            fail("资料已更新，请刷新后重试")
        tag_kinds: dict[str, str] = {}
        if body.tag_ids:
            tag_kinds = {row["id"]: row["kind"] for row in conn.execute(
                "SELECT id, kind FROM catalog_tags WHERE id = ANY(?)", (list(body.tag_ids),)).fetchall()}
        counts: dict[str, int] = {}
        for identifier in body.tag_ids:
            if identifier not in tag_kinds:
                fail("所选标签已删除，请刷新", 404)
            kind = tag_kinds[identifier]
            counts[kind] = counts.get(kind, 0) + 1
        if any(counts.get(kind, 0) > 1 for kind in KINDS[:3]) or counts.get("knowledge", 0) > 20:
            fail("教材、学期、单元各选一个，知识点最多 20 个", 422)
        conn.execute("DELETE FROM catalog_paper_tags WHERE catalog_id = ?", (catalog_id,))
        conn.executemany("INSERT INTO catalog_paper_tags(catalog_id, tag_id) VALUES (?, ?)",
                         [(catalog_id, identifier) for identifier in body.tag_ids])
        conn.execute("UPDATE catalog_papers SET revision = revision + 1 WHERE id = ?", (catalog_id,))
        return {"revision": body.revision + 1, "tags": label_map(conn, [catalog_id], True)[catalog_id]}
