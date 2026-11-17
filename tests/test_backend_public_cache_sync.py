"""跨进程公开缓存同步；仅连接独立的本地 lc_test_* 测试库。"""

import asyncio
import multiprocessing
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from threading import Event
from unittest.mock import AsyncMock, Mock, patch

import psycopg
import pytest
from pg_support import create_test_db, drop_test_db, install_module_database, is_disposable_db

install_module_database()

from app import db as database
from app import public_cache, public_cache_sync
from app.config import get_settings
from app.public_cache_sync import CHANNEL, PublicCacheListener


@pytest.fixture
def cache_db():
    dsn, name = create_test_db()
    database.close_pg_pool()
    try:
        with patch.object(get_settings(), 'database_url', dsn), \
                patch.object(get_settings(), 'db_pool_min', 1), patch.object(get_settings(), 'db_pool_max', 1):
            with psycopg.connect(dsn) as conn:
                conn.execute('CREATE TABLE cache_valid (value INTEGER PRIMARY KEY)')
                conn.execute('INSERT INTO cache_valid VALUES (0), (1), (2), (3)')
                conn.execute('CREATE TABLE cache_probe (value INTEGER REFERENCES cache_valid(value) '
                             'DEFERRABLE INITIALLY DEFERRED)')
                conn.execute('INSERT INTO cache_probe VALUES (0)')
                conn.execute('CREATE TABLE private_probe (value INTEGER)')
            public_cache.invalidate()
            yield dsn
    finally:
        database.close_pg_pool()
        public_cache.invalidate()
        drop_test_db(name)


def metadata_reader():
    loads = []

    @public_cache.cached_public
    def metadata():
        with database.db() as conn:
            value = conn.execute('SELECT value FROM cache_probe').fetchone()[0]
        loads.append(value)
        return value

    return metadata, loads


def wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    assert predicate(), '等待跨进程状态变化超时'


@contextmanager
def listening(dsn):
    changed = Event()

    def invalidate():
        public_cache.invalidate()
        changed.set()

    with patch.object(public_cache_sync, 'invalidate', side_effect=invalidate):
        listener = PublicCacheListener(dsn)
        listener.start()
        try:
            assert listener.ready.wait(5)
            changed.clear()
            yield listener, changed
        finally:
            listener.close()
            assert not listener._thread.is_alive()


def _writer(pipe, dsn):
    """独立 Python 进程通过真实 db() 事务发布通知；管道只用于控制提交时机。"""
    assert is_disposable_db(dsn)
    database.close_pg_pool()
    try:
        with patch.object(get_settings(), 'database_url', dsn), \
                patch.object(get_settings(), 'db_pool_min', 1), patch.object(get_settings(), 'db_pool_max', 1):
            pipe.send('ready')
            while (command := pipe.recv()) != 'stop':
                kind, value = command
                try:
                    with database.db(invalidate_public=kind != 'private') as conn:
                        if kind == 'private':
                            conn.execute('INSERT INTO private_probe VALUES (?)', (value,))
                        else:
                            conn.execute('UPDATE cache_probe SET value=?', (value,))
                        pipe.send('staged')
                        if pipe.recv() == 'rollback':
                            raise RuntimeError('测试回滚')
                except RuntimeError:
                    pipe.send('rolled_back')
                else:
                    pipe.send('committed')
    finally:
        database.close_pg_pool()
        pipe.close()


def receive(pipe):
    assert pipe.poll(10), '独立写入进程未响应'
    return pipe.recv()


def _reader(pipe, dsn):
    """独立接收进程，验证通知能同时驱逐多个 worker 的缓存。"""
    assert is_disposable_db(dsn)
    database.close_pg_pool()
    try:
        with patch.object(get_settings(), 'database_url', dsn), listening(dsn):
            metadata, loads = metadata_reader()
            pipe.send('ready')
            while (command := pipe.recv()) != 'stop':
                if isinstance(command, tuple):
                    wait_until(lambda: metadata() == command[1])
                pipe.send((metadata(), list(loads)))
    finally:
        database.close_pg_pool()
        pipe.close()


@contextmanager
def cache_process(dsn, target=_writer):
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe()
    process = context.Process(target=target, args=(child, dsn))
    process.start()
    child.close()
    try:
        assert receive(parent) == 'ready'
        yield parent
    finally:
        if process.is_alive():
            parent.send('stop')
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        parent.close()
        assert process.exitcode == 0


def write_in_process(pipe, value, *, kind='public', action='commit'):
    pipe.send((kind, value))
    assert receive(pipe) == 'staged'
    pipe.send(action)
    assert receive(pipe) == ('committed' if action == 'commit' else 'rolled_back')


