"""PostgreSQL 测试支撑：一次性测试库 + per-case schema 隔离。

- 管理连接默认指向本机 learncoach-db 容器（127.0.0.1:5432，learncoach/learncoach），
  可用环境变量 LC_TEST_PG_ADMIN 覆盖。
- 安全护栏：只允许本地实例；只创建/删除 lc_test_ 前缀的一次性库；
  绝不触碰业务库（learncoach、lc_verify* 等一律拒绝）。
- install_module_database() 供"模块顶层 os.environ.update"风格的测试文件
  在 import app 之前调用；case_database() 供 per-case 的 setUp 使用
  （与 postgres_experience.py 的 schema 隔离模式一致）。
"""

import atexit
import os
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

ADMIN_DSN = os.environ.get("LC_TEST_PG_ADMIN", "postgresql://learncoach:learncoach@127.0.0.1:5432/postgres")

_LOCAL_HOSTS = ("127.0.0.1", "localhost")


def _guard(dsn: str, *, dbname_prefix: str | None = None) -> str:
    """校验 dsn：host 必须本地，库名必须以指定前缀开头（防止误删业务库）。"""
    config = conninfo_to_dict(dsn)
    if config.get("host", "") not in _LOCAL_HOSTS:
        raise RuntimeError(f"PG 测试只允许本地实例，拒绝连接: {config.get('host')!r}")
    dbname = config.get("dbname", "")
    if dbname_prefix and not dbname.startswith(dbname_prefix):
        raise RuntimeError(f"只允许操作 {dbname_prefix}* 前缀的一次性库，拒绝: {dbname!r}")
    return dbname


def _admin_connect():
    _guard(ADMIN_DSN)
    return psycopg.connect(ADMIN_DSN, autocommit=True, connect_timeout=10)


def create_test_db(prefix: str = "lc_test_") -> tuple[str, str]:
    """建一个一次性测试库，返回 (库 DSN, 库名)。"""
    _guard(ADMIN_DSN)
    name = prefix + uuid.uuid4().hex[:10]
    with _admin_connect() as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    parts = urlsplit(ADMIN_DSN)
    dsn = urlunsplit((parts.scheme, parts.netloc, "/" + name, "", ""))
    return dsn, name


def drop_test_db(name: str) -> None:
    """删除一次性测试库（只接受 lc_test_ 前缀）。"""
    if not name.startswith("lc_test_"):
        raise RuntimeError(f"只允许删除 lc_test_* 前缀的一次性库，拒绝: {name!r}")
    _guard(ADMIN_DSN)
    with _admin_connect() as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


def is_disposable_db(dsn: str) -> bool:
    """dsn 是否指向本机 lc_test_ 前缀的一次性测试库（供 demo 种子等防呆检查用）。"""
    try:
        _guard(dsn, dbname_prefix="lc_test_")
        return True
    except RuntimeError:
        return False


def install_module_database(env_updates: dict | None = None) -> str:
    """模块导入期调用：建一次性库写入 DATABASE_URL，进程退出时删除。

    替代旧的 os.environ.update({"DATABASE_URL": "", ...})（强制 SQLite）模式，
    保证测试进程无论 .env 里配了什么，都落到一次性库上。
    幂等：多个测试模块先后调用时复用同一个一次性库（case 间由 case_database 的 schema 隔离）。
    """
    existing = os.environ.get("DATABASE_URL", "")
    if existing:
        try:
            _guard(existing, dbname_prefix="lc_test_")
            for key, value in (env_updates or {}).items():
                os.environ.setdefault(key, value)
            return existing  # 已指向一次性测试库，直接复用
        except RuntimeError:
            pass
    dsn, name = create_test_db()
    atexit.register(drop_test_db, name)
    os.environ["DATABASE_URL"] = dsn
    for key in ("LC_TEST_PG_DSN",):
        os.environ.pop(key, None)
    if env_updates:
        os.environ.update(env_updates)
    return dsn


def case_database(stack) -> str:
    """per-case 隔离：在模块库内建独立 schema，patch database_url 指向它。

    stack: 测试的 ExitStack（self.stack）。返回带 search_path 的 case DSN。
    用法（setUp 内）：
        pg_support.case_database(self.stack)   # 之后即可 database.init_db()
    """
    from unittest.mock import patch

    from app import db as database
    from app.config import get_settings

    module_dsn = os.environ.get("DATABASE_URL", "")
    _guard(module_dsn, dbname_prefix="lc_test_")
    base = urlsplit(module_dsn)
    schema = "case_" + uuid.uuid4().hex
    with psycopg.connect(module_dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    query = dict(parse_qsl(base.query))
    query["options"] = "-csearch_path=" + schema
    dsn = base._replace(query=urlencode(query)).geturl()

    def cleanup():
        database.close_pg_pool()
        try:
            with psycopg.connect(module_dsn, autocommit=True) as conn:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        except Exception:
            pass

    stack.callback(cleanup)
    # 连接池按 DSN options 建连接：换 schema 前必须先关旧池，避免复用旧 search_path 连接
    database.close_pg_pool()
    stack.enter_context(patch.object(get_settings(), "database_url", dsn))
    return dsn
