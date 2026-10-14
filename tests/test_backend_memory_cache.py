"""缓存并发、失效与容量边界；不访问数据库或业务文件。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.memory_cache import MemoryCache


def test_same_key_loads_once_and_other_keys_do_not_wait():
    cache: MemoryCache[bytes] = MemoryCache(ttl=20, max_entries=3, max_weight=100, weigh=len)
    entered, release, joined = Event(), Event(), Event()

    def load():
        entered.set()
        assert release.wait(5)
        return b"first"

    with ThreadPoolExecutor(3) as pool:
        first = pool.submit(cache.get_or_load, "a", load)
        try:
            assert entered.wait(5)
            # 确认第二个调用已经进入等待，避免调度顺序掩盖重复加载。
            future = cache._loading["a"]
            original_result = future.result

            def wait():
                joined.set()
                return original_result(timeout=5)

            with patch.object(future, "result", side_effect=wait):
                duplicate = pool.submit(cache.get_or_load, "a", Mock(side_effect=AssertionError("重复加载")))
                assert joined.wait(5)
                assert pool.submit(cache.get_or_load, "b", lambda: b"second").result(timeout=5) == b"second"
                release.set()
                assert first.result(timeout=5) == duplicate.result(timeout=5) == b"first"
        finally:
            release.set()


def test_invalidate_during_load_cannot_restore_old_value():
    cache: MemoryCache[str] = MemoryCache(ttl=20, max_entries=3, max_weight=3)
    entered, release = Event(), Event()

    def old_load():
        entered.set()
        assert release.wait(5)
        return "old"

    with ThreadPoolExecutor(1) as pool:
        old = pool.submit(cache.get_or_load, "a", old_load)
        try:
            assert entered.wait(5)
            cache.clear()
            assert cache.get_or_load("a", lambda: "new") == "new"
        finally:
            release.set()
        assert old.result(timeout=5) == "old"
    assert cache.get_or_load("a", lambda: "unexpected") == "new"


def test_lru_byte_budget_oversize_and_expiration():
    cache: MemoryCache[bytes] = MemoryCache(ttl=10, max_entries=2, max_weight=5, weigh=len)
    with patch("app.memory_cache.time.monotonic", return_value=1):
        cache.get_or_load("a", lambda: b"aa")
        cache.get_or_load("b", lambda: b"bb")
        cache.get_or_load("a", lambda: b"unexpected")
        cache.get_or_load("c", lambda: b"ccc")
        assert list(cache._values) == ["a", "c"]
        assert cache._weight == 5
        assert cache.get_or_load("large", lambda: b"123456") == b"123456"
        assert "large" not in cache._values
    with patch("app.memory_cache.time.monotonic", return_value=12):
        assert cache.get_or_load("a", lambda: b"fresh") == b"fresh"
        assert cache._weight == 5


def test_failure_is_not_cached_and_loader_can_invalidate():
    cache: MemoryCache[str] = MemoryCache(ttl=20, max_entries=3, max_weight=3)
    with pytest.raises(ValueError):
        cache.get_or_load("a", Mock(side_effect=ValueError("retry")))
    assert cache.get_or_load("a", lambda: "retried") == "retried"

    def load():
        cache.clear()
        return "uncached"

    assert cache.get_or_load("b", load) == "uncached"
    assert cache.get_or_load("b", lambda: "fresh") == "fresh"


def test_public_cache_isolates_database_and_caller_mutations():
    from app import public_cache

    public_cache.invalidate()
    settings = SimpleNamespace(database_url="fixture-one")
    calls = Mock(return_value={"items": ["public"]})

    @public_cache.cached_public
    def catalog():
        return calls()

    with patch.object(public_cache, "get_settings", return_value=settings):
        catalog()["items"].append("private")
        assert catalog() == {"items": ["public"]}
        assert calls.call_count == 1
        settings.database_url = "fixture-two"
        catalog()
        assert calls.call_count == 2
        public_cache.invalidate()
        catalog()
        assert calls.call_count == 3
