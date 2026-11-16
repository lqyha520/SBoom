"""上传体读取前限流；客户端取消后，处理结束才归还名额。"""

import asyncio
import threading
from functools import wraps

from fastapi import HTTPException


def bounded_upload(slots: int):
    gate = threading.BoundedSemaphore(slots)

    def decorate(function):
        tasks = set()

        @wraps(function)
        async def admitted(*args, **kwargs):
            if not gate.acquire(blocking=False):
                raise HTTPException(429, detail={"error": "素材正在上传或处理，请稍后重试", "code": "asset_upload_busy"},
                                    headers={"Retry-After": "3"})
            try:
                task = asyncio.create_task(function(*args, **kwargs))
            except BaseException:
                gate.release()
                raise

            def finished(completed):
                tasks.discard(completed)
                gate.release()
                if not completed.cancelled():
                    completed.exception()

            tasks.add(task)
            task.add_done_callback(finished)
            # 连读取阶段也受名额约束；断开时由请求流抛出异常，处理阶段由工作线程完成。
            return await asyncio.shield(task)

        return admitted
    return decorate
