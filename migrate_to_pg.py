"""SQLite → PostgreSQL 数据迁移脚本

前提：
1. PostgreSQL 已启动（如 docker compose up -d）
2. .env 已配置 DATABASE_URL=postgresql://...
3. 旧 SQLite 库在默认位置（data/users.db）或用 --sqlite 指定

用法：
    python migrate_to_pg.py
    python migrate_to_pg.py --sqlite path/to/users.db

行为：幂等——重复执行不会产生重复数据（按主键/upsert 去重）。
迁移完成后重启服务即切换到 PostgreSQL。
"""

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import get_settings  # noqa: E402
from app.db import _use_pg, init_db  # noqa: E402

TABLES = ["users", "user_llm_configs", "user_templates", "app_config", "feedbacks"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sqlite",
        default=str(Path(__file__).resolve().parent / "data" / "users.db"),
        help="旧 SQLite 数据库路径",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not _use_pg():
        print("❌ .env 里尚未配置 DATABASE_URL（postgresql://...），先配置再运行本脚本")
        return 1
    src_path = Path(args.sqlite)
    if not src_path.exists():
        print(f"❌ SQLite 源库不存在: {src_path}")
        return 1

    print(f"▶ 目标 PostgreSQL: {settings.database_url.rsplit('@', 1)[-1]}")
    print(f"▶ 源 SQLite:      {src_path}")

    init_db()  # 确保 PG 表结构就绪
    from app.db import db as pg_db

    src = sqlite3.connect(src_path)
    src.row_factory = sqlite3.Row

    total = 0
    with pg_db() as dst:
        for table in TABLES:
            try:
                rows = src.execute(f"SELECT * FROM {table}").fetchall()
            except sqlite3.OperationalError:
                print(f"  - {table}: 源库无此表，跳过")
                continue
            if not rows:
                print(f"  - {table}: 0 行")
                continue
            cols = list(rows[0].keys())
            placeholders = ", ".join(["?"] * len(cols))
            col_list = ", ".join(cols)
            n = 0
            for row in rows:
                dst.execute(
                    f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
                    f"ON CONFLICT DO NOTHING",
                    tuple(row[c] for c in cols),
                )
                n += 1
            total += n
            print(f"  - {table}: {n} 行")

        # 重置序列，让新插入的 id 从现有最大值之后继续
        for table, col in [("users", "id"), ("user_templates", "id"), ("feedbacks", "id")]:
            dst.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', '{col}'), "
                f"COALESCE((SELECT MAX({col}) FROM {table}), 0) + 1, false)"
            )

    src.close()
    print(f"✅ 迁移完成，共 {total} 行。重启服务即切换到 PostgreSQL。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
