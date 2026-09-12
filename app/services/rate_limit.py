"""进程内滑动窗口限流（无第三方依赖）

适用场景：登录防爆破、注册防刷、反馈防灌水。
说明：多 worker 部署时各进程独立计数，仍能显著抬高攻击成本；
若需要精确全局限流，可替换为 Redis 实现（接口保持不变）。
"""

import threading
import time
from collections import defaultdict, deque


_lock = threading.Lock()
_hits: dict = defaultdict(deque)


def allow(key: str, max_events: int, per_seconds: float) -> bool:
    """在 per_seconds 窗口内该 key 已发生 max_events 次则拒绝。

    内存自清理：key 闲置超过窗口时长即被移除，防止无限增长。
    """
    now = time.monotonic()
    with _lock:
        q = _hits.get(key)
        if q is None:
            q = deque()
            _hits[key] = q
        while q and now - q[0] > per_seconds:
            q.popleft()
        if len(q) >= max_events:
            return False
        q.append(now)
        # 简易清理：条目过多时剔除已过期 key，避免长期运行内存膨胀
        if len(_hits) > 10_000:
            for k in [k for k, v in _hits.items() if not v or now - v[-1] > per_seconds]:
                _hits.pop(k, None)
        return True
