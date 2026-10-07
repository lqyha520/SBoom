"""限制单进程内高内存工作；拒绝时不等待、不读取上传内容。"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from inspect import iscoroutinefunction
from threading import BoundedSemaphore

from fastapi import HTTPException

_slots = BoundedSemaphore(2)
_admitted: ContextVar[bool] = ContextVar("media_admitted", default=False)
_image_requests = BoundedSemaphore(2)


@contextmanager
def admitted_image_request():
    if not _image_requests.acquire(blocking=False):
        raise HTTPException(429, detail={"error": "生图任务繁忙，请稍后重试"}, headers={"Retry-After": "3"})
    try:
        yield
    finally:
        _image_requests.release()


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


def _bounded(function, admission):
    if iscoroutinefunction(function):
        @wraps(function)
        async def async_call(*args, **kwargs):
            with admission():
                return await function(*args, **kwargs)
        return async_call
    @wraps(function)
    def call(*args, **kwargs):
        with admission():
            return function(*args, **kwargs)
    return call


def bounded_media(function):
    return _bounded(function, admitted_media)


def bounded_image_request(function):
    return _bounded(function, admitted_image_request)
