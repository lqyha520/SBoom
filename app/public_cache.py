"""仅缓存公开元数据；缓存键包含数据库身份，写入提交后失效。"""

import copy
import threading
import time
from functools import wraps

from app.config import get_settings

_lock = threading.RLock()
_values: dict[tuple, tuple[float, object]] = {}


def invalidate() -> None:
    with _lock:
        _values.clear()


def cached_public(function):
    @wraps(function)
    def wrapped():
        key = (get_settings().database_url, function.__module__, function.__name__)
        # 同一冷启动请求只加载一次；数据必须独立复制，不能混入后续个人统计。
        with _lock:
            value = _values.get(key)
            if value is None or value[0] <= time.monotonic():
                loaded = function()
                if len(_values) >= 32:
                    _values.clear()
                value = (time.monotonic() + 20, loaded)
                _values[key] = value
            return copy.deepcopy(value[1])
    return wrapped
