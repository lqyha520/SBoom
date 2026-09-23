"""API 性能基线自测（可重复运行，用于回归对比）

用法：
    python scripts/bench_api.py                          # 公开端点（无需登录）
    python scripts/bench_api.py --token lc_reader_xxx    # 追加真实业务端点
    python scripts/bench_api.py --base http://127.0.0.1:8011
    python scripts/bench_api.py --concurrency 50 --total 300

说明：
- 全部为只读 GET，不会修改数据；带 --token 时仅打自己的读接口。
- 本机压测时客户端与服务端抢 CPU，QPS 数字偏保守，重点看「趋势」而不是绝对值。
- 沙箱/代理环境下脚本已自动清空 http_proxy（否则请求会绕道代理）。
"""
import argparse
import asyncio
import os
import statistics
import time

import httpx

for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"

PUBLIC_ENDPOINTS = [
    ("GET /health（纯框架开销）", "/health"),
    ("GET /openapi.json（大 JSON 序列化）", "/openapi.json"),
    ("GET /（index.html）", "/"),
    ("GET /docs（Swagger UI）", "/docs"),
]

READER_ENDPOINTS = [
    ("GET /mini/me", "/api/v1/mini/me"),
    ("GET /site/home（首页聚合）", "/api/v1/site/home"),
    ("GET /site/documents/privacy", "/api/v1/site/documents/privacy"),
    ("GET /catalog/summary", "/api/v1/catalog/summary"),
    ("GET /catalog/papers?limit=20", "/api/v1/catalog/papers?limit=20"),
    ("GET /catalog/papers?limit=50", "/api/v1/catalog/papers?limit=50"),
]


async def one(cli, method, url, headers, timeout=60):
    t0 = time.perf_counter()
    try:
        r = await cli.request(method, url, headers=headers, timeout=timeout)
        return (time.perf_counter() - t0) * 1000, r.status_code, len(r.content)
    except Exception as e:
        return (time.perf_counter() - t0) * 1000, f"ERR:{type(e).__name__}", 0


async def bench(path, base, headers, times):
    async with httpx.AsyncClient(base_url=base) as cli:
        for _ in range(3):  # 预热，避开连接建立与首字节抖动
            await one(cli, "GET", path, headers)
        rows = [await one(cli, "GET", path, headers) for _ in range(times)]
    lat = sorted(r[0] for r in rows)
    codes: dict[str | int, int] = {}
    for r in rows:
        codes[r[1]] = codes.get(r[1], 0) + 1
    def p(q):
        return lat[min(len(lat) - 1, int(len(lat) * q))]
    print(f"{path[:44]:46s} avg={statistics.mean(lat):6.1f}ms p50={p(.5):6.1f} "
          f"p95={p(.95):6.1f} max={lat[-1]:6.1f} | {rows[0][2]/1024:6.1f}KB | {codes}")


async def conc(path, base, headers, concurrency, total):
    """每并发独立 client，避免单连接池成为客户端瓶颈。"""
    lat: list[float] = []
    codes: dict[str | int, int] = {}
    box, lock = [0], asyncio.Lock()

    async def worker():
        async with httpx.AsyncClient(base_url=base) as cli:
            while True:
                async with lock:
                    if box[0] >= total:
                        return
                    box[0] += 1
                dt, code, _ = await one(cli, "GET", path, headers)
                lat.append(dt)
                codes[code] = codes.get(code, 0) + 1

    t0 = time.perf_counter()
    await asyncio.gather(*[worker() for _ in range(concurrency)])
    wall = time.perf_counter() - t0
    lat.sort()
    print(f"{path[:44]:46s} c={concurrency:3d} qps={total/wall:7.1f} "
          f"p50={lat[len(lat)//2]:6.1f}ms p95={lat[int(len(lat)*.95)]:6.1f}ms {codes}")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--token", default="", help="小程序读者 bearer token（可选，启用真实业务端点）")
    ap.add_argument("--times", type=int, default=15, help="单请求重复次数")
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--total", type=int, default=300)
    args = ap.parse_args()

    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    print(f"=== 基线 @ {args.base} ===\n")
    print(f"── 单请求延迟（顺序 {args.times} 次）──")
    for _name, path in PUBLIC_ENDPOINTS + [("GET /api/v1/site/home（未登录 401）", "/api/v1/site/home")]:
        await bench(path, args.base, {}, args.times)
    if headers:
        print("\n── 真实业务接口（鉴权 + DB 查询）──")
        for _, path in READER_ENDPOINTS:
            await bench(path, args.base, headers, args.times)

    print("\n── 并发吞吐 ──")
    await conc("/health", args.base, {}, args.concurrency, args.total)
    target = "/api/v1/catalog/papers?limit=20" if headers else "/api/v1/site/home"
    await conc(target, args.base, headers, args.concurrency, args.total)


if __name__ == "__main__":
    asyncio.run(main())
