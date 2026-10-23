"""Bounded, idempotent maintenance owned by the API process lifecycle."""

import asyncio
import logging
import threading
import time
from datetime import datetime, timedelta

from fastapi import HTTPException

from app.blocking import run_sync
from app.config import get_settings
from app.constants import EXPIRY_SWEEP_LOCK as _EXPIRY_SWEEP_LEASE
from app.db import db
from app.services import (
    mini_auth,
    mini_messages,
    mini_orders,
    mini_refunds,
    payment_bills,
    wechat_notices,
    wechat_virtual_pay,
)
from app.services.wechat_pay import PaymentError, configuration

logger = logging.getLogger(__name__)

#: 会员到期提醒扫描的单进程租约键（与 app.db._LOCK_IDS、maintenance.tick 的 70634195 错开）


def tick(stop):
    if stop.is_set():
        return
    if get_settings().maintenance_enabled:
        from app.services.maintenance import tick as maintain
        try:
            maintain()
        except Exception:
            from app.metrics import maintenance_failures
            maintenance_failures.inc()
            logger.exception("Storage maintenance failed; continuing payment jobs")
    now = int(time.time())
    # 过期会话清理从登录路径挪到这里：每轮最多删 500 条，走 expires_at 索引，普通事务即可
    with db() as conn:
        mini_auth.sweep_expired_sessions(conn, now)
    ordinary = configuration()["ready"]
    virtual = wechat_virtual_pay.configuration()["ready"]
    if ordinary or virtual:
        with db() as conn:
            expiring, synchronizing = [], []
            if ordinary:
                expiring += [row[0] for row in conn.execute("SELECT id FROM mini_orders WHERE payment_channel = 'wechat' AND status IN ('created', 'pending') AND expires_at <= ? AND lease_until < ? ORDER BY updated_at, id LIMIT 10", (now, now))]
            if virtual:
                expiring += [row[0] for row in conn.execute("SELECT id FROM mini_orders WHERE payment_channel = 'virtual' AND status IN ('created', 'pending') AND expires_at <= ? AND lease_until < ? ORDER BY updated_at, id LIMIT 10", (now, now))]
                # 未过期的虚拟订单只回查状态，不能走取消流程；用户可能刚在收银台完成付款。
                synchronizing += [row[0] for row in conn.execute("SELECT id FROM mini_orders WHERE payment_channel = 'virtual' AND status IN ('created', 'pending') AND expires_at > ? AND updated_at <= ? ORDER BY updated_at, id LIMIT 10", (now, now - 60))]
            refunds = []
            if ordinary:
                refunds += [row[0] for row in conn.execute("SELECT f.id FROM mini_refunds f JOIN mini_orders o ON o.id = f.order_id WHERE o.payment_channel = 'wechat' AND f.status IN ('processing', 'abnormal') AND f.lease_until < ? ORDER BY f.updated_at, f.id LIMIT 10", (now,))]
            if virtual:
                refunds += [row[0] for row in conn.execute("SELECT f.id FROM mini_refunds f JOIN mini_orders o ON o.id = f.order_id WHERE o.payment_channel = 'virtual' AND f.status IN ('processing', 'abnormal') AND f.lease_until < ? ORDER BY f.updated_at, f.id LIMIT 10", (now,))]
            deliveries = [row[0] for row in conn.execute("SELECT id FROM mini_orders WHERE payment_channel = 'virtual' AND paid_at IS NOT NULL AND delivered_at IS NULL ORDER BY updated_at, id LIMIT 10", ())] if virtual else []
        for function, identifiers in ((mini_orders.cancel, expiring), (mini_orders.sync, synchronizing), (mini_refunds.sync, refunds)):
            for identifier in identifiers:
                if stop.is_set():
                    return
                try:
                    function(identifier)
                except (PaymentError, HTTPException):
                    table = "mini_refunds" if function is mini_refunds.sync else "mini_orders"
                    # 只是把单条记录的 updated_at 往后推（行级 UPDATE），不需要 accounts 全局锁
                    with db() as conn:
                        conn.execute(f"UPDATE {table} SET updated_at = ? WHERE id = ?", (int(time.time()), identifier))
                    logger.warning("Membership maintenance deferred for record %s", identifier)
        for identifier in deliveries:
            if stop.is_set():
                return
            mini_orders.deliver_virtual(identifier)
    if wechat_notices.configuration()["available"] and not stop.is_set():
        # 不再持 accounts 全局锁遍历最多 200 个用户：notify 的插入按 (user_id, event_key) 幂等，
        # 游标推进用 try 租约保证同一时刻只有一个进程在扫，拿不到租约就跳过本轮。
        with db() as conn:
            if conn.execute("SELECT pg_try_advisory_xact_lock(?)", (_EXPIRY_SWEEP_LEASE,)).fetchone()[0]:
                cursor = conn.execute("SELECT value FROM app_config WHERE key = 'mini_expiry_cursor'").fetchone()
                rows = conn.execute("SELECT id FROM mini_users WHERE id > ? AND is_active = 1 AND membership = 'vip' AND vip_expires_at BETWEEN ? AND ? ORDER BY id LIMIT 200", (cursor[0] if cursor else "", now - 7 * 86400, now + 7 * 86400)).fetchall()
                for row in rows:
                    mini_messages.expiry_notice(conn, row[0])
                conn.execute("INSERT INTO app_config(key, value) VALUES ('mini_expiry_cursor', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (rows[-1][0] if len(rows) == 200 else "",))
        for _ in range(10):
            if stop.is_set() or not wechat_notices.dispatch_one():
                break
    if not stop.is_set() and get_settings().wechat_pay_auto_reconcile and configuration()["ready"]:
        today = datetime.now(payment_bills.ZONE)
        day = (today.date() - timedelta(days=1)).isoformat()
        with db() as conn:
            previous = conn.execute("SELECT status, updated_at FROM mini_reconciliations WHERE bill_date = ? ORDER BY created_at DESC, id DESC LIMIT 1", (day,)).fetchone()
        if today.hour >= 10 and (not previous or previous["status"] == "error" and previous["updated_at"] < now - 3600 or previous["status"] == "running" and previous["updated_at"] < now - 300):
            try:
                payment_bills.reconcile(None, day)
            except (PaymentError, HTTPException):
                logger.warning("Daily payment reconciliation deferred for %s", day)


def start():
    stop = threading.Event()
    async def run():
        while not stop.is_set():
            try:
                await run_sync(tick, stop)
            except Exception:
                from app.metrics import maintenance_failures
                maintenance_failures.inc()
                logger.exception("Consumer maintenance iteration failed")
            for _ in range(60):
                if stop.is_set():
                    break
                await asyncio.sleep(1)
    settings = get_settings()
    task = asyncio.create_task(run()) if settings.maintenance_enabled or settings.wechat_pay_enabled or settings.wechat_virtual_pay_enabled or settings.wechat_subscribe_template_id else None
    return stop, task
