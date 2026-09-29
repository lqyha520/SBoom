"""支付操作并发闸门及相同请求合并；不缓存失败或已完成的支付结果。"""

import hashlib
import threading
from concurrent.futures import Future

from fastapi import HTTPException

from app.services.rate_limit import allow

_slots = threading.BoundedSemaphore(4)
_lock = threading.Lock()
_pending: dict[str, Future] = {}


def throttle(user_id: str, kind: str) -> None:
    if not allow(f"commerce:{kind}:{user_id}", 12, 60):
        raise HTTPException(429, detail={"error": "操作较频繁，请稍后再试"}, headers={"Retry-After": "5"})


def execute(function, *args):
    key = hashlib.sha256(repr((function.__module__, function.__name__, args)).encode()).hexdigest()
    with _lock:
        future = _pending.get(key)
        owner = future is None
        if owner:
            future = Future()
            _pending[key] = future
    assert future is not None
    if not owner:
        return future.result(timeout=30)
    acquired = False
    try:
        acquired = _slots.acquire(blocking=False)
        if not acquired:
            raise HTTPException(429, detail={"error": "支付服务繁忙，请稍后重试"}, headers={"Retry-After": "2"})
        value = function(*args)
        future.set_result(value)
        return value
    except BaseException as exc:
        future.set_exception(exc)
        raise
    finally:
        if acquired:
            _slots.release()
        with _lock:
            _pending.pop(key, None)
