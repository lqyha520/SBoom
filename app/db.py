"""数据库层 —— 双驱动：SQLite（stdlib）或 PostgreSQL（psycopg3）

通过 .env 的 DATABASE_URL 切换：
- 空（默认）        → SQLite，文件路径由 LC_DB_PATH 或 data/users.db 决定
- postgresql://... → PostgreSQL，多 worker 部署推荐

两套后端共用同一套业务 SQL（? 占位符、datetime('now','localtime') 时间函数、
ON CONFLICT upsert、RETURNING），由本模块统一翻译，业务代码无需感知差异。
"""

import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(
    os.environ.get("LC_DB_PATH")
    or (Path(__file__).resolve().parent.parent / "data" / "users.db")
)

from app.config import get_settings  # noqa: E402  （放这里避免 env 未就绪的循环导入问题）


def _use_pg() -> bool:
    url = get_settings().database_url
    return bool(url) and url.startswith(("postgresql://", "postgres://"))


# ─── SQL 方言翻译（仅 PG 路径使用） ───

def _to_pg_sql(sql: str) -> str:
    """SQLite 风格 SQL → PostgreSQL 风格：
    1. datetime('now', 'localtime') → to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
    2. ? 占位符 → %s（跳过字符串字面量内的 ?）
    """
    sql = sql.replace(
        "datetime('now', 'localtime')",
        "to_char(now(), 'YYYY-MM-DD HH24:MI:SS')",
    ).replace(
        "datetime('now','localtime')",
        "to_char(now(), 'YYYY-MM-DD HH24:MI:SS')",
    )
    out, in_str, i = [], False, 0
    while i < len(sql):
        ch = sql[i]
        if in_str:
            out.append(ch)
            if ch == "'":
                if i + 1 < len(sql) and sql[i + 1] == "'":
                    out.append("'")
                    i += 1
                else:
                    in_str = False
        elif ch == "'":
            in_str = True
            out.append(ch)
        elif ch == "?":
            out.append("%s")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


class _MixedRow(dict):
    """同时支持 row["name"] 和 row[0] 两种访问方式的行对象（对齐 sqlite3.Row 习惯）。"""

    _order: list

    def __init__(self, keys, values):
        super().__init__(zip(keys, values))
        self._order = list(values)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._order[key]
        return super().__getitem__(key)


def _pg_row_factory(cursor):
    """psycopg3 row_factory：返回一个"行构造器"，产出支持 row["name"] 和 row[0] 的行对象。"""
    if cursor.description is None:
        return lambda values: None
    cols = [d.name if hasattr(d, "name") else d[0] for d in cursor.description]

    def _make_row(values):
        return _MixedRow(cols, values)

    return _make_row


class _PgConn:
    """psycopg3 连接的薄包装：对业务层暴露与 sqlite3.Connection 一致的小接口。"""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        return self._conn.execute(_to_pg_sql(sql), params)

    def executemany(self, sql, seq):
        return self._conn.cursor().executemany(_to_pg_sql(sql), seq)

    def executescript(self, script):
        for stmt in [s.strip() for s in script.split(";") if s.strip()]:
            self._conn.execute(stmt)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


# ─── 建表语句 ───

