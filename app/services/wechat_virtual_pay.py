"""微信小程序虚拟支付（XPay）：固定域名、HMAC 签名、查单/退款/发货与消息推送。"""

import base64
import hashlib
import hmac
import json
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from urllib.parse import urlencode

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.config import get_settings
from app.services.wechat_notices import access_token
from app.services.wechat_pay import PaymentError

API_ORIGIN = "https://api.weixin.qq.com"
logger = logging.getLogger(__name__)

_HTTP_LIMITS = httpx.Limits(max_connections=5, max_keepalive_connections=5)
_http_lock = threading.Lock()
_http_shared: httpx.Client | None = None


def _http_client() -> httpx.Client:
    global _http_shared
    if _http_shared is None or _http_shared.is_closed:
        with _http_lock:
            if _http_shared is None or _http_shared.is_closed:
                _http_shared = httpx.Client(timeout=12, follow_redirects=False, limits=_HTTP_LIMITS)
    return _http_shared


def configuration():
    settings = get_settings()
    env = 1 if settings.wechat_virtual_env == 1 else 0
    app_key = settings.wechat_virtual_sandbox_app_key if env == 1 else settings.wechat_virtual_app_key
    checks = {
        "微信 AppID": bool(re.fullmatch(r"wx[a-zA-Z0-9]{16}", settings.wechat_app_id)),
        "小程序 AppSecret": bool(settings.wechat_app_secret),
        "OfferID": bool(re.fullmatch(r"\d{1,20}", settings.wechat_virtual_offer_id)),
        "对应环境的 AppKey": bool(app_key),
    }
    if settings.wechat_virtual_push_token:
        checks["消息推送 EncodingAESKey"] = len(settings.wechat_virtual_push_aes_key) == 43
    missing = [name for name, valid in checks.items() if not valid]
    return {"enabled": settings.wechat_virtual_pay_enabled,
            "ready": settings.wechat_virtual_pay_enabled and not missing,
            "missing": missing, "env": env, "sandbox": env == 1,
            "offer_id": settings.wechat_virtual_offer_id,
            "ios_enabled": settings.wechat_virtual_ios_enabled,
            "mode": "short_series_goods"}


def _app_key():
    settings = get_settings()
    return settings.wechat_virtual_sandbox_app_key if settings.wechat_virtual_env == 1 else settings.wechat_virtual_app_key


def _digest(key: str, message: str) -> str:
    return hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def pay_signature(data: str) -> str:
    return _digest(_app_key(), "requestVirtualPayment&" + data)


def user_signature(data: str, session_key: str) -> str:
    return _digest(session_key, data)


class VirtualPay:
    def __init__(self, transport=None):
        if not configuration()["ready"]:
            raise PaymentError("NOT_CONFIGURED", "小程序虚拟支付尚未配置完成，请联系客服")
        self.settings = get_settings()
        self.transport = transport

    @contextmanager
    def _client(self, timeout: float):
        if self.transport is not None:
            with httpx.Client(timeout=timeout, follow_redirects=False, transport=self.transport) as client:
                yield client
        else:
            yield _http_client()

    def _request(self, endpoint, payload):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        signature = _digest(_app_key(), endpoint + "&" + body)
        url = API_ORIGIN + endpoint + "?" + urlencode({"access_token": access_token(), "pay_sig": signature})
        try:
            with self._client(12) as client:
                response = client.post(url, content=body.encode("utf-8"), headers={"Content-Type": "application/json", "Accept": "application/json"}, timeout=12)
            if len(response.content) > 1048576:
                raise PaymentError("OVERSIZED_RESPONSE", "微信支付返回内容异常，请稍后重试")
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Invalid response")
        except (httpx.HTTPError, ValueError) as error:
            raise PaymentError("XPAY_UNAVAILABLE", "微信支付服务暂不可用，请稍后重试") from error
        errcode = data.get("errcode", 0)
        if errcode:
            logger.warning("XPay API %s failed errcode=%s errmsg=%s", endpoint, errcode, data.get("errmsg", ""))
            if errcode in (-1, 268490011, 268490014):
                raise PaymentError("XPAY_PENDING", "支付结果生成中，请稍后刷新订单")
            if errcode == 268490009:
                raise PaymentError("XPAY_SESSION_EXPIRED", "微信支付登录态已过期，请重新进入小程序后重试")
            if errcode == 268490003:
                raise PaymentError("XPAY_SIGNATURE", "虚拟支付签名校验失败，请检查 AppKey 配置")
            raise PaymentError("XPAY_" + str(errcode), "微信支付服务暂不可用，请稍后重试")
        return data

    def payment_parameters(self, order, session_key):
        data = json.dumps({
            "offerId": order["virtual_offer_id"] or self.settings.wechat_virtual_offer_id,
            "buyQuantity": 1,
            "env": order["virtual_env"],
            "currencyType": "CNY",
            "productId": order["virtual_product_id"],
            "goodsPrice": order["amount_fen"],
            "outTradeNo": order["id"],
            "attach": order["plan_id"][:64],
        }, ensure_ascii=False, separators=(",", ":"))
        return {"mode": "short_series_goods", "signData": data, "paySig": pay_signature(data),
                "signature": user_signature(data, session_key)}

    def query_order(self, openid, order_id):
        value = self._request("/xpay/query_order", {"openid": openid, "env": configuration()["env"], "order_id": order_id})
        order = value.get("order")
        if not isinstance(order, dict):
            raise PaymentError("INVALID_RESPONSE", "微信支付查询结果异常，请稍后重试")
        return order

    def refund_order(self, order, refund, openid):
        payload = {
            "openid": openid, "env": configuration()["env"], "order_id": order["id"],
            "refund_order_id": refund["id"], "left_fee": order["amount_fen"], "refund_fee": order["amount_fen"],
            "refund_reason": "5", "req_from": "2", "biz_meta": order["plan_id"][:64],
        }
        return self._request("/xpay/refund_order", payload)

    def provide_goods(self, order):
        return self._request("/xpay/notify_provide_goods", {"env": configuration()["env"], "order_id": order["id"]})


