"""小程序运营内容表：分类、首页 Banner、公告、协议文档、年级/科目字典。

「增量、方言中立」的建表脚本：不使用方言专有类型，占位符与时间函数由 app.db 统一翻译。
"""

import hashlib
import time
import uuid

from app.site_defaults import (
    DEFAULT_DOCUMENTS,
    DEFAULT_GRADES,
    DEFAULT_SUBJECTS,
    PREVIOUS_DOCUMENT_HASHES,
    RETIRED_DICTIONARY_VALUES,
)

SITE_TABLES = """
CREATE TABLE IF NOT EXISTS site_categories (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    icon        TEXT NOT NULL DEFAULT '',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_visible  INTEGER NOT NULL DEFAULT 1,
    revision    INTEGER NOT NULL DEFAULT 1,
    created_at  BIGINT NOT NULL,
    updated_at  BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS site_banners (
    id           TEXT PRIMARY KEY,
    kicker       TEXT NOT NULL DEFAULT '',
    title        TEXT NOT NULL,
    subtitle     TEXT NOT NULL DEFAULT '',
    action_label TEXT NOT NULL DEFAULT '',
    target_type  TEXT NOT NULL DEFAULT 'none',
    target_value TEXT NOT NULL DEFAULT '',
    image_key    TEXT NOT NULL DEFAULT '',
    image_storage TEXT NOT NULL DEFAULT '',
    image_mime   TEXT NOT NULL DEFAULT '',
    image_bytes  BIGINT NOT NULL DEFAULT 0,
    image_fit    TEXT NOT NULL DEFAULT 'contain',
    sort_order   INTEGER NOT NULL DEFAULT 0,
    is_visible   INTEGER NOT NULL DEFAULT 1,
    revision     INTEGER NOT NULL DEFAULT 1,
    created_at   BIGINT NOT NULL,
    updated_at   BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS site_notices (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL DEFAULT '',
    placement   TEXT NOT NULL DEFAULT 'popup',
    level       TEXT NOT NULL DEFAULT 'info',
    starts_at   BIGINT NOT NULL DEFAULT 0,
    ends_at     BIGINT NOT NULL DEFAULT 0,
    is_visible  INTEGER NOT NULL DEFAULT 1,
    revision    INTEGER NOT NULL DEFAULT 1,
    created_at  BIGINT NOT NULL,
    updated_at  BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS site_documents (
    key        TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL DEFAULT '',
    revision   INTEGER NOT NULL DEFAULT 1,
    updated_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS site_dictionary (
    id         TEXT PRIMARY KEY,
    kind       TEXT NOT NULL,
    parent     TEXT NOT NULL DEFAULT '',
    value      TEXT NOT NULL,
    label      TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_visible INTEGER NOT NULL DEFAULT 1,
    revision   INTEGER NOT NULL DEFAULT 1,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    UNIQUE (kind, parent, value)
);

-- 年级 ↔ 科目的显式关联（多对多）：parent_id=年级行 id，child_id=科目行 id
CREATE TABLE IF NOT EXISTS site_dict_links (
    parent_id  TEXT NOT NULL,
    child_id   TEXT NOT NULL,
    created_at BIGINT NOT NULL,
    PRIMARY KEY (parent_id, child_id)
);

CREATE INDEX IF NOT EXISTS idx_site_banner_order ON site_banners(is_visible, sort_order, id);
CREATE INDEX IF NOT EXISTS idx_site_notice_window ON site_notices(is_visible, placement, starts_at);
CREATE INDEX IF NOT EXISTS idx_site_dictionary ON site_dictionary(kind, is_visible, sort_order);
"""


def _columns(conn, table):
    rows = conn.execute(
        # 必须限定当前 schema：同库多 schema（测试隔离/多租户）时，
        # 未过滤会匹配到其他 schema 同名表的列，导致误判"列已存在"而跳过补列
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = ? AND table_schema = current_schema()", (table,)
    ).fetchall()
    return {row[0] for row in rows}


def _add_category_column(conn) -> None:
    """catalog_papers 增加 category_id：分类名仍冗余保存，历史 SQL 与搜索无需改动。"""
    if "category_id" in _columns(conn, "catalog_papers"):
        return
    conn.execute("ALTER TABLE catalog_papers ADD COLUMN category_id TEXT NOT NULL DEFAULT ''")


