"""Additive catalog discovery and account service tables."""

from app.mini_schema import _columns


def init_engagement_schema(conn):
    if "wechat_openid_enc" not in _columns(conn, "mini_users"):
        conn.execute("ALTER TABLE mini_users ADD COLUMN wechat_openid_enc TEXT NOT NULL DEFAULT ''")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS catalog_tags (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
            is_visible INTEGER NOT NULL DEFAULT 1, sort_order INTEGER NOT NULL DEFAULT 0,
            revision INTEGER NOT NULL DEFAULT 1, UNIQUE(kind, name)
        );
        CREATE TABLE IF NOT EXISTS catalog_paper_tags (
            catalog_id TEXT NOT NULL REFERENCES catalog_papers(id) ON DELETE CASCADE,
            tag_id TEXT NOT NULL REFERENCES catalog_tags(id) ON DELETE CASCADE,
            PRIMARY KEY(catalog_id, tag_id)
        );
        CREATE INDEX IF NOT EXISTS idx_catalog_tag_papers ON catalog_paper_tags(tag_id, catalog_id);
        CREATE TABLE IF NOT EXISTS catalog_print_editions (
            catalog_id TEXT NOT NULL REFERENCES catalog_papers(id) ON DELETE CASCADE,
            kind TEXT NOT NULL, paper_id TEXT NOT NULL REFERENCES paper_archives(id) ON DELETE RESTRICT,
            PRIMARY KEY(catalog_id, kind)
        );
        CREATE INDEX IF NOT EXISTS idx_catalog_edition_source ON catalog_print_editions(paper_id);
        CREATE TABLE IF NOT EXISTS catalog_edition_history (
            catalog_id TEXT NOT NULL REFERENCES catalog_papers(id) ON DELETE CASCADE,
            paper_id TEXT NOT NULL REFERENCES paper_archives(id) ON DELETE RESTRICT,
            kind TEXT NOT NULL, release_number INTEGER NOT NULL, created_at BIGINT NOT NULL,
            PRIMARY KEY(catalog_id, paper_id, kind, release_number)
        );
        CREATE INDEX IF NOT EXISTS idx_catalog_edition_history_source ON catalog_edition_history(paper_id);
        CREATE TABLE IF NOT EXISTS mini_notifications (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES mini_users(id) ON DELETE CASCADE,
            event_key TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
            target_type TEXT NOT NULL DEFAULT '', target_id TEXT NOT NULL DEFAULT '',
            read_at BIGINT, created_at BIGINT NOT NULL, UNIQUE(user_id, event_key)
        );
        CREATE INDEX IF NOT EXISTS idx_mini_notifications_owner ON mini_notifications(user_id, created_at DESC, id);
        CREATE INDEX IF NOT EXISTS idx_mini_notifications_unread ON mini_notifications(user_id, read_at);
        CREATE TABLE IF NOT EXISTS mini_notice_subscriptions (
            user_id TEXT PRIMARY KEY REFERENCES mini_users(id) ON DELETE CASCADE,
            template_id TEXT NOT NULL, credits INTEGER NOT NULL DEFAULT 0, updated_at BIGINT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mini_subscription_receipts (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES mini_users(id) ON DELETE CASCADE,
            created_at BIGINT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mini_subscription_receipts ON mini_subscription_receipts(user_id, created_at);
        CREATE TABLE IF NOT EXISTS mini_notice_deliveries (
            notification_id TEXT PRIMARY KEY REFERENCES mini_notifications(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
            lease_until BIGINT NOT NULL DEFAULT 0, updated_at BIGINT NOT NULL,
            error_code TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_mini_notice_delivery ON mini_notice_deliveries(status, lease_until);
        CREATE TABLE IF NOT EXISTS mini_content_requests (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES mini_users(id) ON DELETE CASCADE,
            fingerprint TEXT NOT NULL, title TEXT NOT NULL, grade TEXT NOT NULL DEFAULT '',
            subject TEXT NOT NULL DEFAULT '', details TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending', reply TEXT NOT NULL DEFAULT '',
            catalog_id TEXT REFERENCES catalog_papers(id) ON DELETE SET NULL,
            revision INTEGER NOT NULL DEFAULT 1, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mini_requests_owner ON mini_content_requests(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_mini_requests_group ON mini_content_requests(fingerprint, status);
        CREATE INDEX IF NOT EXISTS idx_mini_requests_status ON mini_content_requests(status, updated_at DESC);
        CREATE TABLE IF NOT EXISTS mini_account_closures (
            id TEXT PRIMARY KEY, user_id TEXT UNIQUE REFERENCES mini_users(id) ON DELETE SET NULL,
            account_name TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending', reply TEXT NOT NULL DEFAULT '',
            revision INTEGER NOT NULL DEFAULT 1, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL,
            admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mini_closure_status ON mini_account_closures(status, updated_at DESC);
    """)
