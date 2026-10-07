"""收藏与下载用户数在同一事务内维护，热门查询只读取汇总。"""


def migrate(conn) -> None:
    exists = conn.execute("SELECT to_regclass('catalog_popularity')").fetchone()[0]
    conn.execute("LOCK TABLE mini_catalog_favorites, mini_catalog_downloads IN SHARE ROW EXCLUSIVE MODE")
    conn.execute("""CREATE TABLE IF NOT EXISTS catalog_popularity (
        catalog_id TEXT PRIMARY KEY REFERENCES catalog_papers(id) ON DELETE CASCADE,
        favorite_count BIGINT NOT NULL DEFAULT 0 CHECK (favorite_count >= 0),
        download_users BIGINT NOT NULL DEFAULT 0 CHECK (download_users >= 0)
    )""")
    if not exists:
        conn.execute("""INSERT INTO catalog_popularity(catalog_id, favorite_count, download_users)
            SELECT c.id, COALESCE(f.n, 0), COALESCE(d.n, 0) FROM catalog_papers c
            LEFT JOIN (SELECT catalog_id, COUNT(*) n FROM mini_catalog_favorites GROUP BY catalog_id) f ON f.catalog_id = c.id
            LEFT JOIN (SELECT catalog_id, COUNT(*) n FROM mini_catalog_downloads GROUP BY catalog_id) d ON d.catalog_id = c.id""")
    for table, column in (("mini_catalog_favorites", "favorite_count"), ("mini_catalog_downloads", "download_users")):
        for event, transition, changes in (
            ("INSERT", "NEW TABLE AS new_rows", "SELECT catalog_id, COUNT(*) AS delta FROM new_rows GROUP BY catalog_id"),
            ("DELETE", "OLD TABLE AS old_rows", "SELECT catalog_id, -COUNT(*) AS delta FROM old_rows GROUP BY catalog_id"),
            ("UPDATE", "OLD TABLE AS old_rows NEW TABLE AS new_rows",
             "SELECT catalog_id, SUM(delta) AS delta FROM (SELECT catalog_id, 1 AS delta FROM new_rows "
             "UNION ALL SELECT catalog_id, -1 AS delta FROM old_rows) changes GROUP BY catalog_id HAVING SUM(delta) <> 0"),
        ):
            function = f"{table}_popularity_{event.lower()}"
            # 按资料 ID 加锁，批量操作也保持一致顺序；函数体不能按分号拆分。
            conn.execute(f"""CREATE OR REPLACE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql AS $$
                DECLARE change RECORD;
                BEGIN
                    FOR change IN {changes} ORDER BY catalog_id LOOP
                        IF change.delta > 0 THEN
                            INSERT INTO catalog_popularity(catalog_id, {column}) VALUES (change.catalog_id, change.delta)
                            ON CONFLICT(catalog_id) DO UPDATE SET {column} = catalog_popularity.{column} + EXCLUDED.{column};
                        ELSE
                            UPDATE catalog_popularity SET {column} = {column} + change.delta WHERE catalog_id = change.catalog_id;
                        END IF;
                    END LOOP;
                    RETURN NULL;
                END;
            $$""")
            conn.execute(f"DROP TRIGGER IF EXISTS {function} ON {table}")
            conn.execute(f"CREATE TRIGGER {function} AFTER {event} ON {table} REFERENCING {transition} FOR EACH STATEMENT EXECUTE FUNCTION {function}()")
