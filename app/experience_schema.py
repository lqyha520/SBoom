"""Additive schema for consumer service and editorial workflows."""

from app.mini_schema import _columns


def init_experience_schema(conn):
    if "nickname" not in _columns(conn, "mini_users"):
        conn.execute("ALTER TABLE mini_users ADD COLUMN nickname TEXT NOT NULL DEFAULT ''")
        conn.execute("UPDATE mini_users SET nickname = username")
    for name, definition in (("release_number", "INTEGER NOT NULL DEFAULT 1"),
                             ("update_note", "TEXT NOT NULL DEFAULT ''")):
        if name not in _columns(conn, "catalog_papers"):
            conn.execute(f"ALTER TABLE catalog_papers ADD COLUMN {name} {definition}")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS mini_favorite_groups (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES mini_users(id) ON DELETE CASCADE,
            name TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
            created_at BIGINT NOT NULL, UNIQUE(user_id, name)
        );
        CREATE TABLE IF NOT EXISTS mini_favorite_group_items (
            user_id TEXT NOT NULL, catalog_id TEXT NOT NULL,
            group_id TEXT NOT NULL REFERENCES mini_favorite_groups(id) ON DELETE CASCADE,
            PRIMARY KEY(user_id, catalog_id),
            FOREIGN KEY(user_id, catalog_id) REFERENCES mini_catalog_favorites(user_id, catalog_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_mini_group_items ON mini_favorite_group_items(group_id);
        CREATE TABLE IF NOT EXISTS mini_recent_views (
            user_id TEXT NOT NULL REFERENCES mini_users(id) ON DELETE CASCADE,
            catalog_id TEXT NOT NULL REFERENCES catalog_papers(id) ON DELETE CASCADE,
            viewed_at BIGINT NOT NULL, PRIMARY KEY(user_id, catalog_id)
        );
        CREATE INDEX IF NOT EXISTS idx_mini_recent ON mini_recent_views(user_id, viewed_at DESC);
        CREATE TABLE IF NOT EXISTS mini_feedback (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES mini_users(id) ON DELETE CASCADE,
            catalog_id TEXT REFERENCES catalog_papers(id) ON DELETE SET NULL,
            paper_title TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL, body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', reply TEXT NOT NULL DEFAULT '',
            internal_note TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 1,
            admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mini_feedback ON mini_feedback(status, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_mini_feedback_owner ON mini_feedback(user_id, created_at DESC);
        CREATE TABLE IF NOT EXISTS mini_usage_events (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES mini_users(id) ON DELETE CASCADE,
            kind TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
            catalog_id TEXT REFERENCES catalog_papers(id) ON DELETE SET NULL, created_at BIGINT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mini_events ON mini_usage_events(created_at, kind, user_id);
        CREATE TABLE IF NOT EXISTS site_topics (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            is_visible INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0,
            revision INTEGER NOT NULL DEFAULT 1, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS site_topic_items (
            topic_id TEXT NOT NULL REFERENCES site_topics(id) ON DELETE CASCADE,
            catalog_id TEXT NOT NULL REFERENCES catalog_papers(id) ON DELETE CASCADE,
            sort_order INTEGER NOT NULL, PRIMARY KEY(topic_id, catalog_id)
        );
        CREATE TABLE IF NOT EXISTS catalog_versions (
            id TEXT PRIMARY KEY, catalog_id TEXT NOT NULL REFERENCES catalog_papers(id) ON DELETE CASCADE,
            paper_id TEXT NOT NULL REFERENCES paper_archives(id) ON DELETE RESTRICT,
            release_number INTEGER NOT NULL, note TEXT NOT NULL DEFAULT '', created_at BIGINT NOT NULL,
            UNIQUE(catalog_id, release_number)
        );
        CREATE INDEX IF NOT EXISTS idx_catalog_version_source ON catalog_versions(paper_id);
    """)
