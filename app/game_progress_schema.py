"""游戏云存档随账号删除，版本号防止多设备互相覆盖。"""


def migrate(conn):
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS game_progress (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            game_id TEXT NOT NULL,
            progress_json TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 0,
            mutation_id TEXT NOT NULL,
            updated_at BIGINT NOT NULL,
            PRIMARY KEY(user_id, game_id)
        );
    ''')
