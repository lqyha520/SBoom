"""同步路由与异步入口共用 AnyIO 线程容量，并记录进入工作线程前的等待。"""

import asyncio
import threading
import time
from collections.abc import Callable

import anyio.to_thread

from app.metrics import thread_wait


def configure_threads(pool_max: int) -> None:
    anyio.to_thread.current_default_thread_limiter().total_tokens = max(40, pool_max * 2)


async def run_sync[T, **P](function: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    queued_at = time.perf_counter()
    cancelled = threading.Event()

    def execute() -> T:
        if cancelled.is_set():
            raise asyncio.CancelledError
        thread_wait.observe(time.perf_counter() - queued_at)
        return function(*args, **kwargs)

    # 调用方取消时立即返回，但工作线程结束前仍占用容量；反复取消不能突破线程上限。
    # 尚未开始的任务在取得容量后跳过，不会在请求超时后继续执行写操作。
    task = asyncio.create_task(anyio.to_thread.run_sync(execute))

    def finished(completed: asyncio.Task[T]) -> None:
        if not completed.cancelled():
            completed.exception()  # 调用方离开后也回收同步任务异常。

    task.add_done_callback(finished)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        cancelled.set()
        raise
