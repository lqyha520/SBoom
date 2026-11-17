"""首付奖励、核对凭据和不可覆盖的结算快照。"""

import json
import time

STARTER_POLICY = {'enabled': False, 'beneficiary': 'admin', 'rate_bps': 1000, 'hold_days': 14, 'channel_rate_bps': 60,
                  'channel_rates': {'wechat': 60, 'virtual_android': 100, 'virtual_ios': 1200},
                  'shared_fees': [{'name': '服务成本分摊', 'mode': 'percent', 'rate_bps': 0, 'basis': 'after_channel'}]}


def seed_starter_policy(conn):
    """只更新从未配置过的初始规则，不覆盖用户配置、历史订单或启用奖励。"""
    original = {'enabled': False, 'beneficiary': 'admin', 'rate_bps': 0, 'hold_days': 7, 'shared_fees': []}
    now = int(time.time())
    changed = conn.execute('UPDATE referral_policy SET value=?::jsonb,revision=revision+1,updated_at=? '
                           'WHERE id=1 AND revision=1 AND updated_at=0 AND value=?::jsonb RETURNING id',
                           (json.dumps(STARTER_POLICY), now, json.dumps(original))).fetchone()
    if changed:
        conn.execute('INSERT INTO referral_settlement_audit(actor_id,kind,target,value,created_at) VALUES(NULL,?,?,?::jsonb,?)',
                     ('starter_policy', '1', json.dumps({'before': original, 'after': STARTER_POLICY,
                      'reason': '可修改的起步建议：奖励10%，等待14天，无依据的共同费用先按0%，保持停用'}), now))


