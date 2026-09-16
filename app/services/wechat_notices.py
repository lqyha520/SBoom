"""Explicit WeChat subscription grants; local inbox remains the durable source."""

import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone, timedelta

import httpx
from app.config import get_settings
from app.db import db
from app.security import decrypt_secret, encrypt_secret
from app.services.mini_errors import fail

logger = logging.getLogger(__name__)


def configuration():
    settings = get_settings()
    fields = [settings.wechat_subscribe_title_field, settings.wechat_subscribe_body_field, settings.wechat_subscribe_time_field]
    valid = bool(settings.wechat_app_id and settings.wechat_app_secret and settings.wechat_subscribe_template_id and
                 re.fullmatch(r"(?:thing|phrase)\d+", fields[0]) and re.fullmatch(r"thing\d+", fields[1]) and
                 re.fullmatch(r"(?:time|date)\d+", fields[2]) and len(set(fields)) == 3)
    return {"available": valid, "template_id": settings.wechat_subscribe_template_id if valid else ""}


def grant(user_id, body):
    settings = configuration()
    if not settings["available"] or body.template_id != settings["template_id"]:
        fail("微信提醒暂未开启或模板已更新，请刷新后重试", 409)
    now = int(time.time())
    identifier = hashlib.sha256((user_id + ":" + body.request_id).encode()).hexdigest()
    with db(serialized=True) as conn:
        user = conn.execute("SELECT wechat_openid_enc FROM mini_users WHERE id = ?", (user_id,)).fetchone()
        if not user or not user[0]:
            fail("请在微信小程序登录后订阅提醒", 422)
        conn.execute("DELETE FROM mini_subscription_receipts WHERE user_id = ? AND created_at < ?", (user_id, now - 86400))
        if conn.execute("SELECT 1 FROM mini_subscription_receipts WHERE id = ?", (identifier,)).fetchone():
            return {"accepted": True}
        if conn.execute("SELECT COUNT(*) FROM mini_subscription_receipts WHERE user_id = ?", (user_id,)).fetchone()[0] >= 20:
            fail("今日订阅次数已达上限", 429)
        conn.execute("INSERT INTO mini_subscription_receipts(id, user_id, created_at) VALUES (?, ?, ?)", (identifier, user_id, now))
        old = conn.execute("SELECT * FROM mini_notice_subscriptions WHERE user_id = ?", (user_id,)).fetchone()
        credits = min(20, old["credits"] + 1) if old and old["template_id"] == body.template_id else 1
        conn.execute("INSERT INTO mini_notice_subscriptions(user_id, template_id, credits, updated_at) VALUES (?, ?, ?, ?) "
                     "ON CONFLICT(user_id) DO UPDATE SET template_id = excluded.template_id, credits = excluded.credits, updated_at = excluded.updated_at", (user_id, body.template_id, credits, now))
    return {"accepted": True}


