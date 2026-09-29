"""同步路由与异步入口共用 AnyIO 线程容量，并记录进入工作线程前的等待。"""

import asyncio
import threading
import time
import weakref
from collections.abc import Callable

import anyio.to_thread

from app.metrics import thread_capacity, thread_wait

_limiters: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _limiter(kind: str):
    if kind == "default":
        return anyio.to_thread.current_default_thread_limiter()
    current = _limiters.setdefault(asyncio.get_running_loop(), {})
    if kind not in current:
        current[kind] = anyio.CapacityLimiter({"probe": 1, "auth": 4, "media": 2}[kind])
    return current[kind]


def configure_threads(pool_max: int) -> None:
    anyio.to_thread.current_default_thread_limiter().total_tokens = max(8, pool_max * 2)


async def run_sync[T, **P](function: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    return await run_sync_in("default", function, *args, **kwargs)


async def run_sync_in[T, **P](kind: str, function: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    queued_at = time.perf_counter()
    cancelled = threading.Event()

    def execute() -> T:
        if cancelled.is_set():
            raise asyncio.CancelledError
        thread_wait.observe(time.perf_counter() - queued_at)
        return function(*args, **kwargs)

    # 调用方取消时立即返回，但工作线程结束前仍占用容量；反复取消不能突破线程上限。
    # 尚未开始的任务在取得容量后跳过，不会在请求超时后继续执行写操作。
    limiter = _limiter(kind)
    stats = limiter.statistics()
    thread_capacity.labels(kind, "borrowed").set(stats.borrowed_tokens)
    thread_capacity.labels(kind, "waiting").set(stats.tasks_waiting)
    task = asyncio.create_task(anyio.to_thread.run_sync(execute, limiter=limiter))

    def finished(completed: asyncio.Task[T]) -> None:
        if not completed.cancelled():
            completed.exception()  # 调用方离开后也回收同步任务异常。

    task.add_done_callback(finished)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        cancelled.set()
        raise


async def sample_limiters() -> None:
    """定期采样含同步路由在内的默认 AnyIO limiter，而不限于 run_sync 调用。"""
    while True:
        for kind in ("default", "probe", "auth", "media"):
            stats = _limiter(kind).statistics()
            thread_capacity.labels(kind, "borrowed").set(stats.borrowed_tokens)
            thread_capacity.labels(kind, "waiting").set(stats.tasks_waiting)
        await asyncio.sleep(5)
