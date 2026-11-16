"""小红书选题、资料、笔记和发布记录；采集数据保持独立。"""
import json

from app.services.xhs_publication import content_hash, url_key


def migrate(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS xhs_assets (
        id TEXT PRIMARY KEY, admin_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        digest TEXT NOT NULL, media_type TEXT NOT NULL, size_bytes BIGINT NOT NULL,
        metadata_json TEXT NOT NULL, template_json TEXT, content BYTEA,
        revision INTEGER NOT NULL DEFAULT 1, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(admin_id,digest)
    )""")
    conn.execute('CREATE INDEX IF NOT EXISTS idx_xhs_assets_owner ON xhs_assets(admin_id,updated_at DESC)')
    conn.execute('ALTER TABLE xhs_assets ADD COLUMN IF NOT EXISTS thumbnail BYTEA')
    conn.execute("ALTER TABLE xhs_assets ADD COLUMN IF NOT EXISTS storage TEXT NOT NULL DEFAULT 'local'")
    conn.execute("ALTER TABLE xhs_assets ADD COLUMN IF NOT EXISTS storage_key TEXT NOT NULL DEFAULT ''")
    conn.execute("""CREATE TABLE IF NOT EXISTS xhs_workflow_records (
        id TEXT PRIMARY KEY, admin_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK(kind IN ('ideas','materials','drafts','publications')),
        parent_id TEXT REFERENCES xhs_workflow_records(id),
        title TEXT NOT NULL, status TEXT NOT NULL, data_json TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 1, create_hash TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")
    conn.execute('CREATE INDEX IF NOT EXISTS idx_xhs_workflow_owner ON xhs_workflow_records(admin_id,kind,updated_at DESC)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_xhs_workflow_parent ON xhs_workflow_records(parent_id)')
    conn.execute('ALTER TABLE xhs_workflow_records ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ')
    conn.execute('ALTER TABLE xhs_workflow_records ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ')
    conn.execute('ALTER TABLE xhs_workflow_records ADD COLUMN IF NOT EXISTS publication_url_key TEXT')
    conn.execute('ALTER TABLE xhs_workflow_records ADD COLUMN IF NOT EXISTS publication_content_hash TEXT')
    # 旧记录分批回填，迁移期间只在内存中保留一批历史文案。
    while rows := conn.execute("SELECT id,data_json FROM xhs_workflow_records WHERE kind='publications' AND (publication_url_key IS NULL OR publication_content_hash IS NULL) ORDER BY id LIMIT 200").fetchall():
        for row in rows:
            data = json.loads(row['data_json'])
            conn.execute('UPDATE xhs_workflow_records SET publication_url_key=?,publication_content_hash=? WHERE id=?',
                         (url_key(data.get('url', '')), content_hash(data), row['id']))
    conn.execute("CREATE INDEX IF NOT EXISTS idx_xhs_publication_url ON xhs_workflow_records(admin_id,publication_url_key,id) WHERE kind='publications' AND publication_url_key<>''")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_xhs_publication_content ON xhs_workflow_records(admin_id,publication_content_hash,updated_at DESC,id) WHERE kind='publications' AND publication_content_hash<>''")
    conn.execute("""UPDATE xhs_workflow_records SET
        scheduled_at=NULLIF(data_json::jsonb->>'scheduled_at','')::timestamptz,
        published_at=NULLIF(data_json::jsonb->>'published_at','')::timestamptz
        WHERE kind='publications' AND (scheduled_at IS DISTINCT FROM NULLIF(data_json::jsonb->>'scheduled_at','')::timestamptz
        OR published_at IS DISTINCT FROM NULLIF(data_json::jsonb->>'published_at','')::timestamptz)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_xhs_publication_schedule ON xhs_workflow_records(admin_id,scheduled_at,id) WHERE kind='publications' AND status NOT IN ('published','archived')")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_xhs_publication_published ON xhs_workflow_records(admin_id,published_at,id) WHERE kind='publications' AND published_at IS NOT NULL")
    conn.execute("""CREATE TABLE IF NOT EXISTS xhs_workflow_versions (
        record_id TEXT NOT NULL REFERENCES xhs_workflow_records(id) ON DELETE CASCADE,
        revision INTEGER NOT NULL, data_json TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY(record_id,revision)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS xhs_workflow_metrics (
        publication_id TEXT NOT NULL REFERENCES xhs_workflow_records(id) ON DELETE CASCADE,
        checkpoint INTEGER NOT NULL CHECK(checkpoint IN (1,3,7)),
        revision INTEGER NOT NULL DEFAULT 1, data_json TEXT NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(publication_id,checkpoint)
    )""")
