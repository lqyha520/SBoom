"""真实工作线程验证共享容量、上下文传播和取消，不访问数据库。"""

import asyncio
import threading
import unittest
from contextvars import ContextVar

import anyio.to_thread
from starlette.concurrency import run_in_threadpool

from app.blocking import configure_threads, run_sync
from app.metrics import thread_wait


class BlockingContracts(unittest.IsolatedAsyncioTestCase):
    async def test_configuration_controls_both_entry_points(self):
        configure_threads(32)
        limiter = anyio.to_thread.current_default_thread_limiter()
        self.assertEqual(limiter.total_tokens, 64)
        limiter.total_tokens = 1
        release, entered, second_entered = threading.Event(), threading.Event(), threading.Event()

        def occupy():
            entered.set()
            release.wait(3)

        first = asyncio.create_task(run_sync(occupy))
        try:
            async with asyncio.timeout(2):
                while not entered.is_set():
                    await asyncio.sleep(0.005)
            before = thread_wait._sum.get()
            second = asyncio.create_task(run_in_threadpool(second_entered.set))
            third = asyncio.create_task(run_sync(lambda: "completed"))
            await asyncio.sleep(0.06)
            self.assertFalse(second_entered.is_set())
            self.assertFalse(third.done())
        finally:
            release.set()
            await first
        await second
        self.assertEqual(await third, "completed")
        self.assertGreaterEqual(thread_wait._sum.get() - before, 0.05)

    async def test_keyword_arguments_and_context_reach_worker(self):
        owner = ContextVar("test_owner", default="")
        owner.set("teacher")
        result = await run_sync(lambda *, suffix: owner.get() + suffix, suffix="-7")
        self.assertEqual(result, "teacher-7")

    async def test_cancelling_queued_work_does_not_start_it(self):
        limiter = anyio.to_thread.current_default_thread_limiter()
        limiter.total_tokens = 1
        started = threading.Event()
        async with limiter:
            task = asyncio.create_task(run_sync(started.set))
            await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        await run_sync(lambda: None)
        self.assertFalse(started.is_set(), "已取消的排队任务不应执行")

    async def test_cancelling_waiter_keeps_started_work_alive(self):
        anyio.to_thread.current_default_thread_limiter().total_tokens = 1
        entered, release, completed = threading.Event(), threading.Event(), threading.Event()
        next_started = threading.Event()

        def work():
            entered.set()
            release.wait(3)
            completed.set()

        task = asyncio.create_task(run_sync(work))
        try:
            async with asyncio.timeout(2):
                while not entered.is_set():
                    await asyncio.sleep(0.005)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertFalse(completed.is_set())
            next_job = asyncio.create_task(run_sync(next_started.set))
            await asyncio.sleep(0.04)
            self.assertFalse(next_started.is_set(), "取消等待不能提前释放仍在工作的线程容量")
        finally:
            release.set()
        async with asyncio.timeout(2):
            while not completed.is_set():
                await asyncio.sleep(0.005)
        await next_job
        self.assertTrue(next_started.is_set())
