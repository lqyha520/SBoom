"""Alternative print files must describe the same exercise snapshot."""

import hashlib
import json
import time

from app.db import db
from app.services.mini_errors import fail

LABELS = {"original": "原稿 PDF", "student": "练习版", "answers": "答案解析版"}


def fingerprint(raw):
    paper = json.loads(raw)["paper"]
    value = {"grade": paper["grade"], "subject": paper["subject"], "sections": [
        {"type": section["type"], "data": section["data"]} for section in paper["sections"]]}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def referenced(conn, paper_id):
    return bool(conn.execute("SELECT 1 FROM catalog_edition_history WHERE paper_id = ?", (paper_id,)).fetchone())


def listing(conn, catalog_id, admin=False, can_download=True):
    paper = conn.execute("SELECT paper_id FROM catalog_papers WHERE id = ?", (catalog_id,)).fetchone()
    if not paper:
        return []
    originals = [("original", paper[0])]
    originals.extend((row["kind"], row["paper_id"]) for row in conn.execute("SELECT kind, paper_id FROM catalog_print_editions WHERE catalog_id = ? ORDER BY kind", (catalog_id,)) if row["paper_id"] != paper[0])
    result = []
    for kind, paper_id in originals:
        asset = conn.execute("SELECT s.id, s.byte_size, a.snapshot_json FROM paper_assets s JOIN paper_archives a ON a.id = s.paper_id WHERE s.paper_id = ? AND s.kind = 'pdf' AND a.file_status = 'ready'", (paper_id,)).fetchone()
        if not asset:
            continue
        mode = json.loads(asset["snapshot_json"])["export_options"]["mode"]
        label = LABELS[kind] if kind != "original" else {"student": "练习版", "answersOnly": "答案版", "withAnswers": "习题与答案版"}[mode]
        item = {"kind": kind, "label": label, "byte_size": asset["byte_size"], "mode": mode}
        if admin:
            item["paper_id"] = paper_id
        if can_download:
            prefix = "/api/v1/admin/catalog" if admin else "/api/v1/catalog"
            item["url"] = f"{prefix}/papers/{catalog_id}/assets/{asset['id']}"
        result.append(item)
    return result


def source_id(conn, catalog_id, original_id, kind):
    if kind == "original":
        return original_id
    row = conn.execute("SELECT e.paper_id FROM catalog_print_editions e JOIN paper_archives a ON a.id = e.paper_id WHERE e.catalog_id = ? AND e.kind = ? AND a.file_status = 'ready'", (catalog_id, kind)).fetchone()
    if not row:
        fail("此版本尚未发布或已更新，请刷新资料", 404)
    return row[0]


def is_import(row) -> bool:
    """手动导入的归档（source_id 以 import- 开头）：内容只有导入人清楚，关联打印版本时不做一致性校验。"""
    return bool(row["source_id"]) and row["source_id"].startswith("import-")