def access_token():
    settings = get_settings()
    key = "mini_wechat_access:" + settings.wechat_app_id
    with db() as conn:
        row = conn.execute("SELECT value FROM app_config WHERE key = ?", (key,)).fetchone()
    if row:
        data = json.loads(row[0])
        if data["expires_at"] > time.time() + 120:
            value = decrypt_secret(data["token"])
            if value:
                return value
    with httpx.Client(timeout=10, follow_redirects=False) as client:
        response = client.post("https://api.weixin.qq.com/cgi-bin/stable_token", json={"grant_type": "client_credential", "appid": settings.wechat_app_id, "secret": settings.wechat_app_secret, "force_refresh": False})
        response.raise_for_status()
        value = response.json()
    if not isinstance(value, dict) or value.get("errcode") or not isinstance(value.get("access_token"), str):
        raise ValueError("WECHAT_ACCESS_UNAVAILABLE")
    expires = min(7200, max(60, int(value.get("expires_in", 7200))))
    with db(serialized=True) as conn:
        conn.execute("INSERT INTO app_config(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, json.dumps({"token": encrypt_secret(value["access_token"]), "expires_at": int(time.time()) + expires})))
    return value["access_token"]


def destination(message):
    routes = {"paper": "pages/paper/index", "feedback": "pages/support/index", "membership": "pages/membership/index", "request": "pages/requests/index", "closure": "pages/closure/index", "order": "pages/orders/index"}
    page = routes.get(message["target_type"], "pages/messages/index")
    identifier = message["target_id"]
    return page + ("?id=" + identifier if re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", identifier) else "")


def send(message, openid, template_id):
    settings = get_settings()
    stamp = datetime.fromtimestamp(message["created_at"], timezone(timedelta(hours=8)))
    data = {
        settings.wechat_subscribe_title_field: {"value": message["title"][:5 if settings.wechat_subscribe_title_field.startswith("phrase") else 20]},
        settings.wechat_subscribe_body_field: {"value": message["body"].replace("\n", " ")[:20] or "请打开小程序查看"},
        settings.wechat_subscribe_time_field: {"value": stamp.strftime("%Y-%m-%d" if settings.wechat_subscribe_time_field.startswith("date") else "%Y-%m-%d %H:%M")},
    }
    with httpx.Client(timeout=10, follow_redirects=False) as client:
        response = client.post("https://api.weixin.qq.com/cgi-bin/message/subscribe/send", params={"access_token": access_token()}, json={"touser": openid, "template_id": template_id, "page": destination(message), "data": data})
        response.raise_for_status()
        value = response.json()
    if not isinstance(value, dict) or "errcode" not in value:
        raise ValueError("INVALID_WECHAT_RESPONSE")
    return int(value["errcode"])


def dispatch_one():
    if not configuration()["available"]:
        return False
    now = int(time.time())
    with db(serialized=True) as conn:
        # A timed-out send may already have reached WeChat. Never blindly retry it.
        conn.execute("UPDATE mini_notice_deliveries SET status = 'unknown', error_code = 'INTERRUPTED' WHERE status = 'sending' AND lease_until < ?", (now,))
        row = conn.execute("SELECT n.*, u.wechat_openid_enc, u.is_active FROM mini_notice_deliveries d JOIN mini_notifications n ON n.id = d.notification_id JOIN mini_users u ON u.id = n.user_id WHERE d.status = 'pending' ORDER BY n.created_at, n.id LIMIT 1").fetchone()
        if not row:
            return False
        subscription = conn.execute("SELECT * FROM mini_notice_subscriptions WHERE user_id = ?", (row["user_id"],)).fetchone()
        if not row["is_active"] or not row["wechat_openid_enc"] or not subscription or subscription["credits"] <= 0 or subscription["template_id"] != configuration()["template_id"]:
            conn.execute("UPDATE mini_notice_deliveries SET status = 'skipped', updated_at = ? WHERE notification_id = ?", (now, row["id"]))
            return True
        conn.execute("UPDATE mini_notice_subscriptions SET credits = credits - 1 WHERE user_id = ?", (row["user_id"],))
        conn.execute("UPDATE mini_notice_deliveries SET status = 'sending', attempts = attempts + 1, lease_until = ?, updated_at = ? WHERE notification_id = ?", (now + 60, now, row["id"]))
        message, template_id = dict(row), subscription["template_id"]
    try:
        code = send(message, decrypt_secret(message["wechat_openid_enc"]), template_id)
        state, error = ("sent", "") if code == 0 else ("failed", str(code))
    except (httpx.HTTPError, ValueError, TypeError):
        state, error = "unknown", "DELIVERY_UNCONFIRMED"
    with db(serialized=True) as conn:
        conn.execute("UPDATE mini_notice_deliveries SET status = ?, error_code = ?, lease_until = 0, updated_at = ? WHERE notification_id = ? AND status = 'sending'", (state, error, int(time.time()), message["id"]))
    return True


def status():
    with db() as conn:
        counts = {row["status"]: row["count"] for row in conn.execute("SELECT status, COUNT(*) AS count FROM mini_notice_deliveries GROUP BY status")}
    return {**configuration(), "delivery_counts": counts}
