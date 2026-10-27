import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from app.services import app_config
from app.services.model_profiles import revision


class AppConfigCacheContracts(unittest.TestCase):
    def setUp(self):
        app_config._invalidate_cache()
        self.addCleanup(app_config._invalidate_cache)

    def test_empty_configuration_is_cached_until_expiry(self):
        with patch.object(app_config, "_load_llm_raw", return_value={}) as load, \
                patch.object(app_config.time, "monotonic", return_value=100) as clock:
            for _attempt in range(5):
                self.assertEqual(app_config.get_llm(), app_config._EMPTY | {"revision": revision({})})
            self.assertEqual(load.call_count, 1)
            clock.return_value = 160
            app_config.get_llm()
            self.assertEqual(load.call_count, 2)

    def test_concurrent_refresh_loads_once_and_returns_complete_snapshots(self):
        started, release = threading.Event(), threading.Event()
        def load():
            started.set()
            if not release.wait(5):
                raise TimeoutError("cache test release timed out")
            return {"baseUrl": "https://example.invalid", "model": "fresh", "timeout": 90}
        with patch.object(app_config, "_load_llm_raw", side_effect=load) as loader, \
                ThreadPoolExecutor(max_workers=8) as pool:
            first = pool.submit(app_config.get_llm)
            try:
                self.assertTrue(started.wait(2))
                followers = [pool.submit(app_config.get_llm) for attempt in range(7)]
            finally:
                release.set()
            for job in [first, *followers]:
                result = job.result(timeout=5)
                self.assertEqual((result["baseUrl"], result["model"], result["timeout"]),
                                 ("https://example.invalid", "fresh", 90))
            self.assertEqual(loader.call_count, 1)

    def test_invalidation_is_not_lost_during_refresh(self):
        started, release = threading.Event(), threading.Event()
        def load():
            started.set()
            if not release.wait(5):
                raise TimeoutError("cache test release timed out")
            return {"model": "old"}
        with patch.object(app_config, "_load_llm_raw", side_effect=load), ThreadPoolExecutor(max_workers=2) as pool:
            refresh = pool.submit(app_config.get_llm)
            try:
                self.assertTrue(started.wait(2))
                invalidate = pool.submit(app_config._invalidate_cache)
            finally:
                release.set()
            refresh.result(timeout=5)
            invalidate.result(timeout=5)
        with patch.object(app_config, "_load_llm_raw", return_value={"model": "new"}) as load:
            self.assertEqual(app_config.get_llm()["model"], "new")
            load.assert_called_once()

    def test_failed_refresh_does_not_publish_or_extend_cache(self):
        with patch.object(app_config, "_load_llm_raw", return_value={"model": "old"}), \
                patch.object(app_config.time, "monotonic", return_value=100):
            app_config.get_llm()
        with patch.object(app_config, "_load_llm_raw", side_effect=RuntimeError("unavailable")), \
                patch.object(app_config.time, "monotonic", return_value=161):
            with self.assertRaises(RuntimeError):
                app_config.get_llm()
        self.assertEqual(app_config._cache_raw, {"model": "old"})
        self.assertEqual(app_config._cache_ts, 100)

    def test_clear_invalidates_cached_value(self):
        with patch.object(app_config, "_load_llm_raw", return_value={"model": "old"}):
            app_config.get_llm()
        with patch.object(app_config, "db") as database:
            app_config.clear_llm()
            database.assert_called_once_with(serialized="accounts")
        with patch.object(app_config, "_load_llm_raw", return_value={}):
            self.assertEqual(app_config.get_llm(), app_config._EMPTY | {"revision": revision({})})
