"""保留账号及业务数据；只有明确指定的已有管理员升级为超级管理员。"""

from app.config import get_settings


def migrate(conn):
    conn.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS is_super_admin BOOLEAN NOT NULL DEFAULT false')
    conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS admin_permissions JSONB NOT NULL DEFAULT '{}'::jsonb")
    conn.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions_revision INTEGER NOT NULL DEFAULT 1')
    # 仅在首次引入权限系统时执行；重复迁移不恢复已撤销权限，也不提升其他账号。
    if not conn.execute("SELECT 1 FROM app_config WHERE key='admin_access_initialized'").fetchone():
        conn.execute("UPDATE users SET is_super_admin=true WHERE username=? AND role='admin' AND is_active=1",
                     (get_settings().super_admin_username,))
        conn.execute("INSERT INTO app_config(key,value) VALUES ('admin_access_initialized','1')")
    conn.execute('''CREATE TABLE IF NOT EXISTS admin_permission_audit (
        id BIGSERIAL PRIMARY KEY, actor_id INTEGER NOT NULL, target_id INTEGER NOT NULL,
        permissions JSONB NOT NULL, revision INTEGER NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )''')
