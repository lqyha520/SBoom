"""通用经营账本（收入/支出）schema。"""

def migrate(conn) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS finance_ledger_entries (
            id TEXT PRIMARY KEY,
            identifier TEXT NOT NULL UNIQUE,
            entry_date TEXT NOT NULL,
            direction TEXT NOT NULL CHECK(direction IN ('income','expense')),
            category TEXT NOT NULL,
            amount_fen BIGINT NOT NULL CHECK(amount_fen >= 0),
            tax_fen BIGINT NOT NULL DEFAULT 0 CHECK(tax_fen >= 0),
            counterparty TEXT NOT NULL DEFAULT '',
            reference TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            attachment TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','void')),
            revision INTEGER NOT NULL DEFAULT 1,
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at BIGINT NOT NULL,
            updated_at BIGINT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_finance_ledger_date ON finance_ledger_entries(entry_date DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_finance_ledger_direction ON finance_ledger_entries(direction, status, entry_date DESC);
        ALTER TABLE finance_ledger_entries ALTER COLUMN amount_fen TYPE BIGINT;
        ALTER TABLE finance_ledger_entries ALTER COLUMN tax_fen TYPE BIGINT;
        CREATE TABLE IF NOT EXISTS finance_ledger_audit (
            id BIGSERIAL PRIMARY KEY,
            entry_id TEXT NOT NULL REFERENCES finance_ledger_entries(id),
            actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            action TEXT NOT NULL,
            before_json TEXT NOT NULL,
            after_json TEXT NOT NULL,
            created_at BIGINT NOT NULL
        );
    """)
