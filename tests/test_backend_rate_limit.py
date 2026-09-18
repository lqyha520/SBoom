"""Deterministic sliding-window and memory-pressure regressions (no database)."""

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from app.services import rate_limit


class RateLimitContracts(unittest.TestCase):
    def setUp(self):
        self.clock = patch.object(rate_limit.time, "monotonic", return_value=0.0)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.hits = patch.object(rate_limit, "_hits", {})
        self.hits.start()
        self.addCleanup(self.hits.stop)
        expiry = patch.object(rate_limit, "_expirations", [])
        expiry.start()
        self.addCleanup(expiry.stop)

    def test_short_window_cleanup_preserves_long_window_limits(self):
        self.assertTrue(rate_limit.allow("register:busy", 1, 3600))
        for index in range(10_000):
            rate_limit.allow(f"login:{index}", 1, 300)
        self.now.return_value = 301.0
        self.assertTrue(rate_limit.allow("events:reader", 1, 60))
        self.assertFalse(rate_limit.allow("register:busy", 1, 3600))

    def test_sliding_window_expires_each_accepted_request(self):
        self.assertTrue(rate_limit.allow("reader", 2, 60))
        self.now.return_value = 30.0
        self.assertTrue(rate_limit.allow("reader", 2, 60))
        self.now.return_value = 60.0
        self.assertTrue(rate_limit.allow("reader", 2, 60))
        self.assertFalse(rate_limit.allow("reader", 2, 60))
        self.now.return_value = 90.0
        self.assertTrue(rate_limit.allow("reader", 2, 60))
        self.assertFalse(rate_limit.allow("reader", 2, 60))

    def test_denials_do_not_extend_window(self):
        self.assertTrue(rate_limit.allow("reader", 1, 60))
        self.now.return_value = 59.0
        self.assertFalse(rate_limit.allow("reader", 1, 60))
        self.now.return_value = 60.0
        self.assertTrue(rate_limit.allow("reader", 1, 60))

    def test_capacity_rejects_new_keys_without_resetting_existing_limits(self):
        with patch.object(rate_limit, "_MAX_KEYS", 2):
            self.assertTrue(rate_limit.allow("first", 2, 60))
            self.assertTrue(rate_limit.allow("second", 1, 60))
            self.assertFalse(rate_limit.allow("third", 1, 60))
            self.assertTrue(rate_limit.allow("first", 2, 60))
            self.assertFalse(rate_limit.allow("first", 2, 60))
            self.now.return_value = 60.0
            self.assertTrue(rate_limit.allow("third", 1, 60))

    def test_active_key_keeps_its_latest_window_during_cleanup(self):
        self.assertTrue(rate_limit.allow("reader", 2, 60))
        self.now.return_value = 59.0
        self.assertTrue(rate_limit.allow("reader", 2, 60))
        self.now.return_value = 61.0
        self.assertTrue(rate_limit.allow("other", 1, 60))
        self.assertTrue(rate_limit.allow("reader", 2, 60))
        self.assertFalse(rate_limit.allow("reader", 2, 60))

    def test_concurrent_admission_is_atomic(self):
        barrier = threading.Barrier(16)

        def admit(_):
            barrier.wait(timeout=5)
            return rate_limit.allow("shared", 5, 60)

        with ThreadPoolExecutor(max_workers=16) as pool:
            self.assertEqual(sum(pool.map(admit, range(16))), 5)

    def test_repeated_requests_do_not_grow_expiry_queue(self):
        for _ in range(1000):
            rate_limit.allow("reader", 1000, 60)
        self.assertEqual(len(rate_limit._expirations), 1)

    def test_same_key_with_different_policies_does_not_mix_windows(self):
        self.assertTrue(rate_limit.allow("reader", 1, 3600))
        self.assertTrue(rate_limit.allow("reader", 1, 60))
        self.now.return_value = 61.0
        self.assertTrue(rate_limit.allow("reader", 1, 60))
        self.assertFalse(rate_limit.allow("reader", 1, 3600))

    def test_cleanup_work_is_bounded_and_recovers_capacity(self):
        with patch.object(rate_limit, "_MAX_KEYS", 100):
            for index in range(100):
                self.assertTrue(rate_limit.allow(str(index), 1, 60))
            self.now.return_value = 60.0
            self.assertTrue(rate_limit.allow("fresh", 1, 60))
            self.assertEqual(len(rate_limit._hits), 100 - rate_limit._CLEANUP_BATCH + 1)
            self.assertFalse(rate_limit.allow("fresh", 1, 60))
            self.assertEqual(len(rate_limit._hits), 1)

    def test_invalid_policy_does_not_leave_empty_entries(self):
        for count, seconds in ((0, 60), (-1, 60), (1, 0), (1, -1), (1, float("inf")), (1, float("nan"))):
            with self.subTest(count=count, seconds=seconds), self.assertRaises(ValueError):
                rate_limit.allow("reader", count, seconds)
        self.assertEqual(len(rate_limit._hits), 0)
        self.assertEqual(len(rate_limit._expirations), 0)