def _seed_dictionary(conn, now: int) -> None:
    # 回填历史空 label（种子曾只写 value，导致前端下拉显示空白）；空 label 一律以 value 兜底
    conn.execute("UPDATE site_dictionary SET label = value, updated_at = ? WHERE label = ''", (now,))
    for kind, values in (("grade", DEFAULT_GRADES), ("subject", DEFAULT_SUBJECTS)):
        for index, value in enumerate(values):
            conn.execute(
                "INSERT INTO site_dictionary(id, kind, parent, value, label, sort_order, is_visible, revision, created_at, updated_at) "
                "VALUES (?, ?, '', ?, ?, ?, 1, 1, ?, ?) ON CONFLICT(kind, parent, value) DO NOTHING",
                (f"{kind}-{uuid.uuid4().hex[:12]}", kind, value, value, (index + 1) * 10, now, now),
            )
    # 修剪历史默认值（初中/高中年级、语数英外科目）：精确按字面量删除，不动管理员自加的值
    for kind, retired in RETIRED_DICTIONARY_VALUES.items():
        for value in retired:
            rows = conn.execute("SELECT id FROM site_dictionary WHERE kind = ? AND value = ?", (kind, value)).fetchall()
            for row in rows:
                item_id = row["id"] if not isinstance(row, tuple) else row[0]
                conn.execute("DELETE FROM site_dictionary WHERE id = ?", (item_id,))
                _prune_dictionary_children(conn, item_id)


def _prune_dictionary_children(conn, item_id: str) -> None:
    """删除字典条目时同步清理关联与从属的知识点（知识点 parent = 年级id|科目id）。"""
    conn.execute("DELETE FROM site_dict_links WHERE parent_id = ? OR child_id = ?", (item_id, item_id))
    conn.execute("DELETE FROM site_dictionary WHERE parent LIKE ? OR parent LIKE ?",
                 (item_id + "|%", "%|" + item_id))


def _seed_dictionary_scope(conn, now: int) -> None:
    """首次启动迁移：按 knowledge_scope.json 建立年级-科目关联，并把允许的知识点导入字典。

    用 app_config 标记只跑一次；之后关联与知识点完全以后台管理为准，重启不回写。
    """
    import json
    from pathlib import Path

    markers = {"links": "dict_links_seeded", "points": "dict_points_seeded"}
    done = {row["key"] for row in conn.execute(
        "SELECT key FROM app_config WHERE key IN (?, ?)", list(markers.values())).fetchall()}
    if markers["links"] in done and markers["points"] in done:
        return

    data_path = Path(__file__).parent / "data" / "knowledge_scope.json"
    if not data_path.exists():
        return
    with open(data_path, encoding="utf-8") as handle:
        scope_data = json.load(handle)

    grades = {row["value"]: row["id"] for row in conn.execute("SELECT id, value FROM site_dictionary WHERE kind = 'grade'")}
    subjects = {row["value"]: row["id"] for row in conn.execute("SELECT id, value FROM site_dictionary WHERE kind = 'subject'")}

    if markers["links"] not in done:
        for grade_value, subject_map in scope_data.items():
            grade_id = grades.get(grade_value)
            if not grade_id:
                continue
            for subject_value in subject_map:
                subject_id = subjects.get(subject_value)
                if subject_id:
                    conn.execute(
                        "INSERT INTO site_dict_links(parent_id, child_id, created_at) VALUES (?, ?, ?) "
                        "ON CONFLICT(parent_id, child_id) DO NOTHING", (grade_id, subject_id, now))
        conn.execute("INSERT INTO app_config(key, value) VALUES (?, '1') ON CONFLICT(key) DO NOTHING", (markers["links"],))

    if markers["points"] not in done:
        for grade_value, subject_map in scope_data.items():
            grade_id = grades.get(grade_value)
            if not grade_id:
                continue
            for subject_value, scope in subject_map.items():
                subject_id = subjects.get(subject_value)
                if not subject_id:
                    continue
                parent = f"{grade_id}|{subject_id}"
                for index, point in enumerate(scope.get("allowed", [])):
                    point = str(point).strip()
                    if not point:
                        continue
                    conn.execute(
                        "INSERT INTO site_dictionary(id, kind, parent, value, label, sort_order, is_visible, revision, created_at, updated_at) "
                        "VALUES (?, 'knowledge_point', ?, ?, ?, ?, 1, 1, ?, ?) ON CONFLICT(kind, parent, value) DO NOTHING",
                        (uuid.uuid4().hex, parent, point, point, (index + 1) * 10, now, now))
        conn.execute("INSERT INTO app_config(key, value) VALUES (?, '1') ON CONFLICT(key) DO NOTHING", (markers["points"],))