def _xml_dict(raw: bytes):
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("Unsupported XML declaration")
    root = ET.fromstring(raw)
    return {child.tag: (child.text or "") for child in root}


def _sha1(*values):
    return hashlib.sha1("".join(sorted(values)).encode("utf-8")).hexdigest()


def verify_push_url(signature: str, timestamp: str, nonce: str) -> bool:
    """后台保存消息推送地址时，微信会发起 GET 校验并要求原样返回 echostr。"""
    settings = get_settings()
    if not settings.wechat_virtual_push_token or not signature or not timestamp or not nonce:
        return False
    return hmac.compare_digest(_sha1(settings.wechat_virtual_push_token, timestamp, nonce), signature)


def _decrypt_push(encrypted: str):
    settings = get_settings()
    key = base64.b64decode(settings.wechat_virtual_push_aes_key + "=")
    raw = base64.b64decode(encrypted)
    if len(key) != 32 or len(raw) < 32 or len(raw) % 16:
        raise ValueError("Invalid encrypted push")
    decryptor = Cipher(algorithms.AES(key), modes.CBC(key[:16])).decryptor()
    plain = decryptor.update(raw) + decryptor.finalize()
    pad = plain[-1]
    if not 1 <= pad <= 32:
        raise ValueError("Invalid padding")
    plain = plain[:-pad]
    message = plain[16:]
    length = int.from_bytes(message[:4], "big")
    content = message[4:4 + length]
    appid = message[4 + length:]
    if not content or appid.decode("utf-8", "ignore") != settings.wechat_app_id:
        raise ValueError("Invalid push payload")
    return content


def parse_push(raw: bytes, headers: dict, query: dict | None = None):
    """解析普通或加密的虚拟支付消息推送；只把推送当触发器，最终状态仍以查单为准。

    虚拟支付推送把 timestamp / nonce / msg_signature 放在 URL 查询参数里（和公众号
    推送放 HTTP 头不同），两处都要兼容：查询参数兜底，同名 HTTP 头优先。
    """
    settings = get_settings()
    is_json = not raw.lstrip().startswith(b"<")
    body = raw
    if settings.wechat_virtual_push_token:
        values = {str(key).lower(): value for key, value in (query or {}).items()}
        values.update({str(key).lower(): value for key, value in headers.items()})
        timestamp, nonce = values.get("timestamp", ""), values.get("nonce", "")
        signature = values.get("msg-signature") or values.get("msg_signature") or ""
        if not timestamp or not nonce or not signature or abs(int(time.time()) - int(timestamp)) > 600:
            raise ValueError("Invalid push signature")
        if is_json:
            wrapper = json.loads(raw)
            encrypted = wrapper.get("Encrypt") if isinstance(wrapper, dict) else ""
        else:
            encrypted = _xml_dict(raw).get("Encrypt", "")
        if not isinstance(encrypted, str) or not encrypted:
            raise ValueError("Missing encrypted payload")
        if not hmac.compare_digest(_sha1(settings.wechat_virtual_push_token, timestamp, nonce, encrypted), signature):
            raise ValueError("Invalid push signature")
        body = _decrypt_push(encrypted)
        is_json = not body.lstrip().startswith(b"<")
    data = json.loads(body) if is_json else _xml_dict(body)
    if not isinstance(data, dict):
        raise ValueError("Invalid push payload")
    normalized = {str(key).lower(): value for key, value in data.items()}
    return {
        "event": normalized.get("event", ""),
        "out_trade_no": normalized.get("outtradeno") or normalized.get("mchorderno") or normalized.get("mchorderid") or "",
        "mch_refund_id": normalized.get("mchrefundid") or normalized.get("mchrefundno") or "",
        "wx_order_id": normalized.get("wxorderid") or "",
        "refund_fee": normalized.get("refundfee") or 0,
        "env": normalized.get("env") or 0,
    }, is_json


def success_response(is_json: bool):
    if is_json:
        return json.dumps({"errcode": 0, "errmsg": "ok", "ErrCode": 0, "ErrMsg": "success"})
    return "<xml><return_code>SUCCESS</return_code><return_msg>OK</return_msg><ErrCode>0</ErrCode><ErrMsg><![CDATA[success]]></ErrMsg></xml>"
