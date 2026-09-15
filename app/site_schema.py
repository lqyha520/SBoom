"""小程序运营内容表：分类、首页 Banner、公告、协议文档、年级/科目字典。

与 mini_schema 一样是「增量、双库兼容」的建表脚本：SQLite 与 PostgreSQL 共用同一份
DDL（不使用方言专有类型），由 app.db 负责占位符与时间函数翻译。
"""

import time
import uuid

from app.site_defaults import DEFAULT_DOCUMENTS, DEFAULT_GRADES, DEFAULT_SUBJECTS

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
    value      TEXT NOT NULL,
    label      TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_visible INTEGER NOT NULL DEFAULT 1,
    revision   INTEGER NOT NULL DEFAULT 1,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    UNIQUE (kind, value)
);

CREATE INDEX IF NOT EXISTS idx_site_banner_order ON site_banners(is_visible, sort_order, id);
CREATE INDEX IF NOT EXISTS idx_site_notice_window ON site_notices(is_visible, placement, starts_at);
CREATE INDEX IF NOT EXISTS idx_site_dictionary ON site_dictionary(kind, is_visible, sort_order);
"""


def _columns(conn, table):
    from app.db import _use_pg

    if _use_pg():
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?", (table,)
        ).fetchall()
        return {row[0] for row in rows}
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_category_column(conn) -> None:
    """catalog_papers 增加 category_id：分类名仍冗余保存，历史 SQL 与搜索无需改动。"""
    if "category_id" in _columns(conn, "catalog_papers"):
        return
    conn.execute("ALTER TABLE catalog_papers ADD COLUMN category_id TEXT NOT NULL DEFAULT ''")


def _seed_dictionary(conn, now: int) -> None:
    for kind, values in (("grade", DEFAULT_GRADES), ("subject", DEFAULT_SUBJECTS)):
        for index, value in enumerate(values):
            conn.execute(
                "INSERT INTO site_dictionary(id, kind, value, label, sort_order, is_visible, revision, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?) ON CONFLICT(kind, value) DO NOTHING",
                (f"{kind}-{uuid.uuid4().hex[:12]}", kind, value, "", (index + 1) * 10, now, now),
            )


def _seed_documents(conn, now: int) -> None:
    for key, doc in DEFAULT_DOCUMENTS.items():
        conn.execute(
            "INSERT INTO site_documents(key, title, body, revision, updated_at) VALUES (?, ?, ?, 1, ?) "
            "ON CONFLICT(key) DO NOTHING",
            (key, doc["title"], doc["body"], now),
        )


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


def init_site_schema(conn) -> None:
    now = int(time.time())
    conn.executescript(SITE_TABLES)
    _add_category_column(conn)
    _seed_dictionary(conn, now)
    _seed_documents(conn, now)
    created = _backfill_categories(conn, now)
    if created:
        import logging

        logging.getLogger(__name__).info("分类表已从历史习题数据收编 %d 个分类", created)
