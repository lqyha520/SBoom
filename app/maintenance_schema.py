"""Additive storage maintenance schema."""
def init_maintenance_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS file_deletions (
            storage TEXT NOT NULL, storage_key TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0, next_attempt BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY(storage, storage_key)
        );
        CREATE INDEX IF NOT EXISTS idx_file_deletions_due ON file_deletions(next_attempt);
        CREATE TABLE IF NOT EXISTS image_assets (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            request_id TEXT NOT NULL, storage TEXT NOT NULL, storage_key TEXT NOT NULL,
            byte_size BIGINT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
            expires_at BIGINT NOT NULL, UNIQUE(user_id, request_id)
        );
        CREATE INDEX IF NOT EXISTS idx_image_assets_expiry ON image_assets(expires_at);
        CREATE INDEX IF NOT EXISTS idx_paper_assets_storage ON paper_assets(storage, storage_key);
        CREATE INDEX IF NOT EXISTS idx_image_assets_storage ON image_assets(storage, storage_key);
        CREATE INDEX IF NOT EXISTS idx_generation_result_expiry ON generation_requests(finished_at) WHERE result_json <> '';
    """)

    conn.execute("ALTER TABLE catalog_papers ADD COLUMN IF NOT EXISTS reviewed_at BIGINT NOT NULL DEFAULT 0")
    conn.execute("ALTER TABLE catalog_papers ADD COLUMN IF NOT EXISTS reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL")
    conn.execute("ALTER TABLE catalog_papers ADD COLUMN IF NOT EXISTS answer_readiness TEXT NOT NULL DEFAULT 'unknown'")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS catalog_reviews (
            id BIGSERIAL PRIMARY KEY, catalog_id TEXT NOT NULL REFERENCES catalog_papers(id) ON DELETE CASCADE,
            paper_id TEXT NOT NULL, admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            revision INTEGER NOT NULL, reviewed_at BIGINT NOT NULL, answer_readiness TEXT NOT NULL
        );
    """)
