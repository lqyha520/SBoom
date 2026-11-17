"""先在进程内等待锁域，再借数据库连接；共享锁允许不同用户并行。"""

import threading
import time
from contextlib import ExitStack, contextmanager
from hashlib import sha256

from app.constants import LOCK_IDS


class DatabaseBusy(TimeoutError):
    pass


class _Gate:
    def __init__(self):
        self.condition = threading.Condition()
        self.readers = 0
        self.writer = False
        self.waiting_writers = 0

    @contextmanager
    def enter(self, shared: bool, timeout: float):
        deadline = time.monotonic() + timeout
        with self.condition:
            if not shared:
                self.waiting_writers += 1
            try:
                while self.writer or (not shared and self.readers) or (shared and self.waiting_writers):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise DatabaseBusy("数据库操作繁忙")
                    self.condition.wait(remaining)
                if shared:
                    self.readers += 1
                else:
                    self.writer = True
            finally:
                if not shared:
                    self.waiting_writers -= 1
                self.condition.notify_all()
        try:
            yield
        finally:
            with self.condition:
                if shared:
                    self.readers -= 1
                else:
                    self.writer = False
                self.condition.notify_all()


_DOMAINS = {name: _Gate() for name in sorted(LOCK_IDS, key=LOCK_IDS.__getitem__)}
_USERS = [_Gate() for _ in range(256)]
_KEYS = {name: [_Gate() for _ in range(256)] for name in LOCK_IDS}


@contextmanager
def admission(scopes: tuple[str, ...], content_user: str | None, timeout: float,
              lock_key: tuple[str, str] | None = None):
    locks = dict.fromkeys(scopes, False)
    if content_user is not None:
        locks.setdefault("content", True)
    if lock_key is not None:
        locks.setdefault(lock_key[0], True)
    if unknown := locks.keys() - _DOMAINS.keys():
        raise ValueError(f"未知数据库锁域: {sorted(unknown)}")
    with ExitStack() as stack:
        for name in _DOMAINS:
            if name in locks:
                stack.enter_context(_DOMAINS[name].enter(locks[name], timeout))
        if content_user is not None:
            index = sha256(str(content_user).encode()).digest()[0]
            stack.enter_context(_USERS[index].enter(False, timeout))
        if lock_key is not None:
            domain, key = lock_key
            index = sha256(key.encode()).digest()[0]
            stack.enter_context(_KEYS[domain][index].enter(False, timeout))
        yield
