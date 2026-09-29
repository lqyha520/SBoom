"""进程内滑动窗口限流（无第三方依赖）

适用场景：登录防爆破、注册防刷、反馈防灌水。
说明：多 worker 部署时各进程独立计数，仍能显著抬高攻击成本；
若需要精确全局限流，可替换为 Redis 实现（接口保持不变）。
"""

import threading
import time
from collections import deque
from heapq import heappop, heappush
from ipaddress import ip_address, ip_network
from math import isfinite

_lock = threading.Lock()
_MAX_KEYS = 10_000
_CLEANUP_BATCH = 64
# Include the policy so a short window cannot discard a longer window's history.
_Policy = tuple[str, int, float]
_hits: dict[_Policy, deque[float]] = {}
# One scheduled check per policy, even when that policy receives many requests.
_expirations: list[tuple[float, _Policy]] = []


def client_key(host: str) -> str:
    """IPv6 临时地址按 /64 聚合，IPv4 映射地址与 IPv4 共用计数。"""
    try:
        address = ip_address(host)
        if address.version == 6:
            mapped = getattr(address, "ipv4_mapped", None)
            return str(mapped or ip_network(f"{address}/64", strict=False))
        return str(address)
    except ValueError:
        return host


def _cleanup(now: float) -> None:
    for _ in range(_CLEANUP_BATCH):
        if not _expirations or _expirations[0][0] > now:
            break
        _, policy = heappop(_expirations)
        if policy not in _hits:
            continue
        expires = _hits[policy][-1] + policy[2]
        if expires <= now:
            del _hits[policy]
        else:
            heappush(_expirations, (expires, policy))


def allow(key: str, max_events: int, per_seconds: float) -> bool:
    """在 per_seconds 窗口内该 key 已发生 max_events 次则拒绝。

    窗口左边界不计入；拒绝请求不会延长窗口。
    每次最多清理 64 个到期条目，最多保留 10,000 个 key/策略组合。
    满时淘汰最早调度的条目，避免阻断全站新用户。
    """
    if max_events < 1 or not isfinite(per_seconds) or per_seconds <= 0:
        raise ValueError("Rate limit count and window must be positive and finite")
    policy = (key, max_events, per_seconds)
    with _lock:
        now = time.monotonic()
        _cleanup(now)
        q = _hits.get(policy)
        if q is None:
            if len(_hits) >= _MAX_KEYS:
                # 每个键只有一个到期索引；O(log N) 淘汰最早调度的键。
                _, victim = heappop(_expirations)
                del _hits[victim]
            q = deque()
            _hits[policy] = q
            heappush(_expirations, (now + per_seconds, policy))
        while q and now - q[0] >= per_seconds:
            q.popleft()
        if len(q) >= max_events:
            return False
        q.append(now)
        return True
