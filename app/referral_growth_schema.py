"""推广访问漏斗与活动投入；仅添加字段和表，不改历史财务快照。"""


def migrate(conn):
    conn.executescript("""
        ALTER TABLE referral_campaigns ADD COLUMN IF NOT EXISTS spend_fen BIGINT;
        ALTER TABLE referral_campaigns ADD COLUMN IF NOT EXISTS landing_kind TEXT NOT NULL DEFAULT 'home';
        ALTER TABLE referral_campaigns ADD COLUMN IF NOT EXISTS landing_id TEXT NOT NULL DEFAULT '';
        CREATE TABLE IF NOT EXISTS referral_tracking_config (
            id INTEGER PRIMARY KEY CHECK(id=1), started_at BIGINT NOT NULL
        );
        INSERT INTO referral_tracking_config(id,started_at) VALUES(1,EXTRACT(EPOCH FROM NOW())::bigint)
            ON CONFLICT DO NOTHING;
        CREATE TABLE IF NOT EXISTS referral_visits (
            id TEXT PRIMARY KEY, code TEXT NOT NULL, entry_key TEXT NOT NULL,
            admin_id INTEGER NOT NULL REFERENCES users(id),
            campaign_id TEXT REFERENCES referral_campaigns(id),
            created_at BIGINT NOT NULL, started_at BIGINT, registered_at BIGINT,
            user_id TEXT REFERENCES mini_users(id) ON DELETE SET NULL,
            UNIQUE(code,entry_key), UNIQUE(user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_referral_visit_scope ON referral_visits(admin_id,campaign_id,created_at);
    """)