def migrate(conn):
    conn.executescript("""
        ALTER TABLE mini_orders ADD COLUMN IF NOT EXISTS reward_policy JSONB NOT NULL DEFAULT '{}';
        ALTER TABLE mini_orders ADD COLUMN IF NOT EXISTS reward_buyer TEXT NOT NULL DEFAULT '';
        CREATE INDEX IF NOT EXISTS idx_order_reward_buyer ON mini_orders(reward_buyer,created_at);
        CREATE TABLE IF NOT EXISTS referral_policy (
            id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL DEFAULT 1,
            value JSONB NOT NULL DEFAULT '{"enabled":false,"beneficiary":"admin","rate_bps":0,"hold_days":7,"shared_fees":[]}',
            updated_at BIGINT NOT NULL DEFAULT 0
        );
        INSERT INTO referral_policy(id) VALUES(1) ON CONFLICT DO NOTHING;
        CREATE TABLE IF NOT EXISTS referral_first_payments (
            buyer TEXT PRIMARY KEY, order_id TEXT NOT NULL UNIQUE REFERENCES mini_orders(id),
            paid_at BIGINT NOT NULL, historical BOOLEAN NOT NULL DEFAULT FALSE
        );
        CREATE TABLE IF NOT EXISTS referral_statements (
            id TEXT PRIMARY KEY, beneficiary TEXT NOT NULL, beneficiary_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved','paid','void')),
            revision INTEGER NOT NULL DEFAULT 1, snapshot JSONB NOT NULL,
            gross_fen BIGINT NOT NULL, adjustment_fen BIGINT NOT NULL,
            personal_fen BIGINT NOT NULL DEFAULT 0, tax_fen BIGINT,
            net_fen BIGINT, review JSONB, receipt TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '', created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL,
            approved_at BIGINT, paid_at BIGINT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_referral_open_statement ON referral_statements(beneficiary)
            WHERE status IN ('draft','approved');
        CREATE INDEX IF NOT EXISTS idx_referral_statement_beneficiary ON referral_statements(beneficiary,created_at DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_referral_payment_receipt ON referral_statements(receipt) WHERE status='paid';
        CREATE TABLE IF NOT EXISTS referral_rewards (
            order_id TEXT PRIMARY KEY REFERENCES mini_orders(id), buyer TEXT NOT NULL,
            beneficiary TEXT NOT NULL, beneficiary_name TEXT NOT NULL,
            policy JSONB NOT NULL, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','void','paid')),
            revision INTEGER NOT NULL DEFAULT 1, costs JSONB, commission_fen BIGINT,
            statement_id TEXT REFERENCES referral_statements(id), reason TEXT NOT NULL DEFAULT '',
            created_at BIGINT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_referral_rewards_beneficiary ON referral_rewards(beneficiary,created_at DESC);
        CREATE TABLE IF NOT EXISTS referral_adjustments (
            id BIGSERIAL PRIMARY KEY, beneficiary TEXT NOT NULL, beneficiary_name TEXT NOT NULL,
            amount_fen BIGINT NOT NULL CHECK(amount_fen<>0), source TEXT NOT NULL UNIQUE,
            reason TEXT NOT NULL, evidence TEXT NOT NULL,
            statement_id TEXT REFERENCES referral_statements(id), created_at BIGINT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS referral_settlement_audit (
            id BIGSERIAL PRIMARY KEY, actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            kind TEXT NOT NULL, target TEXT NOT NULL, value JSONB NOT NULL, created_at BIGINT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_referral_pending_adjustments ON referral_adjustments(beneficiary,id) WHERE statement_id IS NULL;
        CREATE TABLE IF NOT EXISTS referral_settlement_requests (
            id TEXT PRIMARY KEY, beneficiary TEXT NOT NULL, beneficiary_name TEXT NOT NULL,
            request_key TEXT NOT NULL, quote_digest TEXT NOT NULL, snapshot JSONB NOT NULL,
            note TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','reviewing','approved','paid','rejected','cancelled','invalidated')),
            statement_id TEXT REFERENCES referral_statements(id), created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL,
            UNIQUE(beneficiary,request_key)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_referral_open_request ON referral_settlement_requests(beneficiary)
            WHERE status IN ('pending','reviewing','approved');
        CREATE INDEX IF NOT EXISTS idx_referral_request_owner ON referral_settlement_requests(beneficiary,created_at DESC);
        ALTER TABLE referral_rewards ADD COLUMN IF NOT EXISTS request_id TEXT REFERENCES referral_settlement_requests(id);
        CREATE INDEX IF NOT EXISTS idx_referral_reward_request ON referral_rewards(request_id) WHERE request_id IS NOT NULL;
    """)
    # 只给升级前已付款的客户建立基线，避免续费被误算为首次付费；重复迁移不覆盖账本。
    conn.execute("UPDATE mini_orders o SET reward_buyer=COALESCE(NULLIF(u.wechat_identity,''),'user:' || u.id) "
                 "FROM mini_users u WHERE o.user_id=u.id AND o.reward_buyer=''")
    conn.execute("UPDATE mini_orders SET reward_buyer='user:' || COALESCE(referral->>'buyer_id',user_id,id) WHERE reward_buyer=''")
    conn.execute("INSERT INTO referral_first_payments(buyer,order_id,paid_at,historical) "
                 "SELECT DISTINCT ON (reward_buyer) reward_buyer,id,COALESCE(paid_at,updated_at),TRUE FROM mini_orders "
                 "WHERE (paid_at IS NOT NULL OR status='refunded') AND NOT(payment_channel='virtual' AND virtual_env=1) "
                 "ORDER BY reward_buyer,COALESCE(paid_at,updated_at),id ON CONFLICT DO NOTHING")
    seed_starter_policy(conn)
    # 只补齐新订单的分渠道建议费率，不改历史快照和用户已配置的奖励规则。
    row = conn.execute('SELECT value FROM referral_policy WHERE id=1').fetchone()
    value = row['value']
    if 'channel_rates' not in value:
        rates = {'wechat': value.get('channel_rate_bps') if value.get('channel_rate_bps') is not None else 60,
                 'virtual_android': 100, 'virtual_ios': 1200}
        updated = {**value, 'channel_rates': rates}
        conn.execute('UPDATE referral_policy SET value=?::jsonb,revision=revision+1,updated_at=? WHERE id=1', (json.dumps(updated), int(time.time())))
        conn.execute('INSERT INTO referral_settlement_audit(actor_id,kind,target,value,created_at) VALUES(NULL,?,?,?::jsonb,?)',
                     ('channel_rates_upgrade', '1', json.dumps({'before': value, 'after': updated,
                      'reason': '分渠道起步费率，普通微信沿用原费率；虚拟支付非 iOS 1%、iOS 12%，实际以类目合同和账单核对'}), int(time.time())))
