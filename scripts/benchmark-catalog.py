"""Synthetic 10k/100k EXPLAIN baselines; always uses disposable local PostgreSQL."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pg_support

os.environ["DATABASE_URL"] = pg_support.install_module_database()
from app.db import close_pg_pool, db, init_db

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts/catalog-benchmark.json")
results = []
try:
    init_db()
    with db() as conn:
        # init_db installs the new indexes; remove them only inside this disposable
        # benchmark database so the baseline remains reproducible after this change.
        for table, column in [('catalog_papers','title'),('catalog_papers','category'),('paper_archives','keyword')]:
            conn.execute(f"DROP INDEX IF EXISTS idx_search_{table}_{column}")
    with db() as conn:
        conn.execute("INSERT INTO users(id, username, password_hash) VALUES (1, 'benchmark', 'unusable')")
        conn.execute("INSERT INTO mini_users(id, username, created_at, updated_at) VALUES ('benchmark', 'benchmark', 1, 1)")
    for count in (10000, 100000):
        with db() as conn:
            conn.execute("TRUNCATE paper_archives CASCADE")
            conn.execute("INSERT INTO paper_archives(id, user_id, source_id, request_id, content_hash, version, title, grade, subject, keyword, question_count, snapshot_json, file_status, created_at, updated_at) SELECT i::text, 1, i::text, i::text, i::text, 1, 'Paper ' || i, 'Grade3', 'Math', CASE WHEN i % 100 = 0 THEN 'fractions' ELSE 'addition' END, 10, '{}', 'ready', i, i FROM generate_series(1, ?) i", (count,))
            conn.execute("INSERT INTO catalog_papers(id, paper_id, publisher_id, title, status, created_at, updated_at, published_at) SELECT i::text, i::text, 1, 'Practice ' || i, 'published', i, i, i FROM generate_series(1, ?) i", (count,))
            conn.execute("INSERT INTO mini_catalog_favorites(user_id, catalog_id, created_at) SELECT 'benchmark', i::text, i FROM generate_series(1, ?) i WHERE i % 3 = 0", (count,))
            conn.execute("INSERT INTO mini_catalog_downloads(user_id, catalog_id, requested_at) SELECT 'benchmark', i::text, i FROM generate_series(1, ?) i WHERE i % 5 = 0", (count,))
            conn.execute("ANALYZE paper_archives")
            conn.execute("ANALYZE catalog_papers")
            conn.execute("ANALYZE mini_catalog_favorites")
            conn.execute("ANALYZE mini_catalog_downloads")
            queries = {
                'popular_correlated': "SELECT c.id FROM catalog_papers c JOIN paper_archives a ON a.id=c.paper_id WHERE c.status='published' AND a.file_status='ready' ORDER BY ((SELECT COUNT(*) FROM mini_catalog_favorites WHERE catalog_id=c.id)+(SELECT COUNT(*) FROM mini_catalog_downloads WHERE catalog_id=c.id)) DESC,c.published_at DESC,c.id DESC LIMIT 20",
                'popular_aggregate': "SELECT c.id FROM catalog_papers c JOIN paper_archives a ON a.id=c.paper_id LEFT JOIN (SELECT catalog_id, COUNT(*) n FROM mini_catalog_favorites GROUP BY catalog_id) f ON f.catalog_id=c.id LEFT JOIN (SELECT catalog_id, COUNT(*) n FROM mini_catalog_downloads GROUP BY catalog_id) d ON d.catalog_id=c.id WHERE c.status='published' AND a.file_status='ready' ORDER BY (COALESCE(f.n,0)+COALESCE(d.n,0)) DESC,c.published_at DESC,c.id DESC LIMIT 20",
                'search_or': "SELECT c.id FROM catalog_papers c JOIN paper_archives a ON a.id=c.paper_id WHERE LOWER(c.title) LIKE '%fractions%' OR LOWER(c.category) LIKE '%fractions%' OR LOWER(a.keyword) LIKE '%fractions%'",
                'search_union': "SELECT c.id FROM catalog_papers c JOIN paper_archives a ON a.id=c.paper_id WHERE c.id IN (SELECT id FROM catalog_papers WHERE LOWER(title) LIKE '%fractions%' OR LOWER(category) LIKE '%fractions%' UNION SELECT c2.id FROM catalog_papers c2 JOIN paper_archives a2 ON a2.id=c2.paper_id WHERE LOWER(a2.keyword) LIKE '%fractions%')"
            }
            for indexed in (False, True):
                if indexed:
                    conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
                    for table, column in [('catalog_papers','title'),('catalog_papers','category'),('paper_archives','keyword')]:
                        conn.execute(f"CREATE INDEX IF NOT EXISTS bench_{table}_{column} ON {table} USING gin (LOWER({column}) gin_trgm_ops)")
                for name, query in queries.items():
                    if indexed and not name.startswith('search'):
                        continue
                    plans = [conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query).fetchone()[0][0] for _ in range(3)]
                    results.append({'rows': count, 'query': name, 'indexed': indexed, 'milliseconds': [p['Execution Time'] for p in plans], 'plan': plans[-1]})
                if not indexed:
                    same = conn.execute(queries['popular_correlated']).fetchall() == conn.execute(queries['popular_aggregate']).fetchall()
                    assert same, 'popular order changed'
            # Next scale must start without the candidate indexes.
            for table, column in [('catalog_papers','title'),('catalog_papers','category'),('paper_archives','keyword')]:
                conn.execute(f"DROP INDEX bench_{table}_{column}")
        print('benchmarked', count, flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding='utf-8')
finally:
    close_pg_pool()
