"""Additive, PostgreSQL-compatible paper library tables."""


def init_library_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS paper_folders (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            created_at BIGINT NOT NULL,
            UNIQUE(user_id, name)
        );
        CREATE TABLE IF NOT EXISTS paper_series (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            PRIMARY KEY(user_id, source_id)
        );
        CREATE TABLE IF NOT EXISTS paper_archives (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_id TEXT NOT NULL,
            request_id TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            version INTEGER NOT NULL,
            title TEXT NOT NULL,
            grade TEXT NOT NULL,
            subject TEXT NOT NULL,
            keyword TEXT NOT NULL,
            question_count INTEGER NOT NULL,
            snapshot_json TEXT NOT NULL,
            folder_id TEXT REFERENCES paper_folders(id) ON DELETE SET NULL,
            group_id TEXT NOT NULL DEFAULT '',
            group_name TEXT NOT NULL DEFAULT '',
            favorite INTEGER NOT NULL DEFAULT 0,
            file_status TEXT NOT NULL DEFAULT 'pending',
            file_error TEXT NOT NULL DEFAULT '',
            upload_token TEXT NOT NULL DEFAULT '',
            upload_started_at BIGINT NOT NULL DEFAULT 0,
            upload_reserved_bytes BIGINT NOT NULL DEFAULT 0,
            page_count INTEGER NOT NULL DEFAULT 0,
            created_at BIGINT NOT NULL,
            updated_at BIGINT NOT NULL,
            UNIQUE(user_id, request_id),
            UNIQUE(user_id, source_id, content_hash),
            UNIQUE(user_id, source_id, version)
        );
        CREATE INDEX IF NOT EXISTS idx_paper_user_created ON paper_archives(user_id, created_at DESC, id);
        CREATE INDEX IF NOT EXISTS idx_paper_folder ON paper_archives(user_id, folder_id);
        CREATE TABLE IF NOT EXISTS paper_assets (
            id TEXT PRIMARY KEY,
            paper_id TEXT NOT NULL REFERENCES paper_archives(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            page_number INTEGER NOT NULL DEFAULT 0,
            storage TEXT NOT NULL,
            storage_key TEXT NOT NULL UNIQUE,
            mime_type TEXT NOT NULL,
            byte_size BIGINT NOT NULL,
            sha256 TEXT NOT NULL,
            UNIQUE(paper_id, kind, page_number)
        );
        CREATE TABLE IF NOT EXISTS mini_accounts (
            identity TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            created_at BIGINT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mini_sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at BIGINT NOT NULL,
            expires_at BIGINT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mini_session_user ON mini_sessions(user_id);
        CREATE TABLE IF NOT EXISTS mini_login_tickets (
            token_hash TEXT PRIMARY KEY,
            identity TEXT NOT NULL,
            expires_at BIGINT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mini_binding_requests (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code_hash TEXT NOT NULL UNIQUE,
            identity TEXT NOT NULL DEFAULT '',
            claim_hash TEXT NOT NULL DEFAULT '',
            verification TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'waiting',
            expires_at BIGINT NOT NULL,
            created_at BIGINT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mini_binding_user ON mini_binding_requests(user_id);
        CREATE TABLE IF NOT EXISTS catalog_papers (
            id TEXT PRIMARY KEY,
            paper_id TEXT NOT NULL UNIQUE REFERENCES paper_archives(id) ON DELETE CASCADE,
            publisher_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            featured INTEGER NOT NULL DEFAULT 0,
            revision INTEGER NOT NULL DEFAULT 1,
            published_at BIGINT NOT NULL DEFAULT 0,
            created_at BIGINT NOT NULL,
            updated_at BIGINT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_catalog_status ON catalog_papers(status, featured, published_at DESC, id);
        CREATE TABLE IF NOT EXISTS catalog_favorites (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            catalog_id TEXT NOT NULL REFERENCES catalog_papers(id) ON DELETE CASCADE,
            created_at BIGINT NOT NULL,
            PRIMARY KEY(user_id, catalog_id)
        );
        CREATE TABLE IF NOT EXISTS catalog_downloads (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            catalog_id TEXT NOT NULL REFERENCES catalog_papers(id) ON DELETE CASCADE,
            requested_at BIGINT NOT NULL,
            PRIMARY KEY(user_id, catalog_id)
        );
        CREATE INDEX IF NOT EXISTS idx_catalog_favorite_paper ON catalog_favorites(catalog_id);
        CREATE INDEX IF NOT EXISTS idx_catalog_download_paper ON catalog_downloads(catalog_id);
    """)
    from app.mini_schema import init_mini_schema

    init_mini_schema(conn)
