"""微信小程序虚拟支付：签名、查单履约、发货、退款与消息推送。"""

import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import httpx
import test_backend_catalog as fixtures  # noqa: F401  Initializes isolated environment before app imports.
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import HTTPException
from test_backend_growth import GrowthBase

from app import db as database
from app import security
from app.config import get_settings
from app.models.commerce import OrderInput, PlanInput, RefundInput, RefundReview
from app.services import mini_auth, mini_orders, mini_refunds, payment_bills, wechat_virtual_pay
from app.services.wechat_virtual_pay import VirtualPay

OFFER_ID = "1450000000"
APP_KEY = "fixture-app-key"
SANDBOX_APP_KEY = "fixture-sandbox-app-key"
SESSION_KEY = "fixture-session-key"


class VirtualPayContracts(GrowthBase):
    def configure(self, **overrides):
        values = {
            "wechat_virtual_pay_enabled": True,
            "wechat_app_id": "wx0123456789abcdef",
            "wechat_app_secret": "fixture-secret",
            "wechat_virtual_offer_id": OFFER_ID,
            "wechat_virtual_app_key": APP_KEY,
            "wechat_virtual_sandbox_app_key": SANDBOX_APP_KEY,
            "wechat_virtual_env": 0,
            "wechat_virtual_ios_enabled": False,
            "wechat_virtual_push_token": "",
            "wechat_virtual_push_aes_key": "",
        }
        values.update(overrides)
        for key, value in values.items():
            self.stack.enter_context(patch.object(get_settings(), key, value))
        self.stack.enter_context(patch.object(VirtualPay, "provide_goods", return_value={}))
        with database.db() as conn:
            conn.execute(
                "UPDATE mini_users SET wechat_identity = ?, wechat_openid_enc = ?, wechat_session_key_enc = ? WHERE id = ?",
                (mini_auth.digest(get_settings().wechat_app_id + ":fixture-openid"), security.encrypt_secret("fixture-openid"),
                 security.encrypt_secret(SESSION_KEY), self.viewer.id),
            )
        self.plan = mini_orders.save_plan(PlanInput(name="测试月会员", days=30, price_fen=1990, is_active=True, virtual_product_id="lc-month"))

    def create_order(self, key="virtual-order-one"):
        return mini_orders.create(self.viewer.id, OrderInput(plan_id=self.plan["id"], plan_revision=self.plan["revision"], request_id=key))

    def query_value(self, order, status=2, **changes):
        value = {
            "order_id": order["id"], "status": status, "order_fee": order["amount_fen"], "paid_fee": order["amount_fen"],
            "wx_order_id": "wxvirtual-" + order["id"], "order_type": 0,
            "env_type": 2 if get_settings().wechat_virtual_env == 1 else 1, "paid_time": int(time.time()),
        }
        value.update(changes)
        return value

    def encrypted_push(self, payload, appid=""):
        settings = get_settings()
        key = base64.b64decode(settings.wechat_virtual_push_aes_key + "=")
        message = json.dumps(payload, ensure_ascii=False).encode()
        raw = os.urandom(16) + len(message).to_bytes(4, "big") + message + (appid or settings.wechat_app_id).encode()
        pad = 32 - len(raw) % 32
        raw += bytes([pad]) * pad
        encryptor = Cipher(algorithms.AES(key), modes.CBC(key[:16])).encryptor()
        encrypted = base64.b64encode(encryptor.update(raw) + encryptor.finalize()).decode()
        timestamp, nonce = str(int(time.time())), "fixture-nonce"
        signature = hashlib.sha1("".join(sorted([settings.wechat_virtual_push_token, timestamp, nonce, encrypted])).encode()).hexdigest()
        return json.dumps({"Encrypt": encrypted}).encode(), {"Timestamp": timestamp, "Nonce": nonce, "Msg-Signature": signature, "Content-Type": "application/json"}

    def test_configuration_requires_environment_app_key_and_plan_product(self):
        self.configure(wechat_virtual_app_key="")
        config = wechat_virtual_pay.configuration()
        self.assertFalse(config["ready"])
        self.assertIn("对应环境的 AppKey", config["missing"])
        with self.assertRaises(HTTPException) as unavailable:
            self.create_order()
        self.assertEqual(unavailable.exception.status_code, 503)

        self.configure()
        missing_plan = mini_orders.save_plan(PlanInput(name="缺少商品", days=30, price_fen=990, is_active=True))
        with self.assertRaises(HTTPException) as missing:
            mini_orders.create(self.viewer.id, OrderInput(plan_id=missing_plan["id"], plan_revision=missing_plan["revision"], request_id="missing-product"))
        self.assertEqual(missing.exception.status_code, 422)

    def test_wechat_session_refresh_rebinds_only_the_same_account(self):
        self.configure()
        identity = mini_auth.digest(get_settings().wechat_app_id + ":fixture-openid")
        with self.assertRaises(HTTPException) as mismatch:
            mini_auth.refresh_wechat_session(self.viewer.id, "other-identity", "fixture-openid", "new-session-key")
        self.assertEqual(mismatch.exception.status_code, 409)
        self.assertEqual(mismatch.exception.detail["code"], "wechat_identity_mismatch")
        with self.assertRaises(HTTPException) as missing:
            mini_auth.refresh_wechat_session(self.viewer.id, identity, "fixture-openid", "")
        self.assertEqual(missing.exception.status_code, 409)
        self.assertEqual(missing.exception.detail["code"], "wechat_session_expired")
        mini_auth.refresh_wechat_session(self.viewer.id, identity, "fixture-openid", "new-session-key")
        order = self.create_order()
        payment = mini_orders.pay(order["id"], self.viewer.id)["payment"]
        self.assertEqual(payment["signature"], hmac.new(b"new-session-key", payment["signData"].encode(), hashlib.sha256).hexdigest())

    def test_plans_expose_virtual_channel_and_admin_configuration(self):
        self.configure()
        public = mini_orders.plans()
        self.assertEqual(public["checkout_channel"], "virtual")
        self.assertTrue(public["checkout_enabled"])
        self.assertFalse(public["ios_enabled"])
        admin = mini_orders.plans(True)
        self.assertTrue(admin["virtual_configuration"]["ready"])
        self.assertEqual(admin["virtual_configuration"]["offer_id"], OFFER_ID)
        self.assertFalse(admin["virtual_configuration"]["sandbox"])

    def test_payment_parameters_are_signed_and_paid_only_after_provider_query(self):
        self.configure()
        order = self.create_order()
        result = mini_orders.pay(order["id"], self.viewer.id)
        payment = result["payment"]
        self.assertEqual(payment["mode"], "short_series_goods")
        data = json.loads(payment["signData"])
        self.assertEqual(data, {
            "offerId": OFFER_ID, "buyQuantity": 1, "env": 0, "currencyType": "CNY",
            "productId": "lc-month", "goodsPrice": 1990, "outTradeNo": order["id"], "attach": self.plan["id"],
        })
        self.assertEqual(payment["paySig"], hmac.new(APP_KEY.encode(), ("requestVirtualPayment&" + payment["signData"]).encode(), hashlib.sha256).hexdigest())
        self.assertEqual(payment["signature"], hmac.new(SESSION_KEY.encode(), payment["signData"].encode(), hashlib.sha256).hexdigest())
        snapshot = mini_orders.detail(order["id"])
        self.assertEqual(snapshot["payment_channel"], "virtual")
        self.assertEqual(snapshot["status"], "pending")
        self.assertEqual(mini_auth.get_user(self.viewer.id).membership, "regular")

        value = self.query_value(order, 2)
        for change, status in (({"order_fee": 1, "paid_fee": 1}, 400), ({"paid_fee": 0}, 400), ({"env_type": 9}, 400), ({"wx_order_id": "short"}, 400), ({"status": 1}, 409)):
            with self.assertRaises(HTTPException) as invalid:
                mini_orders.confirm_virtual_payment({**value, **change})
            self.assertEqual(invalid.exception.status_code, status, change)
        self.assertEqual(mini_auth.get_user(self.viewer.id).membership, "regular")

        with patch.object(VirtualPay, "provide_goods") as provide:
            paid = mini_orders.confirm_virtual_payment(value)
            repeated = mini_orders.confirm_virtual_payment(value)
        self.assertEqual(paid["status"], "paid")
        self.assertEqual(repeated["status"], "paid")
        self.assertEqual(provide.call_count, 1)
        self.assertAlmostEqual(mini_auth.get_user(self.viewer.id).vip_expires_at, time.time() + 30 * 86400, delta=3)
        with database.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM mini_membership_grants WHERE order_id = ?", (order["id"],)).fetchone()[0], 1)
            row = conn.execute("SELECT delivered_at, virtual_order_id, virtual_product_id FROM mini_orders WHERE id = ?", (order["id"],)).fetchone()
            self.assertIsNotNone(row["delivered_at"])
            self.assertEqual(row["virtual_order_id"], value["wx_order_id"])
            self.assertEqual(row["virtual_product_id"], "lc-month")

    def test_ordinary_and_virtual_channels_cannot_confirm_each_others_orders(self):
        self.configure()
        order = self.create_order()
        with self.assertRaises(HTTPException) as mismatch:
            mini_orders.confirm_payment({
                "out_trade_no": order["id"], "trade_state": "SUCCESS", "appid": get_settings().wechat_app_id,
                "mchid": "1900000001", "payer": {"openid": "fixture-openid"}, "amount": {"total": 1990, "currency": "CNY"},
                "transaction_id": "wx-ordinary-" + order["id"], "success_time": "2026-10-23T00:00:00+00:00",
            })
        self.assertEqual(mismatch.exception.status_code, 400)
        with database.db() as conn:
            conn.execute("UPDATE mini_orders SET payment_channel = 'wechat' WHERE id = ?", (order["id"],))
        with self.assertRaises(HTTPException) as mismatch:
            mini_orders.confirm_virtual_payment(self.query_value(order, 2))
        self.assertEqual(mismatch.exception.status_code, 400)

    def test_sync_queries_provider_and_closes_only_when_provider_says_closed(self):
        self.configure()
        order = self.create_order()
        with patch.object(VirtualPay, "query_order", return_value=self.query_value(order, 2)) as query, patch.object(VirtualPay, "provide_goods") as provide:
            synced = mini_orders.sync(order["id"], self.viewer.id)
        self.assertEqual(synced["status"], "paid")
        query.assert_called_once_with("fixture-openid", order["id"])
        self.assertEqual(provide.call_count, 1)
        another = self.create_order("virtual-order-two")
        with patch.object(VirtualPay, "query_order", return_value=self.query_value(another, 6)):
            closed = mini_orders.sync(another["id"], self.viewer.id)
        self.assertEqual(closed["status"], "closed")

    def test_query_order_not_found_is_reported_as_missing_order(self):
        self.configure()
        order = self.create_order()
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"errcode": 268490002, "errmsg": "数据不存在"}))
        with patch.object(wechat_virtual_pay, "access_token", return_value="fixture-token"):
            with self.assertRaises(wechat_virtual_pay.PaymentError) as raised:
                VirtualPay(transport=transport).query_order("fixture-openid", order["id"])
        self.assertEqual(raised.exception.code, "XPAY_NOT_FOUND")
        self.assertIn("取消", str(raised.exception))

    def test_cancel_closes_locally_and_recovers_payment_completed_at_the_same_time(self):
        self.configure()
        order = self.create_order()
        mini_orders.pay(order["id"], self.viewer.id)
        with patch.object(VirtualPay, "query_order", return_value=self.query_value(order, 4, provide_time=int(time.time()))), patch.object(VirtualPay, "provide_goods"):
            result = mini_orders.cancel(order["id"], self.viewer.id)
        self.assertEqual(result["status"], "paid")
        self.assertEqual(mini_auth.get_user(self.viewer.id).membership, "vip")

    def test_virtual_refund_requires_review_and_settles_from_query(self):
        self.configure()
        order = self.create_order()
        mini_orders.confirm_virtual_payment(self.query_value(order, 2))
        mini_refunds.request(order["id"], self.viewer.id, RefundInput(reason="测试虚拟支付整单退款"))
        refund = mini_orders.detail(order["id"])["refund"]
        with patch.object(mini_refunds, "dispatch") as dispatch:
            reviewed = mini_refunds.review(self.admin.id, refund["id"], RefundReview(action="approve", revision=refund["revision"], reply="确认原路退回", confirm_refund=True))
        self.assertEqual(reviewed["refund"]["status"], "processing")
        self.assertEqual(dispatch.call_count, 1)
        settled = mini_refunds.settle_virtual(order["id"], self.query_value(order, 5, refund_fee=order["amount_fen"], wx_order_id="wxrefund-" + order["id"]))
        self.assertEqual(settled["status"], "refunded")
        self.assertLessEqual(mini_auth.get_user(self.viewer.id).vip_expires_at, time.time() + 2)
        with database.db() as conn:
            self.assertEqual(conn.execute("SELECT status FROM mini_refunds WHERE id = ?", (refund["id"],)).fetchone()[0], "success")

    def test_ios_virtual_refund_cannot_be_started_by_admin(self):
        self.configure()
        order = self.create_order()
        mini_orders.confirm_virtual_payment(self.query_value(order, 2, order_type=7))
        mini_refunds.request(order["id"], self.viewer.id, RefundInput(reason="iOS 用户申请退款"))
        refund = mini_orders.detail(order["id"])["refund"]
        with self.assertRaises(HTTPException) as blocked:
            mini_refunds.review(self.admin.id, refund["id"], RefundReview(action="approve", revision=refund["revision"], reply="尝试代为退款", confirm_refund=True))
        self.assertEqual(blocked.exception.status_code, 422)

    def test_refund_push_routes_to_refund_sync_and_settles(self):
        self.configure()
        order = self.create_order()
        mini_orders.confirm_virtual_payment(self.query_value(order, 2))
        mini_refunds.request(order["id"], self.viewer.id, RefundInput(reason="推送触发退款"))
        refund = mini_orders.detail(order["id"])["refund"]
        with patch.object(mini_refunds, "dispatch"):
            mini_refunds.review(self.admin.id, refund["id"], RefundReview(action="approve", revision=refund["revision"], reply="确认原路退回", confirm_refund=True))
        body = json.dumps({"Event": "xpay_refund_notify", "OutTradeNo": order["id"]}).encode()
        value = self.query_value(order, 5, refund_fee=order["amount_fen"], wx_order_id="wxrefund-" + order["id"])
        with patch.object(VirtualPay, "query_order", return_value=value) as query:
            response = self.client.post("/api/v1/payments/wechat/virtual-notify", content=body, headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200)
        query.assert_called_once_with("fixture-openid", order["id"])
        detail = mini_orders.detail(order["id"])
        self.assertEqual(detail["status"], "refunded")
        self.assertEqual(detail["refund"]["status"], "success")

    def test_push_url_verification_requires_a_signed_echo(self):
        self.configure(wechat_virtual_push_token="fixture-token", wechat_virtual_push_aes_key="a" * 43)
        timestamp, nonce, echo = str(int(time.time())), "fixture-nonce", "echo-value"
        query = {"timestamp": timestamp, "nonce": nonce, "echostr": echo}
        signature = hashlib.sha1("".join(sorted(["fixture-token", timestamp, nonce])).encode()).hexdigest()
        response = self.client.get("/api/v1/payments/wechat/virtual-notify", params={**query, "signature": signature})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, echo)
        invalid = self.client.get("/api/v1/payments/wechat/virtual-notify", params={**query, "signature": "0" * 40})
        self.assertEqual(invalid.status_code, 400)

    def test_push_triggers_query_and_never_trusts_the_push_body(self):
        self.configure()
        order = self.create_order()
        with patch.object(mini_orders, "sync", return_value={}) as sync:
            response = self.client.post("/api/v1/payments/wechat/virtual-notify", content=json.dumps({"Event": "xpay_goods_deliver_notify", "OutTradeNo": order["id"]}).encode(), headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ErrCode"], 0)
        sync.assert_called_once_with(order["id"])

    def test_encrypted_push_requires_a_valid_signature_and_appid(self):
        aes_key = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
        self.configure(wechat_virtual_push_token="fixture-token", wechat_virtual_push_aes_key=aes_key)
        order = self.create_order()
        body, headers = self.encrypted_push({"Event": "xpay_refund_notify", "OutTradeNo": order["id"]})
        with self.assertRaises(ValueError):
            wechat_virtual_pay.parse_push(body, {})
        self.assertEqual(self.client.post("/api/v1/payments/wechat/virtual-notify", content=body).status_code, 400)
        with patch.object(mini_refunds, "sync_order", return_value={}) as sync:
            response = self.client.post("/api/v1/payments/wechat/virtual-notify", content=body, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        sync.assert_called_once_with(order["id"])
        body, headers = self.encrypted_push({"Event": "xpay_goods_deliver_notify", "OutTradeNo": order["id"]})
        headers["Msg-Signature"] = "0" * 40
        self.assertEqual(self.client.post("/api/v1/payments/wechat/virtual-notify", content=body, headers=headers).status_code, 400)
        body, headers = self.encrypted_push({"Event": "xpay_goods_deliver_notify", "OutTradeNo": order["id"]}, appid="wx0000000000000000")
        self.assertEqual(self.client.post("/api/v1/payments/wechat/virtual-notify", content=body, headers=headers).status_code, 400)

    def test_encrypted_push_accepts_signature_in_query_string(self):
        aes_key = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
        self.configure(wechat_virtual_push_token="fixture-token", wechat_virtual_push_aes_key=aes_key)
        order = self.create_order()
        body, headers = self.encrypted_push({"Event": "xpay_refund_notify", "OutTradeNo": order["id"]})
        query = {"timestamp": headers["Timestamp"], "nonce": headers["Nonce"], "msg_signature": headers["Msg-Signature"]}
        with patch.object(mini_refunds, "sync_order", return_value={}) as sync:
            response = self.client.post("/api/v1/payments/wechat/virtual-notify", content=body, params=query)
        self.assertEqual(response.status_code, 200, response.text)
        sync.assert_called_once_with(order["id"])
        body, headers = self.encrypted_push({"Event": "xpay_goods_deliver_notify", "OutTradeNo": order["id"]})
        query = {"timestamp": headers["Timestamp"], "nonce": headers["Nonce"], "msg_signature": "0" * 40}
        self.assertEqual(self.client.post("/api/v1/payments/wechat/virtual-notify", content=body, params=query).status_code, 400)

    def test_virtual_payments_stay_out_of_ordinary_bill_reconciliation(self):
        self.configure()
        order = self.create_order()
        mini_orders.confirm_virtual_payment(self.query_value(order, 2))
        day = datetime.now(payment_bills.ZONE) - timedelta(days=1)
        stamp = int(datetime.combine(day.date(), datetime.min.time(), payment_bills.ZONE).timestamp()) + 3600
        with database.db() as conn:
            conn.execute("UPDATE mini_orders SET paid_at = ? WHERE id = ?", (stamp, order["id"]))
        with database.db() as conn:
            summary, differences = payment_bills.compare(conn, [], day.date().isoformat())
        self.assertEqual(summary["local_paid_fen"], 0)
        self.assertEqual(differences, [])
        exported = payment_bills.export_orders()
        self.assertIn(order["id"], exported)
        self.assertIn("虚拟支付", exported)
