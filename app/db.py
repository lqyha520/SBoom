"""数据库层 —— PostgreSQL（psycopg3 + 连接池）

业务代码统一写 SQLite 风格 SQL（? 占位符、datetime('now','localtime') 时间函数、
ON CONFLICT upsert、RETURNING），由本模块统一翻译为 PostgreSQL 方言，业务代码无需感知差异。
本项目已移除 SQLite 运行时支持：DATABASE_URL 必须配置为 PostgreSQL 连接串。
"""

import itertools
import logging
import threading
import time
from contextlib import contextmanager
from functools import lru_cache
from hashlib import sha256

logger = logging.getLogger(__name__)

from app.config import get_settings  # noqa: E402
from app.constants import LOCK_IDS as _LOCK_IDS  # noqa: E402


def _database_url() -> str:
    url = get_settings().database_url
    if not url.startswith(("postgresql://", "postgres://")):
        raise RuntimeError(
            "DATABASE_URL 未配置或不是 PostgreSQL 连接串。"
            "本项目仅支持 PostgreSQL，请在 .env 配置例如 "
            "DATABASE_URL=postgresql://learncoach:learncoach@127.0.0.1:5432/learncoach"
        )
    return url


# ─── SQL 方言翻译 ───

@lru_cache(maxsize=4096)
def _to_pg_sql(sql: str) -> str:
    """SQLite 风格 SQL → PostgreSQL 风格：
    1. datetime('now', 'localtime') → to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
    2. ? 占位符 → %s（跳过字符串字面量内的 ?）
    3. 字面量 % → %%（psycopg 只认 %s/%b/%t，LIKE 'import-%' 这类会被当成非法占位符）

    纯函数（输出只由输入字符串决定），业务 SQL 基本都是固定模板，
    用 LRU 缓存省掉每次 execute 的逐字符扫描。
    """
    sql = sql.replace(
        "datetime('now', 'localtime')",
        "to_char(now(), 'YYYY-MM-DD HH24:MI:SS')",
    ).replace(
        "datetime('now','localtime')",
        "to_char(now(), 'YYYY-MM-DD HH24:MI:SS')",
    )
    out, in_str, i = [], False, 0
    # 字面量 % 先整体转义成 %%（psycopg 只认 %s/%b/%t，LIKE 'import-%' 会被当成非法占位符）；
    # 必须先做这一步再插 %s，否则连占位符一起被转义。
    sql = sql.replace("%", "%%")
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

    _order: tuple

    def __init__(self, keys, values):
        super().__init__(zip(keys, values, strict=False))
        # psycopg 传进来的就是不可变 tuple，直接持有引用即可，不再逐行复制一份 list
        self._order = values if isinstance(values, tuple) else tuple(values)

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
    """psycopg3 连接的薄包装：对业务层暴露统一的 execute/executemany/commit 接口。"""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        # 始终传 tuple：params=None 时 psycopg 不做占位符解析，%% 转义就不会被还原
        return self._conn.execute(_to_pg_sql(sql), () if params is None else params)

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


_sp_seq = itertools.count(1)


@contextmanager
def savepoint(conn):
    """在既有事务内开子事务（SAVEPOINT），块内失败只回滚该子事务。

    PostgreSQL 里任何一条语句失败都会把**整个事务**打成 aborted，后续语句全部报
    InFailedSqlTransaction，最终 commit 退化成 ROLLBACK。所以那种"用 try/except 吞掉
    可选 DDL（建索引/补列），失败就算了"的写法在 PG 下并不安全：吞掉异常不等于救回事务，
    整个 init_db 的建表会一起被回滚。要真正隔离失败，必须把语句放进 SAVEPOINT。

    conn 可以是 _PgConn，也可以是裸 psycopg 连接。
    """
    raw = getattr(conn, "_conn", conn)
    name = f"lc_sp_{next(_sp_seq)}"
    raw.execute(f"SAVEPOINT {name}")
    try:
        yield conn
    except Exception:
        # 事务处于 aborted 时，ROLLBACK TO SAVEPOINT 是少数仍被允许执行的命令
        raw.execute(f"ROLLBACK TO SAVEPOINT {name}")
        raise
    raw.execute(f"RELEASE SAVEPOINT {name}")


