"""Consumer accounts and entitlements, separate from workbench users."""

import json


def _columns(conn, table):
    rows = conn.execute(
        # 必须限定当前 schema，避免同库其他 schema 的同名表干扰补列判断
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = ? AND table_schema = current_schema()", (table,)
    ).fetchall()
    return {row[0] for row in rows}


def _add_avatar_column(conn) -> None:
    """mini_users 增加 avatar：存预设头像键，空串表示还没选（前端按账号 id 派生配色兜底）。"""
    if "avatar" in _columns(conn, "mini_users"):
        return
    conn.execute("ALTER TABLE mini_users ADD COLUMN avatar TEXT NOT NULL DEFAULT ''")


def init_mini_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS mini_users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL DEFAULT '',
            wechat_identity TEXT UNIQUE,
            avatar TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            membership TEXT NOT NULL DEFAULT 'regular',
            vip_expires_at BIGINT,
            revision INTEGER NOT NULL DEFAULT 1,
            created_at BIGINT NOT NULL,
            updated_at BIGINT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mini_user_sessions (
            token_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES mini_users(id) ON DELETE CASCADE,
            created_at BIGINT NOT NULL,
            expires_at BIGINT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mini_user_sessions ON mini_user_sessions(user_id);
        CREATE TABLE IF NOT EXISTS mini_user_avatars (
            user_id TEXT PRIMARY KEY REFERENCES mini_users(id) ON DELETE CASCADE,
            version TEXT NOT NULL,
            content_base64 TEXT NOT NULL,
            updated_at BIGINT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mini_catalog_favorites (
            user_id TEXT NOT NULL REFERENCES mini_users(id) ON DELETE CASCADE,
            catalog_id TEXT NOT NULL REFERENCES catalog_papers(id) ON DELETE CASCADE,
            created_at BIGINT NOT NULL,
            PRIMARY KEY(user_id, catalog_id)
        );
        CREATE TABLE IF NOT EXISTS mini_catalog_downloads (
            user_id TEXT NOT NULL REFERENCES mini_users(id) ON DELETE CASCADE,
            catalog_id TEXT NOT NULL REFERENCES catalog_papers(id) ON DELETE CASCADE,
            requested_at BIGINT NOT NULL,
            PRIMARY KEY(user_id, catalog_id)
        );
        CREATE INDEX IF NOT EXISTS idx_mini_favorite_catalog ON mini_catalog_favorites(catalog_id);
        CREATE INDEX IF NOT EXISTS idx_mini_download_catalog ON mini_catalog_downloads(catalog_id);
        CREATE TABLE IF NOT EXISTS mini_membership_events (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES mini_users(id) ON DELETE CASCADE,
            admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            before_json TEXT NOT NULL,
            after_json TEXT NOT NULL,
            created_at BIGINT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS catalog_access (
            catalog_id TEXT PRIMARY KEY REFERENCES catalog_papers(id) ON DELETE CASCADE,
            view_access TEXT NOT NULL DEFAULT 'inherit',
            download_access TEXT NOT NULL DEFAULT 'inherit'
        );
        CREATE TABLE IF NOT EXISTS catalog_question_types (
            catalog_id TEXT NOT NULL REFERENCES catalog_papers(id) ON DELETE CASCADE,
            question_type TEXT NOT NULL,
            PRIMARY KEY(catalog_id, question_type)
        );
        CREATE INDEX IF NOT EXISTS idx_catalog_question_type ON catalog_question_types(question_type);
        CREATE TABLE IF NOT EXISTS catalog_type_rules (
            question_type TEXT PRIMARY KEY,
            view_access TEXT NOT NULL DEFAULT 'free',
            download_access TEXT NOT NULL DEFAULT 'free',
            revision INTEGER NOT NULL DEFAULT 1,
            updated_at BIGINT NOT NULL
        );
    """)
    _add_avatar_column(conn)
    # Backfill the public type index, never workbench identities or private data.
    rows = conn.execute("SELECT c.id, a.snapshot_json FROM catalog_papers c JOIN paper_archives a ON a.id = c.paper_id "
                        "WHERE NOT EXISTS (SELECT 1 FROM catalog_question_types t WHERE t.catalog_id = c.id)").fetchall()
    for row in rows:
        index_question_types(conn, row["id"], row["snapshot_json"])


def index_question_types(conn, catalog_id, snapshot_json):
    snapshot = json.loads(snapshot_json)
    from app.models import GameType
    kinds = {section["type"] for section in snapshot["paper"]["sections"]}
    kinds.update(kind for kind in snapshot["paper"].get("declared_question_types", []) if kind in {item.value for item in GameType})
    for kind in kinds:
        conn.execute("INSERT INTO catalog_question_types(catalog_id, question_type) VALUES (?, ?) "
                     "ON CONFLICT(catalog_id, question_type) DO NOTHING", (catalog_id, kind))
