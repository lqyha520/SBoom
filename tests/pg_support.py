"""PostgreSQL 测试支撑：一次性测试库 + per-case 隔离（模板库克隆）。

- 管理连接默认指向本机 learncoach-db 容器（127.0.0.1:5432，learncoach/learncoach），
  可用环境变量 LC_TEST_PG_ADMIN 覆盖。
- 安全护栏：只允许本地实例；只创建/删除 lc_test_ 前缀的一次性库；
  绝不触碰业务库（learncoach、lc_verify* 等一律拒绝）。
- install_module_database() 供"模块顶层 os.environ.update"风格的测试文件
  在 import app 之前调用；case_database() 供 per-case 的 setUp 使用。
- 并行（pytest -n auto）：库名带 uuid，每个 worker 进程各自建模块库 / 模板库，
  进程退出时由 atexit 各自清理，进程间没有共享的库名。
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


def _speed_up_password_hashing() -> None:
    """测试进程内把 PBKDF2 迭代数从 240k 降到 1000。

    每个 setUp 都要创建/登录 2-6 个账号，240k 迭代一次约 70ms，全套 300+ case 累计
    要一分钟以上。verify_password 从哈希串里读迭代数，所以降低后仍能自洽校验；
    没有测试断言哈希强度。放在这里（而不是 conftest）是为了让
    `python -m unittest discover` 与 `pytest` 两条路径都生效——每个后端测试模块
    都会（直接或经 test_backend_catalog）先 import 本模块。
    """
    from app import security

    security._PBKDF2_ITER = 1000


_speed_up_password_hashing()


def _guard(dsn: str, *, dbname_prefix: str | None = None) -> str:
    """校验 dsn：host 必须本地，库名必须以指定前缀开头（防止误删业务库）。"""
    config = conninfo_to_dict(dsn)
    if config.get("host", "") not in _LOCAL_HOSTS:
        raise RuntimeError(f"PG 测试只允许本地实例，拒绝连接: {config.get('host')!r}")
    if config.get("hostaddr") not in (None, "127.0.0.1") or config.get("service") or config.get("servicefile"):
        raise RuntimeError("测试 DSN 不允许远程 hostaddr 或连接服务覆盖")
    if config.get("port", "5432") not in ("5432", "55432"):
        raise RuntimeError("测试数据库端口须为本机 5432 或独立测试端口 55432")
    dbname = config.get("dbname", "")
    if dbname_prefix and not dbname.startswith(dbname_prefix):
        raise RuntimeError(f"只允许操作 {dbname_prefix}* 前缀的一次性库，拒绝: {dbname!r}")
    return dbname


def _admin_connect():
    _guard(ADMIN_DSN)
    return psycopg.connect(ADMIN_DSN, autocommit=True, connect_timeout=10)


def _db_dsn(name: str) -> str:
    """用管理 DSN 的 host/port/账号拼出指定库的 DSN。"""
    parts = urlsplit(ADMIN_DSN)
    return urlunsplit((parts.scheme, parts.netloc, "/" + name, "", ""))


def create_test_db(prefix: str = "lc_test_", template: str | None = None) -> tuple[str, str]:
    """建一个一次性测试库，返回 (库 DSN, 库名)。template 给定时从模板库克隆。"""
    _guard(ADMIN_DSN)
    if not prefix.startswith("lc_test_"):
        raise RuntimeError(f"一次性库前缀必须以 lc_test_ 开头，拒绝: {prefix!r}")
    name = prefix + uuid.uuid4().hex[:10]
    with _admin_connect() as conn:
        if template:
            conn.execute(sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(sql.Identifier(name), sql.Identifier(template)))
        else:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    return _db_dsn(name), name


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
    幂等：多个测试模块先后调用时复用同一个一次性库（case 间由 case_database 隔离）。
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


# 进程内的"已 init_db 的模板库"名字；懒创建，供 case_database 克隆。
_template_db: str | None = None


def _template_database() -> str:
    """进程内只跑一次完整 init_db()（约 500ms / 136 条 DDL），之后每个 case 直接
    `CREATE DATABASE ... TEMPLATE` 克隆（约 40ms）。init_db() 只读 database_url，
    不依赖其他 settings，所以模板与各 case 自己跑 init_db 的结果一致；
    setUp 里随后的 database.init_db() 走幂等路径（约 75ms）。
    """
    global _template_db
    if _template_db is None:
        from unittest.mock import patch

        from app import db as database
        from app.config import get_settings

        dsn, name = create_test_db(prefix="lc_test_tpl_")
        atexit.register(drop_test_db, name)
        database.close_pg_pool()
        with patch.object(get_settings(), "database_url", dsn):
            database.init_db()
        # 模板库不能有活动连接，否则 CREATE DATABASE ... TEMPLATE 会报 "being accessed by other users"
        database.close_pg_pool()
        _template_db = name
    return _template_db


def case_database(stack, *, fresh: bool = False) -> str:
    """per-case 隔离：patch database_url 指向一个只属于本 case 的库/schema。

    stack: 测试的 ExitStack（self.stack）。返回 case DSN。
    用法（setUp 内）：
        pg_support.case_database(self.stack)   # 之后即可 database.init_db()

    默认：从进程内模板库克隆一个已建好表的库（快）。
    fresh=True：在模块库内建一个全新的空 schema（慢；只给需要"首次部署空库"
    形态的回归测试用，例如 FreshSchemaContracts）。
    """
    from unittest.mock import patch

    from app import db as database
    from app.config import get_settings

    module_dsn = os.environ.get("DATABASE_URL", "")
    _guard(module_dsn, dbname_prefix="lc_test_")

    if fresh:
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
    else:
        dsn, name = create_test_db(prefix="lc_test_case_", template=_template_database())

        def cleanup():
            database.close_pg_pool()
            try:
                drop_test_db(name)
            except Exception:
                pass

    stack.callback(cleanup)
    # 连接池按 DSN 建连接：换库/schema 前必须先关旧池，避免复用指向旧库的连接
    database.close_pg_pool()
    stack.enter_context(patch.object(get_settings(), "database_url", dsn))
    return dsn


def drain_after_file_grace() -> None:
    """仅测试使用：推进六小时，验证文件物理回收的宽限期。"""
    import time
    from unittest.mock import patch

    from app.services import file_retention
    future = time.time() + 6 * 3600 + 1
    with patch.object(file_retention.time, "time", return_value=future):
        file_retention.drain()
