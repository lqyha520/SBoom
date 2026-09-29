"""限制单进程内高内存工作；拒绝时不等待、不读取上传内容。"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from inspect import iscoroutinefunction
from threading import BoundedSemaphore

from fastapi import HTTPException

_slots = BoundedSemaphore(2)
_admitted: ContextVar[bool] = ContextVar("media_admitted", default=False)


@contextmanager
def admitted_media():
    if _admitted.get():
        yield
        return
    if not _slots.acquire(blocking=False):
        raise HTTPException(429, detail={"error": "图片处理繁忙，请稍后重试"}, headers={"Retry-After": "3"})
    token = _admitted.set(True)
    try:
        yield
    finally:
        _admitted.reset(token)
        _slots.release()


def bounded_media(function):
    if iscoroutinefunction(function):
        @wraps(function)
        async def async_call(*args, **kwargs):
            with admitted_media():
                return await function(*args, **kwargs)
        return async_call
    @wraps(function)
    def call(*args, **kwargs):
        with admitted_media():
            return function(*args, **kwargs)
    return call
