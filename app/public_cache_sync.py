"""通过 PostgreSQL 事务通知同步各进程的公开缓存失效。"""

import logging
from contextlib import closing
from threading import Event, Thread

import psycopg

from app.public_cache import invalidate

logger = logging.getLogger(__name__)
CHANNEL = "learn_coach_public_cache_v1"


def publish_invalidation(conn: psycopg.Connection) -> None:
    # 和内容写入共用事务：提交才投递，回滚自动丢弃；不广播内容、账号或连接信息。
    conn.execute("SELECT pg_notify(%s, '')", (CHANNEL,))


class PublicCacheListener:
    """每个应用 lifespan 持有一个监听器；不占请求池连接，也不在导入时启动。"""

    def __init__(self, database_url: str):
        self._database_url = database_url
        self._stop = Event()
        self.ready = Event()
        self._thread = Thread(target=self._run, name="public-cache-listener", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self.ready.clear()
        # 通知等待每 0.5 秒检查关停，连接建立设置 3 秒超时；关停等待本身也有上限。
        if self._thread.ident is not None:
            self._thread.join(timeout=5)
        if self._thread.is_alive():
            logger.warning("公开缓存监听仍在结束连接；连接返回后将自动释放")

    def _run(self) -> None:
        retry = 1.0
        while not self._stop.is_set():
            try:
                # LISTEN 要求固定会话与自动提交；连接由此线程独占并随重连/关停释放。
                with psycopg.connect(
                    self._database_url, autocommit=True, connect_timeout=3,
                    application_name="learn-coach-public-cache", keepalives=1,
                    keepalives_idle=10, keepalives_interval=5, keepalives_count=3,
                ) as conn:
                    if self._stop.is_set():
                        return
                    conn.execute(f"LISTEN {CHANNEL}")
                    if self._stop.is_set():
                        return
                    # 必须先完成订阅再清缓存，补偿启动/断线期间漏掉的通知及未完成的旧加载。
                    invalidate()
                    self.ready.set()
                    logger.info("公开缓存跨进程监听已就绪")
                    retry = 1.0
                    while not self._stop.is_set():
                        with closing(conn.notifies(timeout=0.5)) as notifications:
                            for _ in notifications:
                                if self._stop.is_set():
                                    return
                                invalidate()
            except (psycopg.Error, OSError) as error:
                if not self._stop.is_set():
                    # 数据库错误可能含 DSN 或服务器细节，只记录异常类型。
                    logger.warning("公开缓存监听中断（%s），将自动重连；暂由 20 秒 TTL 刷新",
                                   type(error).__name__)
            finally:
                self.ready.clear()
            if self._stop.wait(retry):
                return
            retry = min(retry * 2, 20.0)
