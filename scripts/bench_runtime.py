"""Compare runtime hotspots with a Git revision, using disposable PostgreSQL data.

python scripts/bench_runtime.py --baseline 10eaa55
LC_TEST_PG_ADMIN has the same local-only safeguards as tests/pg_support.py.
This measures service functions, not HTTP latency or production throughput.
"""

import argparse
import ast
import gc
import json
import statistics
import subprocess
import sys
import time
import tracemalloc
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def source_at(revision, path):
    return subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=ROOT).decode("utf-8")


def rate_benchmark(source):
    namespace = {}
    exec(compile(source, "rate_limit_benchmark", "exec"), namespace)
    allow = namespace["allow"]
    for index in range(10_001):
        allow(f"key-{index}", 100_000, 3600)
    samples = []
    for _ in range(2000):
        started = time.perf_counter()
        assert allow("key-0", 100_000, 3600)
        samples.append((time.perf_counter() - started) * 1_000_000)
    return {"median_us": round(statistics.median(samples), 2),
            "p95_us": round(sorted(samples)[int(len(samples) * .95)], 2),
            "tracked_keys": len(namespace["_hits"])}


def analytics_benchmark(function):
    function()  # warm connection/query caches
    samples = []
    for _ in range(7):
        started = time.perf_counter()
        function()
        samples.append((time.perf_counter() - started) * 1000)
    gc.collect()
    tracemalloc.start()
    try:
        function()
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    return {"median_ms": round(statistics.median(samples), 2),
            "peak_python_mib": round(peak / 1024 / 1024, 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="HEAD", help="Trusted Git revision to compare with the working tree")
    parser.add_argument("--events", type=int, default=50_000)
    args = parser.parse_args()
    if not 1 <= args.events <= 1_000_000:
        parser.error("--events must be between 1 and 1000000")
    baseline_rate = source_at(args.baseline, "app/services/rate_limit.py")
    baseline_analytics = source_at(args.baseline, "app/services/mini_experience.py")
    report = {"baseline": args.baseline, "events": args.events, "rate_limit": {
        "before": rate_benchmark(baseline_rate),
        "after": rate_benchmark((ROOT / "app/services/rate_limit.py").read_text(encoding="utf-8")),
    }}

    import pg_support
    pg_support.install_module_database({"SECRET_KEY": "disposable-runtime-benchmark-secret",
                                        "ADMIN_USERNAME": "", "ADMIN_PASSWORD": "", "LLM_API_KEY": ""})
    from app import db as database
    from app.services import mini_experience

    node = next(node for node in ast.parse(baseline_analytics).body
                if isinstance(node, ast.FunctionDef) and node.name == "usage_analytics")
    namespace = dict(vars(mini_experience))
    exec(compile(ast.Module(body=[node], type_ignores=[]), "analytics_baseline", "exec"), namespace)
    baseline = namespace["usage_analytics"]
    with ExitStack() as stack:
        pg_support.case_database(stack)
        database.init_db()
        today = datetime.now(timezone(timedelta(hours=8))).replace(hour=0, minute=0, second=0, microsecond=0)
        start = int((today - timedelta(days=29)).timestamp())
        with database.db() as conn:
            conn.execute("INSERT INTO mini_users(id, username, created_at, updated_at) "
                         "SELECT 'bench-' || n, 'bench-' || n, 0, 0 FROM generate_series(0, 1999) AS n")
            conn.execute(
                "INSERT INTO mini_usage_events(id, user_id, kind, detail, created_at) "
                "SELECT 'event-' || n, 'bench-' || (n % 2000), "
                "CASE n % 4 WHEN 0 THEN 'active' WHEN 1 THEN 'download_ok' "
                "WHEN 2 THEN 'download_failed' ELSE 'search_miss' END, "
                "'query-' || (n % 25), ?::bigint + (n % 30) * 86400 + 3600 "
                "FROM generate_series(1, ?::integer) AS n", (start, args.events))
            conn.execute("ANALYZE mini_usage_events")
        assert baseline() == mini_experience.usage_analytics(), "Analytics results changed for the benchmark data"
        report["analytics"] = {"before": analytics_benchmark(baseline),
                               "after": analytics_benchmark(mini_experience.usage_analytics)}
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