_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',
    is_active     INTEGER NOT NULL DEFAULT 1,
    token_valid_after INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS user_llm_configs (
    user_id     INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    base_url    TEXT NOT NULL DEFAULT '',
    model       TEXT NOT NULL DEFAULT '',
    api_key_enc TEXT NOT NULL DEFAULT '',
    timeout     INTEGER NOT NULL DEFAULT 60,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS user_templates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    data       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS app_config (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS feedbacks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    username   TEXT NOT NULL DEFAULT '',
    game_id    TEXT NOT NULL DEFAULT '',
    is_oob     INTEGER NOT NULL DEFAULT 0,
    comment    TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_feedbacks_created ON feedbacks(created_at DESC);
"""

_SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',
    is_active     INTEGER NOT NULL DEFAULT 1,
    token_valid_after INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS user_llm_configs (
    user_id     INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    base_url    TEXT NOT NULL DEFAULT '',
    model       TEXT NOT NULL DEFAULT '',
    api_key_enc TEXT NOT NULL DEFAULT '',
    timeout     INTEGER NOT NULL DEFAULT 60,
    updated_at  TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS user_templates (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    data       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    updated_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS app_config (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS feedbacks (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    username   TEXT NOT NULL DEFAULT '',
    game_id    TEXT NOT NULL DEFAULT '',
    is_oob     INTEGER NOT NULL DEFAULT 0,
    comment    TEXT,
    created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE INDEX IF NOT EXISTS idx_feedbacks_created ON feedbacks(created_at DESC);
"""


# ─── PostgreSQL 连接池（懒创建） ───

_pg_pool = None
_pg_pool_lock = threading.Lock()


def _get_pg_pool():
    """psycopg_pool 连接池：进程内复用，避免每请求新建 TCP+TLS 连接。

    双检锁防竞态：db() 会被事件循环线程与 to_thread 工作线程并发调用，
    无锁时多个线程可能同时建池——输家池泄漏连接，赢家可能长时间等打开。
    """
    global _pg_pool
    if _pg_pool is None:
        with _pg_pool_lock:
            if _pg_pool is None:
                from psycopg_pool import ConnectionPool

                pool = ConnectionPool(
                    get_settings().database_url,
                    min_size=1,
                    max_size=10,
                    timeout=30,  # 池耗尽时最多等 30s
                    open=False,
                    kwargs={"row_factory": _pg_row_factory, "connect_timeout": 10},
                )
                pool.open(wait=True, timeout=30)
                _pg_pool = pool
                logger.info("PostgreSQL 连接池已就绪（min=1, max=10）")
    return _pg_pool


def close_pg_pool() -> None:
    """应用关停时释放连接池。"""
    global _pg_pool
    with _pg_pool_lock:
        if _pg_pool is not None:
            _pg_pool.close()
            _pg_pool = None


@contextmanager
def db():
    """从连接池取连接（PG）或每请求新建（SQLite）；正常退出 commit，异常回滚并关闭。

    SQLite 路径：WAL 模式 + busy_timeout，多用户并发写不再互相锁死。
    PG 路径：psycopg_pool 连接池接管（min=1, max=10）。
    """
    if _use_pg():
        with _get_pg_pool().connection() as conn:
            yield _PgConn(conn)
            conn.commit()
        return

    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    # 注：journal_mode=WAL 是持久化设置，init_db() 已执行一次，
    # 不在每连接重复执行（避免短暂持锁放大写竞争）
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate_sqlite(conn: sqlite3.Connection) -> None:
    """存量库补列（方案B初期建的 users 表没有 role/is_active/token_valid_after）。"""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "role" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        logger.info("迁移：users 表新增 role 列")
    if "is_active" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        logger.info("迁移：users 表新增 is_active 列")
    if "token_valid_after" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN token_valid_after INTEGER NOT NULL DEFAULT 0")
        logger.info("迁移：users 表新增 token_valid_after 列（改密吊销旧会话）")


def _migrate_pg(conn) -> None:
    """存量 PG 库补列（与 _migrate_sqlite 对齐）。"""
    cols = {
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'users'"
        ).fetchall()
    }
    if "role" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        logger.info("迁移：users 表新增 role 列（PG）")
    if "is_active" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        logger.info("迁移：users 表新增 is_active 列（PG）")
    if "token_valid_after" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN token_valid_after INTEGER NOT NULL DEFAULT 0")
        logger.info("迁移：users 表新增 token_valid_after 列（PG，改密吊销旧会话）")


def init_db() -> None:
    if _use_pg():
        with db() as conn:
            conn.executescript(_SCHEMA_PG)
            _migrate_pg(conn)
        logger.info("PostgreSQL 数据库就绪")
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        # WAL 模式是数据库级持久设置，建表时设一次即可（多用户并发写不互相锁死）
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(_SCHEMA_SQLITE)
        _migrate_sqlite(conn)
    logger.info(f"用户数据库就绪: {DB_PATH}")