def _seed_documents(conn, now: int) -> None:
    for key, doc in DEFAULT_DOCUMENTS.items():
        conn.execute(
            "INSERT INTO site_documents(key, title, body, revision, updated_at) VALUES (?, ?, ?, 1, ?) "
            "ON CONFLICT(key) DO NOTHING",
            (key, doc["title"], doc["body"], now),
        )
        row = conn.execute("SELECT title, body, revision FROM site_documents WHERE key = ?", (key,)).fetchone()
        if row["revision"] == 1 and row["title"] == doc["title"] and hashlib.sha256(row["body"].encode()).hexdigest() == PREVIOUS_DOCUMENT_HASHES.get(key):
            conn.execute("UPDATE site_documents SET body = ?, revision = revision + 1, updated_at = ? WHERE key = ? AND revision = 1",
                         (doc["body"], now, key))


def _backfill_categories(conn, now: int) -> int:
    """把历史自由文本分类收编成分类表条目，并回填 category_id。"""
    names = [row[0] for row in conn.execute(
        "SELECT DISTINCT category FROM catalog_papers WHERE category <> '' ORDER BY category")]
    created = 0
    for index, name in enumerate(names):
        row = conn.execute("SELECT id FROM site_categories WHERE name = ?", (name,)).fetchone()
        if row:
            continue
        conn.execute(
            "INSERT INTO site_categories(id, name, description, icon, sort_order, is_visible, revision, created_at, updated_at) "
            "VALUES (?, ?, '', '', ?, 1, 1, ?, ?)",
            (uuid.uuid4().hex, name, (index + 1) * 10, now, now),
        )
        created += 1
        conn.execute("UPDATE catalog_papers SET category_id = (SELECT id FROM site_categories WHERE name = ?) "
                     "WHERE category = ? AND category_id = ''", (name, name))
    # 已存在同名分类但 category_id 仍为空的历史行
    conn.execute("UPDATE catalog_papers SET category_id = COALESCE((SELECT id FROM site_categories WHERE name = catalog_papers.category), '') "
                 "WHERE category_id = '' AND category <> ''")
    return created


def _migrate_dictionary_v2(conn) -> None:
    """存量库升级：补 parent 列、放宽唯一约束（知识点允许同名挂在不同组合下）。

    parent 相关索引也在这里建：SITE_TABLES 里建会撞上「存量表还没有该列」的窗口。
    """
    if "parent" not in _columns(conn, "site_dictionary"):
        conn.execute("ALTER TABLE site_dictionary ADD COLUMN parent TEXT NOT NULL DEFAULT ''")
    constraints = {row[0] for row in conn.execute(
        "SELECT conname FROM pg_constraint WHERE conrelid = 'site_dictionary'::regclass AND contype = 'u'")}
    if "site_dictionary_kind_value_key" in constraints:
        conn.execute("ALTER TABLE site_dictionary DROP CONSTRAINT site_dictionary_kind_value_key")
    if "site_dictionary_kind_parent_value_key" not in constraints:
        conn.execute("ALTER TABLE site_dictionary ADD CONSTRAINT site_dictionary_kind_parent_value_key UNIQUE (kind, parent, value)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_site_dictionary_parent ON site_dictionary(kind, parent, is_visible, sort_order)")


def init_site_schema(conn) -> None:
    now = int(time.time())
    conn.executescript(SITE_TABLES)
    if "image_fit" not in _columns(conn, "site_banners"):
        conn.execute("ALTER TABLE site_banners ADD COLUMN image_fit TEXT NOT NULL DEFAULT 'contain'")
    _add_category_column(conn)
    _migrate_dictionary_v2(conn)
    _seed_dictionary(conn, now)
    _seed_dictionary_scope(conn, now)
    _seed_documents(conn, now)
    created = _backfill_categories(conn, now)
    if created:
        import logging

        logging.getLogger(__name__).info("分类表已从历史习题数据收编 %d 个分类", created)
