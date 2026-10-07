"""先在进程内等待锁域，再借数据库连接；共享锁允许不同用户并行。"""

import threading
import time
from contextlib import ExitStack, contextmanager
from hashlib import sha256


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


_DOMAINS = {name: _Gate() for name in ("content", "accounts", "generation", "schema")}
_USERS = [_Gate() for _ in range(256)]


@contextmanager
def admission(scopes: tuple[str, ...], content_user: str | None, timeout: float):
    locks = dict.fromkeys(scopes, False)
    if content_user is not None:
        locks.setdefault("content", True)
    with ExitStack() as stack:
        for name in _DOMAINS:
            if name in locks:
                stack.enter_context(_DOMAINS[name].enter(locks[name], timeout))
        if content_user is not None:
            index = sha256(str(content_user).encode()).digest()[0]
            stack.enter_context(_USERS[index].enter(False, timeout))
        yield
