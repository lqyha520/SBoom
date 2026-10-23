"""Money amounts are integer fen; historical orders survive account removal."""

from app.mini_schema import _columns


def init_commerce_schema(conn):
    if "entitlement_epoch" not in _columns(conn, "mini_users"):
        conn.execute("ALTER TABLE mini_users ADD COLUMN entitlement_epoch INTEGER NOT NULL DEFAULT 0")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS mini_membership_plans (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            days INTEGER NOT NULL, price_fen INTEGER NOT NULL, is_active INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 1,
            purchase_limit INTEGER NOT NULL DEFAULT 0,
            virtual_product_id TEXT NOT NULL DEFAULT '',
            created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mini_orders (
            id TEXT PRIMARY KEY, user_id TEXT REFERENCES mini_users(id) ON DELETE SET NULL,
            request_key TEXT NOT NULL UNIQUE, plan_id TEXT NOT NULL REFERENCES mini_membership_plans(id) ON DELETE RESTRICT,
            plan_name TEXT NOT NULL, plan_days INTEGER NOT NULL, amount_fen INTEGER NOT NULL,
            currency TEXT NOT NULL DEFAULT 'CNY', status TEXT NOT NULL DEFAULT 'created',
            appid TEXT NOT NULL, mchid TEXT NOT NULL, transaction_id TEXT UNIQUE,
            payment_channel TEXT NOT NULL DEFAULT 'wechat', virtual_env INTEGER NOT NULL DEFAULT 0,
            virtual_offer_id TEXT NOT NULL DEFAULT '', virtual_product_id TEXT NOT NULL DEFAULT '',
            virtual_order_id TEXT NOT NULL DEFAULT '', virtual_order_type INTEGER NOT NULL DEFAULT 0,
            delivered_at BIGINT,
            prepay_id TEXT NOT NULL DEFAULT '', payer_enc TEXT NOT NULL DEFAULT '',
            lease_key TEXT NOT NULL DEFAULT '', lease_until BIGINT NOT NULL DEFAULT 0,
            revision INTEGER NOT NULL DEFAULT 1, created_at BIGINT NOT NULL, expires_at BIGINT NOT NULL,
            paid_at BIGINT, closed_at BIGINT, updated_at BIGINT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mini_orders_owner ON mini_orders(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_mini_orders_status ON mini_orders(status, expires_at);
        CREATE TABLE IF NOT EXISTS mini_refunds (
            id TEXT PRIMARY KEY, order_id TEXT NOT NULL UNIQUE REFERENCES mini_orders(id) ON DELETE RESTRICT,
            reason TEXT NOT NULL, reply TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'requested',
            provider_id TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 1,
            admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            lease_key TEXT NOT NULL DEFAULT '', lease_until BIGINT NOT NULL DEFAULT 0,
            created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL, completed_at BIGINT
        );
        CREATE INDEX IF NOT EXISTS idx_mini_refunds_status ON mini_refunds(status, updated_at);
        CREATE TABLE IF NOT EXISTS mini_membership_grants (
            id TEXT PRIMARY KEY, user_id TEXT REFERENCES mini_users(id) ON DELETE SET NULL,
            order_id TEXT UNIQUE REFERENCES mini_orders(id) ON DELETE RESTRICT,
            epoch INTEGER NOT NULL, starts_at BIGINT NOT NULL, ends_at BIGINT NOT NULL,
            revoked_at BIGINT, created_at BIGINT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mini_member_grants ON mini_membership_grants(user_id, epoch, starts_at);
        CREATE TABLE IF NOT EXISTS mini_payment_events (
            id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES mini_orders(id) ON DELETE RESTRICT,
            kind TEXT NOT NULL, created_at BIGINT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mini_reconciliations (
            id TEXT PRIMARY KEY, bill_date TEXT NOT NULL, status TEXT NOT NULL,
            summary_json TEXT NOT NULL DEFAULT '{}', differences_json TEXT NOT NULL DEFAULT '[]',
            error TEXT NOT NULL DEFAULT '', admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mini_reconciliation_date ON mini_reconciliations(bill_date, created_at DESC);
        CREATE TABLE IF NOT EXISTS mini_membership_cards (
            id TEXT PRIMARY KEY, code_hash TEXT NOT NULL UNIQUE, code_hint TEXT NOT NULL,
            days INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'active',
            redeemed_by TEXT REFERENCES mini_users(id) ON DELETE SET NULL,
            redeemed_at BIGINT, created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at BIGINT NOT NULL, expires_at BIGINT
        );
        CREATE INDEX IF NOT EXISTS idx_mini_membership_cards_status ON mini_membership_cards(status, created_at DESC);
    """)
    # 存量库补列：虚拟支付渠道快照与发货状态。
    conn.executescript("""
        ALTER TABLE mini_membership_plans ADD COLUMN IF NOT EXISTS purchase_limit INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE mini_membership_plans ADD COLUMN IF NOT EXISTS virtual_product_id TEXT NOT NULL DEFAULT '';
        ALTER TABLE mini_orders ADD COLUMN IF NOT EXISTS payment_channel TEXT NOT NULL DEFAULT 'wechat';
        ALTER TABLE mini_orders ADD COLUMN IF NOT EXISTS virtual_env INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE mini_orders ADD COLUMN IF NOT EXISTS virtual_offer_id TEXT NOT NULL DEFAULT '';
        ALTER TABLE mini_orders ADD COLUMN IF NOT EXISTS virtual_product_id TEXT NOT NULL DEFAULT '';
        ALTER TABLE mini_orders ADD COLUMN IF NOT EXISTS virtual_order_id TEXT NOT NULL DEFAULT '';
        ALTER TABLE mini_orders ADD COLUMN IF NOT EXISTS virtual_order_type INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE mini_orders ADD COLUMN IF NOT EXISTS delivered_at BIGINT;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mini_orders_virtual_order ON mini_orders(virtual_order_id) WHERE virtual_order_id <> '';
        CREATE INDEX IF NOT EXISTS idx_mini_orders_channel_status ON mini_orders(payment_channel, status, updated_at);
    """)