def test_notifications_follow_successful_commit_only(cache_db):
    metadata, loads = metadata_reader()
    assert metadata() == 0
    with psycopg.connect(cache_db, autocommit=True) as observer:
        observer.execute(f'LISTEN {CHANNEL}')
        with database.db(serialized='accounts') as conn:
            conn.execute('INSERT INTO private_probe VALUES (1)')
        with pytest.raises(RuntimeError), database.db(invalidate_public=True) as conn:
            conn.execute('UPDATE cache_probe SET value=1')
            raise RuntimeError('回滚')
        # NOTIFY 已排入事务，但提交时的延迟约束失败也不能广播或清缓存。
        with pytest.raises(psycopg.errors.ForeignKeyViolation), database.db(invalidate_public=True) as conn:
            conn.execute('UPDATE cache_probe SET value=99')
        assert list(observer.notifies(timeout=0.1)) == []
        assert metadata() == 0 and loads == [0]
        with database.db(invalidate_public=True) as conn:
            conn.execute('UPDATE cache_probe SET value=1')
            assert list(observer.notifies(timeout=0.1)) == []
            assert metadata() == 0
        notices = list(observer.notifies(timeout=1, stop_after=1))
        assert len(notices) == 1 and notices[0].payload == ''
        assert metadata() == 1 and loads == [0, 1]
        with database.db(ddl=True) as conn:
            conn.execute('SELECT 1')
        assert len(list(observer.notifies(timeout=1, stop_after=1))) == 1


def test_two_processes_refresh_without_waiting_for_ttl_or_using_pool_slot(cache_db):
    with cache_process(cache_db) as writer, listening(cache_db) as (_, changed):
        metadata, loads = metadata_reader()
        assert metadata() == 0
        # 监听器持有连接时，max_size=1 的请求池仍可读取。
        assert database._get_pg_pool().get_stats()['pool_size'] == 1
        writer.send(('public', 1))
        assert receive(writer) == 'staged'
        assert not changed.wait(0.1)
        assert metadata() == 0
        started = time.monotonic()
        writer.send('commit')
        assert receive(writer) == 'committed'
        assert changed.wait(5)
        assert metadata() == 1 and loads == [0, 1]
        assert time.monotonic() - started < 5  # 明显早于 20 秒 TTL
        changed.clear()
        write_in_process(writer, 2, action='rollback')
        write_in_process(writer, 2, kind='private')
        assert not changed.wait(0.2)
        assert metadata() == 1 and loads == [0, 1]


def test_remote_invalidation_prevents_inflight_old_load_from_refilling(cache_db):
    entered, release = Event(), Event()
    loads = []

    @public_cache.cached_public
    def slow_metadata():
        with database.db() as conn:
            value = conn.execute('SELECT value FROM cache_probe').fetchone()[0]
        loads.append(value)
        if len(loads) == 1:
            entered.set()
            assert release.wait(10)
        return value

    with cache_process(cache_db) as writer, listening(cache_db) as (_, changed), ThreadPoolExecutor(1) as pool:
        old = pool.submit(slow_metadata)
        try:
            assert entered.wait(5)
            write_in_process(writer, 1)
            assert changed.wait(5)
            assert slow_metadata() == 1
        finally:
            release.set()
        assert old.result(timeout=5) == 0
        assert slow_metadata() == 1 and loads == [0, 1]


def listener_pids(dsn):
    assert is_disposable_db(dsn)
    with psycopg.connect(dsn, autocommit=True) as conn:
        return [row[0] for row in conn.execute(
            "SELECT pid FROM pg_stat_activity WHERE datname=current_database() "
            "AND application_name='learn-coach-public-cache'").fetchall()]


def test_reconnect_and_listener_restart_clear_missed_updates(cache_db):
    connect = psycopg.connect
    offline = Event()

    def controlled_connect(*args, **kwargs):
        if kwargs.get('application_name') == 'learn-coach-public-cache' and offline.is_set():
            raise psycopg.OperationalError('模拟监听网络暂时不可用')
        return connect(*args, **kwargs)

    with cache_process(cache_db) as writer, patch.object(public_cache_sync.psycopg, 'connect', controlled_connect):
        with listening(cache_db) as (listener, changed):
            metadata, loads = metadata_reader()
            assert metadata() == 0
            original_pid, = listener_pids(cache_db)
            offline.set()
            with connect(cache_db, autocommit=True) as conn:
                assert conn.execute('SELECT pg_terminate_backend(%s)', (original_pid,)).fetchone()[0]
            wait_until(lambda: not listener.ready.is_set())
            write_in_process(writer, 1)
            assert not changed.is_set()
            assert metadata() == 0
            offline.clear()
            assert listener.ready.wait(5)
            assert metadata() == 1 and loads == [0, 1]
            assert listener_pids(cache_db) != [original_pid]
        assert listener_pids(cache_db) == []
        # 重新启动监听时，订阅前发生的写入没有通知可补收，必须主动驱逐旧缓存。
        write_in_process(writer, 2)
        assert metadata() == 1
        with listening(cache_db):
            assert metadata() == 2 and loads == [0, 1, 2]
        assert listener_pids(cache_db) == []