def sources(admin_id, catalog_id, q=""):
    with db() as conn:
        target = conn.execute("SELECT a.* FROM catalog_papers c JOIN paper_archives a ON a.id = c.paper_id WHERE c.id = ?", (catalog_id,)).fetchone()
        if not target:
            fail("资料不存在", 404)
        if is_import(target):
            # 导入的资料：列出自己全部导入的归档，不限年级科目题量，内容是否配套由导入人确认
            args = [admin_id]
            where = "user_id = ? AND file_status = 'ready' AND source_id LIKE 'import-%'"
            match = None
        else:
            match = fingerprint(target["snapshot_json"])
            args = [admin_id, target["grade"], target["subject"], target["question_count"]]
            where = "user_id = ? AND grade = ? AND subject = ? AND question_count = ? AND file_status = 'ready'"
        if q:
            where += " AND LOWER(title) LIKE ? ESCAPE '\\'"
            args.append("%" + q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
        rows = conn.execute(f"SELECT id, title, version, snapshot_json FROM paper_archives WHERE {where} ORDER BY created_at DESC, id DESC LIMIT 500", args)
        items = []
        for row in rows:
            if match is None or fingerprint(row["snapshot_json"]) == match:
                mode = json.loads(row["snapshot_json"])["export_options"]["mode"]
                dupe = conn.execute("SELECT title FROM catalog_papers WHERE paper_id = ? AND id <> ?", (row["id"], catalog_id)).fetchone()
                items.append({"id": row["id"], "title": row["title"], "version": row["version"], "mode": mode,
                              "owned_by": dupe["title"] if dupe else ""})
            if len(items) == 50:
                break
    return {"items": items, "loose": match is None}


def assign(admin_id, catalog_id, body):
    with db(serialized=True) as conn:
        target = conn.execute("SELECT c.*, a.snapshot_json, a.source_id AS archive_source_id FROM catalog_papers c JOIN paper_archives a ON a.id = c.paper_id WHERE c.id = ?", (catalog_id,)).fetchone()
        if not target:
            fail("资料不存在", 404)
        if target["revision"] != body.revision:
            fail("资料已更新，请刷新后重试")
        if target["status"] == "published" and not body.confirm_publication:
            fail("请确认文件内容与权限后发布此打印版本", 422)
        if body.paper_id:
            source = conn.execute("SELECT * FROM paper_archives WHERE id = ? AND user_id = ?", (body.paper_id, admin_id)).fetchone()
            if not source:
                fail("只能选择自己保存的原稿", 404)
            if source["file_status"] != "ready":
                fail("该原稿的文件尚未就绪")
            if not (is_import(source) or target["archive_source_id"].startswith("import-")):
                # 仅工作台产出做内容一致性校验；涉及手动导入的由导入人自行确认内容配套
                mode = json.loads(source["snapshot_json"])["export_options"]["mode"]
                if (body.kind == "student" and mode != "student") or (body.kind == "answers" and mode not in ("answersOnly", "withAnswers")):
                    fail("文件的导出模式与所选打印版本不一致", 422)
                if fingerprint(source["snapshot_json"]) != fingerprint(target["snapshot_json"]):
                    fail("打印版本必须与当前资料包含相同题目，请从同一份习题保存练习版或答案版", 422)
            dupe = conn.execute("SELECT title FROM catalog_papers WHERE paper_id = ? AND id <> ?", (body.paper_id, catalog_id)).fetchone()
            if dupe:
                fail(f"该文件已单独建了公共条目「{dupe['title']}」，请先删除该条目（原稿会保留），再关联为打印版本", 409)
            for table, field in (("catalog_versions", "catalog_id"), ("catalog_edition_history", "catalog_id")):
                if conn.execute(f"SELECT 1 FROM {table} WHERE paper_id = ? AND {field} <> ?", (body.paper_id, catalog_id)).fetchone():
                    fail("此原稿已属于另一公共条目，请另存版本")
            conn.execute("INSERT INTO catalog_print_editions(catalog_id, kind, paper_id) VALUES (?, ?, ?) ON CONFLICT(catalog_id, kind) DO UPDATE SET paper_id = excluded.paper_id", (catalog_id, body.kind, body.paper_id))
            conn.execute("INSERT INTO catalog_edition_history(catalog_id, paper_id, kind, release_number, created_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(catalog_id, paper_id, kind, release_number) DO NOTHING",
                         (catalog_id, body.paper_id, body.kind, target["release_number"], int(time.time())))
        else:
            conn.execute("DELETE FROM catalog_print_editions WHERE catalog_id = ? AND kind = ?", (catalog_id, body.kind))
        conn.execute("UPDATE catalog_papers SET revision = revision + 1, updated_at = ? WHERE id = ?", (int(time.time()), catalog_id))
        if body.confirm_publication:
            from app.services.catalog_review import confirm
            confirm(conn, catalog_id, admin_id)
        else:
            conn.execute("UPDATE catalog_papers SET reviewed_at = 0, reviewed_by = NULL, answer_readiness = 'unknown' WHERE id = ?", (catalog_id,))
        return {"revision": body.revision + 1, "editions": listing(conn, catalog_id, True)}
