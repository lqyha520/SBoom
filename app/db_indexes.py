"""数据库索引优化脚本

分析常见查询模式并添加缺失的索引。
在 init_db() 中调用此函数。
"""


def add_optimization_indexes(conn):
    """为常见查询模式添加优化索引"""

    # generation_requests 表：按用户查询历史、按状态查询待处理
    try:
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_generation_user_status
            ON generation_requests(user_id, status, created_at DESC)
        """)
    except Exception:
        pass  # 表可能不存在

    # mini_users 表：按用户名查询
    try:
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mini_users_username
            ON mini_users(username)
        """)
    except Exception:
        pass

    # catalog_papers 表：按发布状态查询、按年级科目查询
    try:
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_catalog_status
            ON catalog_papers(status, updated_at DESC)
        """)
    except Exception:
        pass

    try:
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_catalog_grade_subject
            ON catalog_papers(grade, subject, status)
        """)
    except Exception:
        pass

    # mini_catalog_favorites 表：按用户查询收藏
    try:
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_favorites_user
            ON mini_catalog_favorites(user_id, created_at DESC)
        """)
    except Exception:
        pass

    # mini_usage_events 表：按用户查询使用记录
    try:
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_usage_events_user
            ON mini_usage_events(user_id, created_at DESC)
        """)
    except Exception:
        pass

    # mini_usage_events 表：按类型查询统计
    try:
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_usage_events_kind
            ON mini_usage_events(kind, created_at DESC)
        """)
    except Exception:
        pass

    # site_dictionary 表：按 kind 和可见性查询
    try:
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dict_kind_visible
            ON site_dictionary(kind, is_visible, sort_order)
        """)
    except Exception:
        pass

    # site_dict_links 表：按父节点查询子节点
    try:
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dict_links_parent
            ON site_dict_links(parent_id)
        """)
    except Exception:
        pass

    # site_dict_links 表：按子节点查询父节点
    try:
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dict_links_child
            ON site_dict_links(child_id)
        """)
    except Exception:
        pass

    # commerce_orders 表：按用户查询订单
    try:
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_user
            ON commerce_orders(user_id, created_at DESC)
        """)
    except Exception:
        pass

    # commerce_orders 表：按状态查询
    try:
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_status
            ON commerce_orders(status, created_at DESC)
        """)
    except Exception:
        pass

    # membership_ledger 表：按用户查询会员记录
    try:
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ledger_user
            ON membership_ledger(user_id, valid_until DESC)
        """)
    except Exception:
        pass

    # membership_ledger 表：按状态查询
    try:
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ledger_status
            ON membership_ledger(status, created_at DESC)
        """)
    except Exception:
        pass
