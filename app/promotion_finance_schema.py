"""月度账本、付款批次、异议和投入台账；升级不覆盖历史快照。"""


def migrate(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS referral_cost_vouchers (
            id TEXT PRIMARY KEY, admin_id INTEGER NOT NULL REFERENCES users(id), reference TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL, total_fen BIGINT NOT NULL CHECK(total_fen>0), evidence TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1, created_at BIGINT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cost_voucher_owner ON referral_cost_vouchers(admin_id,created_at);
        CREATE TABLE IF NOT EXISTS referral_cost_voucher_files (
            id TEXT PRIMARY KEY, voucher_id TEXT NOT NULL REFERENCES referral_cost_vouchers(id),
            name TEXT NOT NULL, media_type TEXT NOT NULL, digest TEXT NOT NULL, content BYTEA NOT NULL,
            created_at BIGINT NOT NULL, UNIQUE(voucher_id,digest)
        );
        ALTER TABLE referral_notice_reads ADD COLUMN IF NOT EXISTS personal_last_id BIGINT;
        CREATE TABLE IF NOT EXISTS referral_finance_controls (
            id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL DEFAULT 1,
            separate_review BOOLEAN NOT NULL DEFAULT FALSE, separate_payment BOOLEAN NOT NULL DEFAULT FALSE
        );
        INSERT INTO referral_finance_controls(id) VALUES(1) ON CONFLICT DO NOTHING;
        CREATE TABLE IF NOT EXISTS referral_ledger_events (
            source TEXT PRIMARY KEY, beneficiary TEXT NOT NULL, kind TEXT NOT NULL,
            amount_fen BIGINT NOT NULL, occurred_at BIGINT NOT NULL, original_at BIGINT NOT NULL DEFAULT 0,
            statement_id TEXT NOT NULL DEFAULT ''
        );
        ALTER TABLE referral_ledger_events ADD COLUMN IF NOT EXISTS original_at BIGINT NOT NULL DEFAULT 0;
        CREATE INDEX IF NOT EXISTS idx_referral_ledger_owner ON referral_ledger_events(beneficiary,occurred_at);
        CREATE TABLE IF NOT EXISTS referral_monthly_reports (
            id TEXT PRIMARY KEY, beneficiary TEXT NOT NULL, month TEXT NOT NULL, snapshot JSONB NOT NULL,
            actor_id INTEGER REFERENCES users(id), created_at BIGINT NOT NULL, UNIQUE(beneficiary,month)
        );
        CREATE TABLE IF NOT EXISTS referral_payout_batches (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, request_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','cancelled')),
            revision INTEGER NOT NULL DEFAULT 1, actor_id INTEGER REFERENCES users(id), created_at BIGINT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS referral_payout_batch_items (
            batch_id TEXT NOT NULL REFERENCES referral_payout_batches(id),
            statement_id TEXT NOT NULL REFERENCES referral_statements(id), snapshot JSONB NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','failed','paid','cancelled')),
            reason TEXT NOT NULL DEFAULT '', PRIMARY KEY(batch_id,statement_id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_referral_batch_reserved ON referral_payout_batch_items(statement_id)
            WHERE status IN ('pending','failed');
        CREATE TABLE IF NOT EXISTS referral_payout_imports (
            batch_id TEXT NOT NULL REFERENCES referral_payout_batches(id), digest TEXT NOT NULL,
            result JSONB NOT NULL, actor_id INTEGER REFERENCES users(id), created_at BIGINT NOT NULL,
            PRIMARY KEY(batch_id,digest)
        );
        CREATE TABLE IF NOT EXISTS referral_disputes (
            id TEXT PRIMARY KEY, beneficiary TEXT NOT NULL, target_kind TEXT NOT NULL CHECK(target_kind IN ('reward','statement')),
            target_id TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open'
                CHECK(status IN ('open','processing','resolved','rejected')),
            request_key TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
            created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL, UNIQUE(beneficiary,request_key)
        );
        CREATE INDEX IF NOT EXISTS idx_referral_dispute_target ON referral_disputes(target_kind,target_id,status);
        CREATE TABLE IF NOT EXISTS referral_dispute_messages (
            id BIGSERIAL PRIMARY KEY, dispute_id TEXT NOT NULL REFERENCES referral_disputes(id),
            actor_id INTEGER REFERENCES users(id), content TEXT NOT NULL, evidence TEXT NOT NULL,
            created_at BIGINT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS referral_dispute_files (
            id TEXT PRIMARY KEY, dispute_id TEXT NOT NULL REFERENCES referral_disputes(id),
            name TEXT NOT NULL, media_type TEXT NOT NULL, digest TEXT NOT NULL, content BYTEA NOT NULL,
            created_at BIGINT NOT NULL, UNIQUE(dispute_id,digest)
        );
        CREATE TABLE IF NOT EXISTS referral_campaign_expenses (
            id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES referral_campaigns(id),
            request_key TEXT, request_digest TEXT,
            expense_date TEXT NOT NULL, category TEXT NOT NULL, amount_fen BIGINT NOT NULL CHECK(amount_fen>0),
            evidence TEXT NOT NULL, note TEXT NOT NULL, active BOOLEAN NOT NULL DEFAULT TRUE,
            revision INTEGER NOT NULL DEFAULT 1, actor_id INTEGER REFERENCES users(id), created_at BIGINT NOT NULL
        );
        ALTER TABLE referral_campaign_expenses ADD COLUMN IF NOT EXISTS request_key TEXT;
        ALTER TABLE referral_campaign_expenses ADD COLUMN IF NOT EXISTS request_digest TEXT;
        ALTER TABLE referral_campaign_expenses ADD COLUMN IF NOT EXISTS source_ref TEXT NOT NULL DEFAULT '';
        ALTER TABLE referral_campaign_expenses ADD COLUMN IF NOT EXISTS included_in_baseline BOOLEAN NOT NULL DEFAULT FALSE;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_referral_expense_source ON referral_campaign_expenses(source_ref)
            WHERE active AND source_ref<>'';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_referral_expense_request ON referral_campaign_expenses(campaign_id,request_key)
            WHERE request_key IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_referral_expense_campaign ON referral_campaign_expenses(campaign_id,expense_date);
    """)
    from app.services.settlement_ledger import backfill
    backfill(conn)
