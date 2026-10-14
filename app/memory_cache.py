"""进程内有界缓存：同键合并加载，不同键互不等待；清空后旧加载不能重新填充。"""

import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from concurrent.futures import Future
from threading import Lock


class MemoryCache[T]:
    def __init__(self, *, ttl: float, max_entries: int, max_weight: int,
                 weigh: Callable[[T], int] = lambda value: 1):
        self._ttl = ttl
        self._max_entries = max_entries
        self._max_weight = max_weight
        self._weigh = weigh
        self._lock = Lock()
        self._values: OrderedDict[Hashable, tuple[float, T, int]] = OrderedDict()
        self._loading: dict[Hashable, Future[T]] = {}
        self._weight = 0

    def clear(self) -> None:
        with self._lock:
            self._values.clear()
            self._loading.clear()
            self._weight = 0

    def get_or_load(self, key: Hashable, load: Callable[[], T]) -> T:
        with self._lock:
            entry = self._values.get(key)
            if entry is not None:
                if entry[0] > time.monotonic():
                    self._values.move_to_end(key)
                    return entry[1]
                self._weight -= self._values.pop(key)[2]
            future = self._loading.get(key)
            leader = future is None
            if future is None:
                future = Future()
                self._loading[key] = future
        if not leader:
            return future.result()
        try:
            value = load()
            weight = self._weigh(value)
            with self._lock:
                if self._loading.get(key) is future:
                    # clear() 会移除旧加载的身份，避免写入提交后缓存复活。
                    if weight <= self._max_weight:
                        while self._values and (len(self._values) >= self._max_entries
                                                or self._weight + weight > self._max_weight):
                            self._weight -= self._values.popitem(last=False)[1][2]
                        self._values[key] = (time.monotonic() + self._ttl, value, weight)
                        self._weight += weight
                    del self._loading[key]
        except BaseException as error:
            with self._lock:
                if self._loading.get(key) is future:
                    del self._loading[key]
            future.set_exception(error)
            raise
        future.set_result(value)
        return value
