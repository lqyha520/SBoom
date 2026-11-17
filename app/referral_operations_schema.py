"""推广运营扩展：只增表增列，历史奖励与结算快照保持原值。"""


def migrate(conn):
    conn.executescript("""
        ALTER TABLE referral_statements ADD COLUMN IF NOT EXISTS payout JSONB NOT NULL DEFAULT '{}';
        CREATE TABLE IF NOT EXISTS referral_campaigns (
            id TEXT PRIMARY KEY, admin_id INTEGER NOT NULL REFERENCES users(id),
            code TEXT NOT NULL UNIQUE, name TEXT NOT NULL, source TEXT NOT NULL,
            active BOOLEAN NOT NULL DEFAULT TRUE, budget_fen BIGINT,
            revision INTEGER NOT NULL DEFAULT 1, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_referral_campaign_admin ON referral_campaigns(admin_id,created_at);
        CREATE TABLE IF NOT EXISTS referral_budgets (
            beneficiary TEXT PRIMARY KEY, budget_fen BIGINT, revision INTEGER NOT NULL DEFAULT 1,
            updated_at BIGINT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS referral_payees (
            beneficiary TEXT PRIMARY KEY, value_enc TEXT NOT NULL, summary JSONB NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1, updated_at BIGINT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS referral_payout_accounts (
            statement_id TEXT PRIMARY KEY REFERENCES referral_statements(id), value_enc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS referral_attachments (
            id TEXT PRIMARY KEY, statement_id TEXT NOT NULL REFERENCES referral_statements(id),
            actor_id INTEGER REFERENCES users(id), name TEXT NOT NULL, media_type TEXT NOT NULL,
            digest TEXT NOT NULL, content BYTEA NOT NULL, created_at BIGINT NOT NULL,
            UNIQUE(statement_id,digest)
        );
        CREATE TABLE IF NOT EXISTS referral_bill_imports (
            id TEXT PRIMARY KEY, digest TEXT NOT NULL UNIQUE, name TEXT NOT NULL, evidence TEXT NOT NULL,
            actor_id INTEGER REFERENCES users(id), created_at BIGINT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS referral_bill_rows (
            id BIGSERIAL PRIMARY KEY, import_id TEXT NOT NULL REFERENCES referral_bill_imports(id),
            order_id TEXT NOT NULL, transaction_id TEXT NOT NULL, channel TEXT NOT NULL,
            amount_fen BIGINT NOT NULL, channel_fee_fen BIGINT NOT NULL, refunded_fen BIGINT NOT NULL,
            bill_date TEXT NOT NULL, UNIQUE(import_id,order_id)
        );
        CREATE INDEX IF NOT EXISTS idx_referral_bill_order ON referral_bill_rows(order_id,id DESC);
        CREATE TABLE IF NOT EXISTS referral_notice_reads (
            actor_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            last_id BIGINT NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_settlement_audit_target ON referral_settlement_audit(target,id);
    """)
