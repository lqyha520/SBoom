"""仅缓存公开元数据；缓存键包含数据库身份，写入提交后失效。"""

import copy
from functools import wraps

from app.config import get_settings
from app.memory_cache import MemoryCache

_cache: MemoryCache[object] = MemoryCache(ttl=20, max_entries=32, max_weight=32)


def invalidate() -> None:
    _cache.clear()


def cached_public(function):
    @wraps(function)
    def wrapped():
        key = (get_settings().database_url, function.__module__, function.__name__)
        # 数据库读取、深拷贝和等待同键加载均在全局锁外完成。
        # 每个调用者仍得到独立副本，不能混入后续个人统计。
        return copy.deepcopy(_cache.get_or_load(key, function))
    return wrapped
