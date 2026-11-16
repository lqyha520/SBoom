"""推广来源独立于微信身份；用户与订单保存归属快照。"""

import secrets


def migrate(conn):
    conn.executescript("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code TEXT NOT NULL DEFAULT '';
        ALTER TABLE mini_users ADD COLUMN IF NOT EXISTS referral_code TEXT NOT NULL DEFAULT '';
        ALTER TABLE mini_users ADD COLUMN IF NOT EXISTS referral JSONB NOT NULL DEFAULT '{"source":"legacy"}';
        ALTER TABLE mini_orders ADD COLUMN IF NOT EXISTS referral JSONB NOT NULL DEFAULT '{"source":"legacy"}';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_admin_referral_code ON users(referral_code) WHERE referral_code <> '';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mini_referral_code ON mini_users(referral_code) WHERE referral_code <> '';
        CREATE INDEX IF NOT EXISTS idx_mini_referral_admin ON mini_users((referral->>'admin_id'), created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_order_referral_admin ON mini_orders((referral->>'admin_id'), created_at DESC);
        CREATE TABLE IF NOT EXISTS mini_referral_audit (
            id BIGSERIAL PRIMARY KEY, actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            user_id TEXT REFERENCES mini_users(id) ON DELETE SET NULL,
            before_json JSONB NOT NULL, after_json JSONB NOT NULL, reason TEXT NOT NULL,
            created_at BIGINT NOT NULL
        );
    """)
    # 老用户也能作为邀请人；其自身的历史来源不做猜测或回填。
    for row in conn.execute("SELECT id FROM mini_users WHERE referral_code = ''").fetchall():
        conn.execute("UPDATE mini_users SET referral_code=? WHERE id=?", ('u_' + secrets.token_hex(10), row['id']))
