"""教材订阅、个人题库与公共资料排期的增量结构。"""


def migrate(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS mini_curriculum_subscriptions (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES mini_users(id) ON DELETE CASCADE,
            grade TEXT NOT NULL, subject TEXT NOT NULL, textbook_id TEXT NOT NULL DEFAULT '',
            notify INTEGER NOT NULL DEFAULT 1, created_at BIGINT NOT NULL,
            UNIQUE(user_id, grade, subject, textbook_id)
        );
        CREATE INDEX IF NOT EXISTS idx_curriculum_owner ON mini_curriculum_subscriptions(user_id,id);
        CREATE TABLE IF NOT EXISTS mini_curriculum_digest (
            subscription_id TEXT PRIMARY KEY REFERENCES mini_curriculum_subscriptions(id) ON DELETE CASCADE,
            checked_at BIGINT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS question_bank (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL, grade TEXT NOT NULL, subject TEXT NOT NULL, topic TEXT NOT NULL,
            difficulty TEXT NOT NULL, section_type TEXT NOT NULL, content_json TEXT NOT NULL,
            content_hash TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
            created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL,
            UNIQUE(user_id,content_hash)
        );
        CREATE INDEX IF NOT EXISTS idx_question_bank_owner ON question_bank(user_id,updated_at DESC,id);
        CREATE TABLE IF NOT EXISTS catalog_schedules (
            catalog_id TEXT PRIMARY KEY REFERENCES catalog_papers(id) ON DELETE CASCADE,
            admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL, scheduled_at BIGINT NOT NULL,
            catalog_revision INTEGER NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
            policy_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', message TEXT NOT NULL DEFAULT '',
            created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_catalog_schedules_due ON catalog_schedules(status,scheduled_at,catalog_id);
        CREATE TABLE IF NOT EXISTS catalog_link_checks (
            catalog_id TEXT PRIMARY KEY REFERENCES catalog_papers(id) ON DELETE CASCADE,
            url_hash TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL,
            checked_at BIGINT NOT NULL
        );
    """)