# ─── 建表语句 ───

_SCHEMA = """
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

CREATE TABLE IF NOT EXISTS provider_health (
    kind TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    successes BIGINT NOT NULL DEFAULT 0,
    failures BIGINT NOT NULL DEFAULT 0,
    fallback_calls BIGINT NOT NULL DEFAULT 0,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    cooldown_until DOUBLE PRECISION NOT NULL DEFAULT 0,
    probe_until DOUBLE PRECISION NOT NULL DEFAULT 0,
    total_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
    last_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
    last_status TEXT NOT NULL DEFAULT '',
    updated_at DOUBLE PRECISION NOT NULL DEFAULT 0,
    PRIMARY KEY (kind, profile_id, fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_provider_health_updated ON provider_health(updated_at);

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
CREATE INDEX IF NOT EXISTS idx_feedbacks_user_id ON feedbacks(user_id);
CREATE INDEX IF NOT EXISTS idx_feedbacks_game_id ON feedbacks(game_id);
CREATE INDEX IF NOT EXISTS idx_user_templates_user_id ON user_templates(user_id);
CREATE INDEX IF NOT EXISTS idx_user_templates_created_at ON user_templates(created_at DESC);
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

                settings = get_settings()
                url = _database_url()
                min_size = max(1, min(settings.db_pool_min, settings.db_pool_max))
                pool = ConnectionPool(
                    url,
                    min_size=min_size,
                    max_size=settings.db_pool_max,
                    timeout=settings.db_pool_timeout,  # 池耗尽时最多等多久
                    check=ConnectionPool.check_connection,
                    open=False,
                    kwargs={
                        "row_factory": _pg_row_factory,
                        "connect_timeout": 10,
                        "options": _connection_options(url, settings),
                    },
                )
                pool.open(wait=True, timeout=30)
                _pg_pool = pool
                logger.info(
                    "PostgreSQL 连接池已就绪（min=%d, max=%d, statement_timeout=%dms, lock_timeout=%dms, idle_in_transaction=%dms）",
                    min_size, settings.db_pool_max, settings.db_statement_timeout_ms,
                    settings.db_lock_timeout_ms, settings.db_idle_in_transaction_timeout_ms,
                )
    return _pg_pool


def _connection_options(url: str, settings) -> str:
    """拼出 libpq 的 options 参数：服务端会话级超时，连接建立时即生效、无需额外往返。

    DSN 里可能已经带了 options（测试用 -csearch_path=xxx 做 schema 隔离），
    kwargs 会整体覆盖同名参数，所以必须把两者合并而不是直接替换。
    """
    from psycopg.conninfo import conninfo_to_dict

    try:
        existing = str(conninfo_to_dict(url).get("options") or "")
    except Exception:
        existing = ""
    extra = (
        f"-c statement_timeout={int(settings.db_statement_timeout_ms)} "
        f"-c lock_timeout={int(settings.db_lock_timeout_ms)} "
        f"-c idle_in_transaction_session_timeout={int(settings.db_idle_in_transaction_timeout_ms)}"
    )
    return f"{existing} {extra}".strip()


_pool_stats_sampled_at = 0.0


def _sample_pool_metrics(pool, *, returning: bool = False) -> None:
    """把池占用情况写进 Prometheus 指标，最多每秒采样一次。

    pool.get_stats() 要拿池锁并拷一份计数字典；每次取/还连接都调两次纯属浪费，
    指标本身也只是秒级刷新。多线程同时进来最多重复采样一次，无需加锁。
    """
    global _pool_stats_sampled_at
    now = time.monotonic()
    if now - _pool_stats_sampled_at < 1.0:
        return
    _pool_stats_sampled_at = now
    from app.metrics import update_db_pool_metrics

    stats = pool.get_stats()
    size, available = stats.get("pool_size", 0), stats.get("pool_available", 0)
    if returning:
        # finally 里连接尚未归还，按"即将归还"修正一格
        update_db_pool_metrics(max(0, size - available - 1), available + 1)
    else:
        update_db_pool_metrics(max(0, size - available), available)


def close_pg_pool() -> None:
    """应用关停时释放连接池。"""
    global _pg_pool
    with _pg_pool_lock:
        if _pg_pool is not None:
            _pg_pool.close()
            _pg_pool = None


# Keep related transactions in one domain. Mixed operations acquire all required
# domains in this fixed order; never acquire another domain in a nested db().


@contextmanager
def db(serialized: bool | str | tuple[str, ...] = False, *, content_user: str | None = None, ddl: bool = False):
    """从连接池取连接；正常退出 commit，异常回滚（连接归还池时自动清理）。

    True 兼容内容域；字符串指定业务域，元组用于跨域事务。
    事务锁跨 worker 生效，固定排序避免交叉获取锁导致死锁。
    ddl=True 仅供启动建表：解除本事务的 statement/lock 超时——大表补索引可能远超 30s，
    多 worker 同时启动时排队等 schema 锁也不该被 lock_timeout 打断。
    """
    from app.db_admission import admission
    from app.metrics import db_wait
    scopes = ("content",) if serialized is True else (serialized,) if isinstance(serialized, str) else serialized or ()
    timeout = 30.0 if ddl else max(0.1, get_settings().db_lock_timeout_ms / 1000)
    pool = _get_pg_pool()
    started = time.perf_counter()
    with admission(tuple(scopes), content_user, timeout), pool.connection() as conn:
        db_wait.labels("pool").observe(time.perf_counter() - started)
        _sample_pool_metrics(pool)
        started = time.perf_counter()
        if ddl:
            conn.execute("SET LOCAL statement_timeout = 0")
            conn.execute("SET LOCAL lock_timeout = '30s'")
        scopes = ("content",) if serialized is True else (serialized,) if isinstance(serialized, str) else serialized or ()
        locks = {_LOCK_IDS[scope]: False for scope in scopes}
        if content_user is not None:
            locks.setdefault(_LOCK_IDS["content"], True)
        for lock_id, shared in sorted(locks.items()):
            function = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
            conn.execute(f"SELECT {function}(%s)", (lock_id,))
        if content_user is not None:
            user_key = int.from_bytes(sha256(str(content_user).encode()).digest()[:4], signed=True)
            conn.execute("SELECT pg_advisory_xact_lock(%s, %s)", (_LOCK_IDS["content"], user_key))
        db_wait.labels("lock").observe(time.perf_counter() - started)
        try:
            yield _PgConn(conn)
            conn.commit()
        finally:
            _sample_pool_metrics(pool, returning=True)
    # 仅独占域写入会改动公开元数据（标签、分类、Banner、字典）；content_user 只取
    # 共享内容锁并写用户表，不会改这些表，无需在此清空进程级公开缓存。
    if scopes:
        from app.public_cache import invalidate
        invalidate()


def database_ready() -> bool:
    """Probe the existing pool only: bounded acquisition and SQL execution."""
    pool = _pg_pool
    if pool is None:
        return False
    try:
        with pool.connection(timeout=1) as conn:
            conn.execute("SET LOCAL statement_timeout = '1000ms'")
            row = conn.execute("SELECT 1").fetchone()
            return row is not None and row[0] == 1
    except Exception:
        return False


def _migrate_pg(conn) -> None:
    """存量库补列（方案B初期建的 users 表没有 role/is_active/token_valid_after）。"""
    cols = {
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'users' AND table_schema = current_schema()"
        ).fetchall()
    }
    if "role" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        logger.info("迁移：users 表新增 role 列")
    if "is_active" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        logger.info("迁移：users 表新增 is_active 列")
    if "token_valid_after" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN token_valid_after INTEGER NOT NULL DEFAULT 0")
        logger.info("迁移：users 表新增 token_valid_after 列（改密吊销旧会话）")


def _init_reliability_schema(conn) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS generation_requests (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            request_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at BIGINT NOT NULL,
            finished_at BIGINT NOT NULL DEFAULT 0,
            result_json TEXT NOT NULL DEFAULT '',
            error_json TEXT NOT NULL DEFAULT '',
            error_status INTEGER NOT NULL DEFAULT 0,
            model_calls INTEGER NOT NULL DEFAULT 0,
            reported_calls INTEGER NOT NULL DEFAULT 0,
            prompt_tokens BIGINT NOT NULL DEFAULT 0,
            completion_tokens BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, request_id)
        );
        ALTER TABLE generation_requests ADD COLUMN IF NOT EXISTS lease_expires_at BIGINT NOT NULL DEFAULT 0;
        ALTER TABLE generation_requests ADD COLUMN IF NOT EXISTS instance_id TEXT NOT NULL DEFAULT '';
        CREATE TABLE IF NOT EXISTS generation_budget (
            id TEXT PRIMARY KEY, created_at BIGINT NOT NULL, tokens BIGINT NOT NULL, images INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_generation_budget_time ON generation_budget(created_at);
        CREATE INDEX IF NOT EXISTS idx_generation_created ON generation_requests(created_at);
        CREATE INDEX IF NOT EXISTS idx_generation_status ON generation_requests(status, created_at);
        CREATE INDEX IF NOT EXISTS idx_generation_user_created ON generation_requests(user_id, created_at);
        CREATE TABLE IF NOT EXISTS template_revision_counters (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            revision BIGINT NOT NULL
        );
    """)
    conn.execute("ALTER TABLE user_templates ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 1")


