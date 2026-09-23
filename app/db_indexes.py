"""数据库索引优化脚本

为常见查询模式补索引，在 init_db() 中调用。

⚠️ 两个必须遵守的约束（都踩过坑）：

1) 每条索引必须跑在 SAVEPOINT 里（见 app.db.savepoint）。
   这些语句和 init_db() 的建表共用同一个大事务。PostgreSQL 中一条语句失败会让
   整个事务进入 aborted，后续语句全部 InFailedSqlTransaction，commit 最终退化成
   ROLLBACK —— 原先用 `try/except: pass` 包住"表可能不存在"的语句，
   结果整库建表被一起回滚，日志却说"PostgreSQL 数据库就绪"，库里只剩 users 等几张表。
   空库首次部署必现；已有库（表早就建好）看不出问题，所以很容易漏到线上。

2) 索引指向的表名/列名必须真实存在，删表改名时要同步清理这里。
   历史遗留：曾引用了 commerce_orders / membership_ledger（真实表名是
   mini_orders / mini_membership_grants）和 catalog_papers.grade/subject
   （这两列在 paper_archives 上），即本次事故的直接触发点。

另外：已经被 UNIQUE 约束或别处索引覆盖的列不重复建（PG 对 UNIQUE 会自动建唯一索引），
同名索引不要在两处用不同定义声明 —— `CREATE INDEX IF NOT EXISTS` 只比对名字，
定义不同会静默跳过，留下难以察觉的偏差。
"""

import logging

from app.db import savepoint

logger = logging.getLogger(__name__)

# (索引名, 建索引语句) —— 按表分组，只保留真正有查询价值且不重复的
_INDEXES = (
    # 生成历史：按用户 + 状态回溯（PK 是 (user_id, request_id)，此索引覆盖 status 过滤 + 时间倒序）
    (
        "idx_generation_user_status",
        "CREATE INDEX IF NOT EXISTS idx_generation_user_status "
        "ON generation_requests(user_id, status, created_at DESC)",
    ),
    # 收藏：小程序端按用户取最近收藏（PK 是 (user_id, catalog_id)，排序需要带上 created_at）
    (
        "idx_favorites_user",
        "CREATE INDEX IF NOT EXISTS idx_favorites_user "
        "ON mini_catalog_favorites(user_id, created_at DESC)",
    ),
    # 使用事件：按用户查明细 / 按类型统计
    (
        "idx_usage_events_user",
        "CREATE INDEX IF NOT EXISTS idx_usage_events_user "
        "ON mini_usage_events(user_id, created_at DESC)",
    ),
    (
        "idx_usage_events_kind",
        "CREATE INDEX IF NOT EXISTS idx_usage_events_kind "
        "ON mini_usage_events(kind, created_at DESC)",
    ),
    # 字典关联：按子节点（科目）反查父节点（年级）；parent_id 已是主键首列，无需再建
    (
        "idx_dict_links_child",
        "CREATE INDEX IF NOT EXISTS idx_dict_links_child ON site_dict_links(child_id)",
    ),
    # 小程序会话：后台任务按 expires_at 分批清理过期会话（登录路径不再全表扫）
    (
        "idx_mini_sessions_expires",
        "CREATE INDEX IF NOT EXISTS idx_mini_sessions_expires ON mini_user_sessions(expires_at)",
    ),
)


def add_optimization_indexes(conn):
    """为常见查询模式添加优化索引（幂等；单条失败不影响 init_db 的其他建表）。"""
    failed = []
    for name, statement in _INDEXES:
        try:
            with savepoint(conn):
                conn.execute(statement)
        except Exception as exc:  # noqa: BLE001 — 索引是非关键路径，不该拖垮启动
            failed.append(name)
            logger.warning("索引 %s 创建失败，已跳过：%s", name, exc)
    if failed:
        logger.warning("本次跳过的索引：%s（请核对表/列名是否已变更）", ", ".join(failed))
    else:
        logger.info("优化索引就绪（%d 条）", len(_INDEXES))


def add_search_indexes(conn):
    # Optional on managed databases without extension privileges; the query remains correct.
    try:
        with savepoint(conn):
            conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            for table, column in (("catalog_papers", "title"), ("catalog_papers", "category"), ("paper_archives", "keyword")):
                conn.execute(f"CREATE INDEX IF NOT EXISTS idx_search_{table}_{column} ON {table} USING gin (LOWER({column}) gin_trgm_ops)")
    except Exception:
        logger.warning("Trigram indexes unavailable; ask the database administrator to enable pg_trgm")
