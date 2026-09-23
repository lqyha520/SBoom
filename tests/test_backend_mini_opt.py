"""小程序侧性能优化的契约：去掉全局 accounts 锁后的行为、单次会话解析、有界查询数与新增字段。"""

import threading
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import test_backend_catalog as fixtures  # 先建一次性测试库，再 import app
from fastapi import HTTPException

from app import db as database
from app.config import get_settings
from app.models.commerce import PlanInput
from app.routers import commerce, engagement, experience
from app.services import catalog_ops, mini_auth, mini_jobs, mini_messages, mini_orders


@contextmanager
def count_queries():
    """统计一段代码里经由 db() 连接执行的 SQL 条数（咨询锁走裸连接，不计入）。"""
    counter = {"n": 0}
    original = database._PgConn.execute

    def counted(self, sql, params=None):
        counter["n"] += 1
        return original(self, sql, params)

    with patch.object(database._PgConn, "execute", counted):
        yield counter


class MiniOptimizationContracts(unittest.TestCase):
    sign_in = fixtures.PublicCatalogContracts.sign_in
    source = fixtures.PublicCatalogContracts.source
    draft = fixtures.PublicCatalogContracts.draft
    update = fixtures.PublicCatalogContracts.update
    publish = fixtures.PublicCatalogContracts.publish
    restricted = fixtures.PublicCatalogContracts.restricted

    def setUp(self):
        fixtures.PublicCatalogContracts.setUp(self)
        for router in (engagement.router, commerce.router, experience.router):
            self.client.app.include_router(router)
        for key, value in {"wechat_pay_enabled": False, "wechat_subscribe_template_id": "", "wechat_pay_auto_reconcile": False,
                           "maintenance_enabled": False}.items():
            self.stack.enter_context(patch.object(get_settings(), key, value))

    # ── 会话解析：一次 JOIN，保持返回形状 ──

    def test_resolve_session_is_a_single_query_and_keeps_shape(self):
        token = mini_auth.login_password(self.viewer.username, "test-password")["token"]
        with count_queries() as counter:
            user = mini_auth.resolve_session(token)
        self.assertEqual(counter["n"], 1)
        self.assertIsInstance(user, mini_auth.MiniUser)
        self.assertEqual(user.public(), mini_auth.get_user(self.viewer.id).public())
        with database.db() as conn:
            conn.execute("UPDATE mini_users SET is_active = 0 WHERE id = ?", (self.viewer.id,))
        with self.assertRaises(HTTPException) as disabled:
            mini_auth.resolve_session(token)
        self.assertEqual((disabled.exception.status_code, disabled.exception.detail["code"]), (403, "account_disabled"))
        with database.db() as conn:
            conn.execute("UPDATE mini_users SET is_active = 1 WHERE id = ?", (self.viewer.id,))
            conn.execute("UPDATE mini_user_sessions SET expires_at = ? WHERE token_hash = ?", (int(time.time()) - 1, mini_auth.digest(token)))
        with self.assertRaises(HTTPException) as expired:
            mini_auth.resolve_session(token)
        self.assertEqual(expired.exception.status_code, 401)

    # ── 登录：账号不存在也跑一次同等代价的密码校验 ──

    def test_password_login_verifies_a_dummy_hash_for_unknown_users(self):
        with patch.object(mini_auth, "verify_password", return_value=False) as verify:
            with self.assertRaises(HTTPException):
                mini_auth.login_password("no-such-user", "whatever")
            self.assertEqual(verify.call_count, 1)
            self.assertEqual(verify.call_args.args[1], mini_auth._dummy_hash())
            with self.assertRaises(HTTPException):
                mini_auth.login_password(self.viewer.username, "wrong-password")
            self.assertEqual(verify.call_count, 2)
            self.assertNotEqual(verify.call_args.args[1], mini_auth._dummy_hash())
        # 即便 verify 被篡改成恒真，不存在/没密码的账号也不能登录
        with patch.object(mini_auth, "verify_password", return_value=True):
            with self.assertRaises(HTTPException):
                mini_auth.login_password("no-such-user", "whatever")
        self.assertEqual(mini_auth._dummy_hash(), mini_auth._dummy_hash())
        self.assertTrue(mini_auth.login_password(self.viewer.username, "test-password")["token"].startswith("lc_reader_"))

    # ── 注册：靠唯一索引而不是全局锁去重 ──

    def test_registration_relies_on_unique_index_under_concurrency(self):
        with self.assertRaises(HTTPException) as taken:
            mini_auth.register(self.viewer.username, "test-password")
        self.assertEqual(taken.exception.status_code, 409)
        outcomes = []
        barrier = threading.Barrier(4)

        def attempt():
            barrier.wait()
            try:
                outcomes.append(mini_auth.register("race-reader", "test-password")["status"])
            except HTTPException as error:
                outcomes.append(error.status_code)

        threads = [threading.Thread(target=attempt) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(outcomes, key=str), sorted(["authenticated", 409, 409, 409], key=str))
        with database.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM mini_users WHERE username = 'race-reader'").fetchone()[0], 1)

    # ── 过期会话：登录不再全表清理，由后台任务分批处理 ──

    def test_expired_sessions_are_swept_by_jobs_not_by_login(self):
        stale = mini_auth.login_password(self.other.username, "test-password")["token"]
        with database.db() as conn:
            conn.execute("UPDATE mini_user_sessions SET expires_at = 1 WHERE token_hash = ?", (mini_auth.digest(stale),))
        mini_auth.login_password(self.viewer.username, "test-password")
        with database.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM mini_user_sessions WHERE expires_at = 1").fetchone()[0], 1)
            self.assertEqual(mini_auth.sweep_expired_sessions(conn, limit=1), 1)
            self.assertEqual(mini_auth.sweep_expired_sessions(conn), 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM mini_user_sessions WHERE expires_at = 1").fetchone()[0], 0)
            conn.execute("UPDATE mini_user_sessions SET expires_at = 1 WHERE user_id = ?", (self.viewer.id,))
        mini_jobs.tick(threading.Event())
        with database.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM mini_user_sessions WHERE expires_at <= ?", (int(time.time()),)).fetchone()[0], 0)
            self.assertTrue(conn.execute("SELECT 1 FROM pg_indexes WHERE indexname = 'idx_mini_sessions_expires'").fetchone())

    def test_login_still_trims_each_account_to_ten_sessions(self):
        for _ in range(12):
            mini_auth.login_password(self.viewer.username, "test-password")
        with database.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM mini_user_sessions WHERE user_id = ?", (self.viewer.id,)).fetchone()[0], 10)

    # ── 订单列表：退款与下单人一次 JOIN 带出 ──

    def seed_orders(self, count):
        plan = mini_orders.save_plan(PlanInput(name="测试月会员", days=30, price_fen=1990, is_active=True))
        now = int(time.time())
        with database.db() as conn:
            for index in range(count):
                identifier = f"{index:032x}"
                conn.execute("INSERT INTO mini_orders(id, user_id, request_key, plan_id, plan_name, plan_days, amount_fen, appid, mchid, payer_enc, "
                             "status, paid_at, created_at, expires_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'wx', 'mch', '', 'paid', ?, ?, ?, ?)",
                             (identifier, self.viewer.id if index % 2 else self.other.id, "key-" + identifier, plan["id"], plan["name"], plan["days"], plan["price_fen"],
                              now, now - index, now + 900, now))
                if index % 3 == 0:
                    conn.execute("INSERT INTO mini_refunds(id, order_id, reason, created_at, updated_at) VALUES (?, ?, '整单退款', ?, ?)", ("refund-" + identifier, identifier, now, now))
        return plan

    def test_order_listing_uses_a_bounded_number_of_queries(self):
        self.seed_orders(30)
        with count_queries() as counter:
            mine = mini_orders.listing(self.viewer.id, limit=50)
        self.assertEqual(len(mine["items"]), 15)
        self.assertEqual(counter["n"], 3)
        with count_queries() as counter:
            everything = mini_orders.listing(limit=50)
        self.assertEqual(len(everything["items"]), 30)
        self.assertEqual(counter["n"], 3)
        for item in everything["items"]:
            single = mini_orders.detail(item["id"])
            self.assertEqual(item, single)
        with_refund = next(item for item in everything["items"] if item["refund"])
        self.assertEqual(with_refund["refund"]["status"], "requested")
        self.assertEqual({item["username"] for item in everything["items"]}, {self.viewer.username, self.other.username})
        self.assertNotIn("username", mine["items"][0])
        self.assertEqual(mini_orders.listing(status="refund_requested", limit=50)["total"], 10)

    def test_order_listing_marks_deleted_owners(self):
        self.seed_orders(2)
        with database.db() as conn:
            conn.execute("UPDATE mini_orders SET user_id = NULL WHERE user_id = ?", (self.other.id,))
        items = mini_orders.listing(limit=50)["items"]
        orphan = next(item for item in items if item["user_id"] is None)
        self.assertEqual((orphan["username"], orphan["nickname"]), ("已注销用户", ""))
        self.assertEqual(orphan, mini_orders.detail(orphan["id"]))

    # ── 专题：所有条目一次聚合查询 ──

    def test_topics_use_two_queries_regardless_of_topic_count(self):
        first, second, hidden = self.publish(), self.publish(), self.draft()
        for index in range(5):
            body = {"title": f"专题 {index}", "is_visible": index != 4, "paper_ids": [second["id"], hidden["id"], first["id"]]}
            self.assertEqual(self.client.post("/api/v1/admin/experience/topics", json=body).status_code, 201)
        with count_queries() as counter:
            public = catalog_ops.topics()
        self.assertEqual(counter["n"], 2)
        self.assertEqual(len(public["items"]), 4)
        for topic in public["items"]:
            self.assertEqual(topic["paper_ids"], [second["id"], first["id"]])
            self.assertEqual(topic["paper_count"], 2)
        with count_queries() as counter:
            admin = catalog_ops.topics(admin=True)
        self.assertEqual(counter["n"], 2)
        self.assertEqual(len(admin["items"]), 5)
        self.assertEqual([item["paper_ids"] for item in admin["items"]], [[second["id"], hidden["id"], first["id"]]] * 5)
        self.assertEqual(admin["items"][0]["papers"][1]["status"], "draft")
        self.assertEqual(self.client.get("/api/v1/site/topics").json()["items"][0]["paper_count"], 2)

    # ── 公开详情：顶层 difficulty，不再返回快照；后台详情两者都有 ──

    def test_public_detail_exposes_difficulty_without_snapshot(self):
        paper = self.publish()
        self.sign_in(self.viewer)
        detail = self.client.get(f"/api/v1/catalog/papers/{paper['id']}").json()
        self.assertEqual(detail["difficulty"], "medium")
        self.assertNotIn("snapshot", detail)
        self.assertNotIn("sections", detail)
        self.sign_in(self.admin)
        admin = self.client.get(f"/api/v1/admin/catalog/papers/{paper['id']}").json()
        self.assertEqual(admin["difficulty"], "medium")
        self.assertEqual(admin["snapshot"]["paper"]["difficulty"], "medium")
        self.assertEqual(self.client.get(f"/api/v1/admin/catalog/papers/{paper['id']}/preview?membership=vip").json()["snapshot"]["paper"]["title"], paper["title"])
        with database.db() as conn:
            # 只抹掉难度字段，快照其余部分保持合法（打印版本列表也会解析它）
            conn.execute("UPDATE paper_archives SET snapshot_json = (snapshot_json::jsonb #- '{paper,difficulty}')::text")
        self.sign_in(self.viewer)
        self.assertIsNone(self.client.get(f"/api/v1/catalog/papers/{paper['id']}").json()["difficulty"])

    # ── /mini/me 与 /catalog/summary 附带未读数 ──

    def test_me_and_summary_carry_unread_counts(self):
        self.sign_in(self.viewer)
        self.assertEqual(self.client.get("/api/v1/mini/me").json()["unread"], 0)
        with database.db() as conn:
            mini_messages.notify(conn, self.viewer.id, "opt-one", "paper", "资料更新", "内容", "paper", "")
            mini_messages.notify(conn, self.viewer.id, "opt-two", "paper", "资料更新", "内容", "paper", "")
        me = self.client.get("/api/v1/mini/me").json()
        self.assertEqual(me["unread"], 2)
        self.assertEqual(me["id"], self.viewer.id)
        self.assertEqual(self.client.get("/api/v1/catalog/summary").json()["unread"], 2)
        self.assertEqual(self.client.post("/api/v1/mini/messages/read-all").json()["unread"], 0)
        self.assertEqual(self.client.get("/api/v1/mini/me").json()["unread"], 0)
        self.sign_in(self.other)
        self.assertEqual(self.client.get("/api/v1/mini/me").json()["unread"], 0)
        self.client.headers.pop("Authorization", None)
        self.assertEqual(self.client.get("/api/v1/catalog/summary").json()["unread"], 0)

    # ── 收件箱读路径无全局锁：与持有 accounts 锁的事务并发也不阻塞 ──

    def test_inbox_reads_do_not_wait_for_the_accounts_lock(self):
        held = threading.Event()
        release = threading.Event()

        def hold():
            with database.db(serialized="accounts"):
                held.set()
                release.wait(10)

        holder = threading.Thread(target=hold)
        holder.start()
        self.assertTrue(held.wait(5))
        try:
            started = time.perf_counter()
            self.assertEqual(mini_messages.inbox(self.viewer.id)["unread"], 0)
            self.assertEqual(mini_messages.read(self.viewer.id)["unread"], 0)
            self.assertEqual(mini_auth.update_profile(self.viewer.id, fixtures.MiniProfileUpdate(nickname="并发昵称"))["nickname"], "并发昵称")
            self.assertTrue(mini_auth.login_password(self.viewer.username, "test-password")["token"])
            self.assertLess(time.perf_counter() - started, 5)
        finally:
            release.set()
            holder.join()


if __name__ == "__main__":
    unittest.main()