# 建表流程出问题时（例如上面 savepoint 那类坑）必须能在日志里看出来，
# 抽查几张跨模块的核心表，缺任何一张都说明整个 DDL 事务其实被回滚了。
_CORE_TABLES = (
    "users",
    "generation_requests",
    "provider_health",
    "paper_archives",
    "catalog_papers",
    "catalog_popularity",
    "mini_users",
    "mini_catalog_favorites",
    "mini_usage_events",
    "site_dictionary",
    "site_dict_links",
    "mini_orders",
    "mini_membership_grants",
)


def _verify_schema(conn) -> tuple[list, int]:
    """返回 (缺失的核心表, 当前 schema 表总数)。"""
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()"
    ).fetchall()
    present = {row[0] for row in rows}
    return [t for t in _CORE_TABLES if t not in present], len(present)


SCHEMA_VERSION = 2026102701


def init_db(*, migrate: bool | None = None) -> None:
    from app.commerce_schema import init_commerce_schema
    from app.db_indexes import add_optimization_indexes, add_search_indexes
    from app.engagement_schema import init_engagement_schema
    from app.experience_schema import init_experience_schema
    from app.library_schema import init_library_schema
    from app.maintenance_schema import init_maintenance_schema
    from app.site_schema import init_site_schema

    migrate = get_settings().db_auto_migrate if migrate is None else migrate
    with db() as conn:
        exists = conn.execute("SELECT to_regclass('schema_migrations')").fetchone()[0]
        current = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0] if exists else 0
    if current == SCHEMA_VERSION:
        return
    if current > SCHEMA_VERSION:
        raise RuntimeError("数据库版本高于应用；请使用兼容版本回滚")
    if not migrate:
        raise RuntimeError("数据库版本未就绪；请先运行 python -m app.migrations")
    # 只有迁移进程运行 DDL；其他 worker 获取锁后再次校验版本。
    with db(serialized=tuple(_LOCK_IDS), ddl=True) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version BIGINT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
        if conn.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (SCHEMA_VERSION,)).fetchone():
            return
        conn.executescript(_SCHEMA)
        _migrate_pg(conn)
        _init_reliability_schema(conn)
        init_library_schema(conn)
        init_site_schema(conn)
        init_experience_schema(conn)
        init_engagement_schema(conn)
        init_commerce_schema(conn)
        from app.catalog_popularity_schema import migrate as popularity_schema
        popularity_schema(conn)
        add_optimization_indexes(conn)
        add_search_indexes(conn)
        init_maintenance_schema(conn)
        from app.archive_metadata import migrate as archive_metadata
        archive_metadata(conn)
        from app.services.workspace_sessions import migrate as session_schema
        session_schema(conn)
        conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (SCHEMA_VERSION,))
    # 事务已提交，另起一个连接读真实落库结果（不是"没抛异常"就算成功）
    with db() as conn:
        missing, total = _verify_schema(conn)
    if missing:
        logger.error(
            "数据库建表不完整：缺失 %s（当前共 %d 张表）。"
            "通常意味着 init_db() 的 DDL 事务中途失败并整体回滚，请查上面的告警日志。",
            ", ".join(missing),
            total,
        )
    logger.info("PostgreSQL 数据库就绪（%d 张表）", total)