def test_all_receiving_processes_refresh_and_restarted_worker_reads_latest(cache_db):
    with cache_process(cache_db, _reader) as first:
        with cache_process(cache_db, _reader) as second:
            for reader in (first, second):
                reader.send('read')
                assert receive(reader) == (0, [0])
            with database.db(invalidate_public=True) as conn:
                conn.execute('UPDATE cache_probe SET value=1')
            for reader in (first, second):
                reader.send(('await', 1))
                assert receive(reader) == (1, [0, 1])
        assert len(listener_pids(cache_db)) == 1
        with database.db(invalidate_public=True) as conn:
            conn.execute('UPDATE cache_probe SET value=2')
        with cache_process(cache_db, _reader) as restarted:
            restarted.send('read')
            assert receive(restarted) == (2, [2])
        first.send(('await', 2))
        assert receive(first) == (2, [0, 1, 2])
    assert listener_pids(cache_db) == []


def test_shutdown_during_connection_setup_closes_late_connection_without_subscribing():
    connecting, release = Event(), Event()
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)

    def delayed_connect(*args, **kwargs):
        connecting.set()
        assert release.wait(5)
        return connection

    with patch.object(public_cache_sync.psycopg, 'connect', side_effect=delayed_connect), \
            patch.object(public_cache_sync, 'invalidate') as invalidate, ThreadPoolExecutor(1) as pool:
        listener = PublicCacheListener('unused-test-dsn')
        listener.start()
        try:
            assert connecting.wait(5)
            closed = pool.submit(listener.close)
            assert listener._stop.wait(5)
        finally:
            release.set()
        closed.result(timeout=5)
        assert not listener._thread.is_alive()
        assert not listener.ready.is_set()
        connection.__exit__.assert_called_once()
        connection.execute.assert_not_called()
        invalidate.assert_not_called()


def test_unavailable_listener_retries_without_leaking_details_and_stops_promptly(caplog):
    attempted = Event()

    def unavailable(*args, **kwargs):
        attempted.set()
        raise psycopg.OperationalError('password=do-not-log-this')

    with patch.object(public_cache_sync.psycopg, 'connect', side_effect=unavailable) as connect:
        listener = PublicCacheListener('unused-test-dsn')
        listener.start()
        try:
            assert attempted.wait(5)
            wait_until(lambda: 'TTL' in caplog.text)
            assert not listener.ready.is_set()
            assert connect.call_count == 1
            assert 'do-not-log-this' not in caplog.text
        finally:
            started = time.monotonic()
            listener.close()
        assert not listener._thread.is_alive()
        assert time.monotonic() - started < 1


@pytest.mark.parametrize('failure', [None, 'startup', 'serving'])
def test_lifespan_closes_listener_even_when_startup_or_serving_fails(failure):
    from app import main

    with ExitStack() as stack:
        stack.enter_context(patch.object(type(main.settings), 'validate_startup'))
        for target in ('app.metrics.init_metrics',
                       'app.blocking.configure_threads', 'app.main.init_db',
                       'app.services.app_config.seed_llm_from_user_configs', 'app.main.close_pg_pool'):
            stack.enter_context(patch(target))
        stack.enter_context(patch.object(main.settings, 'admin_username', ''))
        stack.enter_context(patch.object(main.settings, 'metrics_enabled', False))
        stack.enter_context(patch('app.main.security_warnings', return_value=[]))
        stack.enter_context(patch('app.services.mini_jobs.start', return_value=(None, None)))
        for target in ('app.blocking.sample_limiters', 'app.services.generation_control.shutdown_generation',
                       'app.main.llm_client.close', 'app.services.provider_http.close_clients'):
            stack.enter_context(patch(target, new_callable=AsyncMock))
        reclaim = stack.enter_context(patch('app.services.generation_control.reclaim_expired'))
        listener = Mock()
        factory = stack.enter_context(patch.object(main, 'PublicCacheListener', return_value=listener))
        if failure == 'startup':
            reclaim.side_effect = RuntimeError('启动失败')

        async def serve():
            async with main.lifespan(main.app):
                listener.start.assert_called_once_with()
                if failure == 'serving':
                    raise RuntimeError('服务中断')

        if failure:
            with pytest.raises(RuntimeError):
                asyncio.run(serve())
        else:
            asyncio.run(serve())
        factory.assert_called_once_with(main.settings.database_url)
        listener.close.assert_called_once_with()
