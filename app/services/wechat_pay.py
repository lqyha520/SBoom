"""WeChat Pay API v3: fixed hosts, RSA signatures, authenticated callback decryption."""

import base64
import hashlib
import json
import re
import secrets
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography import x509
from cryptography.exceptions import InvalidSignature, InvalidTag, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.types import PublicKeyTypes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.config import get_settings

API_ORIGIN = "https://api.mch.weixin.qq.com"


class PaymentError(Exception):
    def __init__(self, code="UNAVAILABLE"):
        self.code = code if re.fullmatch(r"[A-Z0-9_]{1,80}", code) else "UNAVAILABLE"
        super().__init__("微信支付服务暂不可用，请稍后重试")


@lru_cache(maxsize=4)
def _key_material(private_path, private_stat, public_path, public_stat, serial):
    # File metadata is part of the cache key so replacing a key reloads it.
    private_bytes = Path(private_path).read_bytes()
    public_bytes = Path(public_path).read_bytes()
    if len(private_bytes) > 32768 or len(public_bytes) > 32768:
        raise ValueError("Oversized key")
    private = serialization.load_pem_private_key(private_bytes, password=None)
    certificate = None
    # 证书公钥与裸公钥是两种不同的联合类型，显式标注为完整的公钥联合，避免分支间类型冲突
    public: PublicKeyTypes
    if b"BEGIN CERTIFICATE" in public_bytes:
        certificate = x509.load_pem_x509_certificate(public_bytes)
        if format(certificate.serial_number, "X").upper() != serial.upper():
            raise ValueError("Platform serial mismatch")
        public = certificate.public_key()
    else:
        public = serialization.load_pem_public_key(public_bytes)
    if not isinstance(private, rsa.RSAPrivateKey) or not isinstance(public, rsa.RSAPublicKey) or private.key_size < 2048 or public.key_size < 2048:
        raise ValueError("RSA 2048 or stronger required")
    return private, public, certificate


def _keys(settings):
    try:
        paths = [Path(settings.wechat_pay_private_key_path), Path(settings.wechat_pay_platform_key_path)]
        stats = [(path.stat().st_mtime_ns, path.stat().st_size) for path in paths]
        private, public, certificate = _key_material(str(paths[0]), stats[0], str(paths[1]), stats[1], settings.wechat_pay_platform_serial)
        if certificate and not certificate.not_valid_before_utc <= datetime.now(timezone.utc) <= certificate.not_valid_after_utc:
            raise ValueError("Expired platform certificate")
        return private, public
    except (OSError, ValueError, TypeError, UnsupportedAlgorithm) as error:
        raise PaymentError("INVALID_KEYS") from error


def configuration():
    settings = get_settings()
    def key_exists(value):
        try:
            return bool(value and Path(value).is_file() and Path(value).stat().st_size <= 32768)
        except (OSError, ValueError):
            return False
    checks = {
        "微信 AppID": bool(re.fullmatch(r"wx[a-zA-Z0-9]{16}", settings.wechat_app_id)),
        "商户号": bool(re.fullmatch(r"\d{6,20}", settings.wechat_pay_mchid)),
        "商户证书序列号": bool(re.fullmatch(r"[A-Za-z0-9_]{8,128}", settings.wechat_pay_serial_no)),
        "商户私钥": key_exists(settings.wechat_pay_private_key_path),
        "微信支付公钥/证书编号": bool(re.fullmatch(r"[A-Za-z0-9_]{8,128}", settings.wechat_pay_platform_serial)),
        "微信支付公钥/证书": key_exists(settings.wechat_pay_platform_key_path),
        "API v3 密钥": len(settings.wechat_pay_api_v3_key.encode()) == 32,
    }
    origin = settings.wechat_pay_notify_origin.rstrip("/")
    try:
        parsed = urlsplit(origin)
        checks["HTTPS 回调域名"] = bool(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password and not parsed.path and not parsed.query and not parsed.fragment and parsed.port in (None, 443))
    except ValueError:
        checks["HTTPS 回调域名"] = False
    if checks["商户私钥"] and checks["微信支付公钥/证书"]:
        try:
            _keys(settings)
            checks["密钥格式与证书有效期"] = True
        except PaymentError:
            checks["密钥格式与证书有效期"] = False
    missing = [name for name, valid in checks.items() if not valid]
    return {"enabled": settings.wechat_pay_enabled, "ready": settings.wechat_pay_enabled and not missing,
            "missing": missing, "ios_enabled": settings.wechat_pay_ios_enabled,
            "payment_callback": origin + "/api/v1/payments/wechat/notify" if origin else "",
            "refund_callback": origin + "/api/v1/payments/wechat/refund-notify" if origin else ""}


class WeChatPay:
    def __init__(self, transport=None):
        if not configuration()["ready"]:
            raise PaymentError("NOT_CONFIGURED")
        self.settings = get_settings()
        self.transport = transport
        self.private, self.public = _keys(self.settings)

    def sign(self, value):
        return base64.b64encode(self.private.sign(value.encode(), padding.PKCS1v15(), hashes.SHA256())).decode()

    def headers(self, method, path, body):
        stamp, nonce = str(int(time.time())), secrets.token_hex(16)
        signature = self.sign(f"{method}\n{path}\n{stamp}\n{nonce}\n{body}\n")
        authorization = (f'WECHATPAY2-SHA256-RSA2048 mchid="{self.settings.wechat_pay_mchid}",nonce_str="{nonce}",'
                         f'timestamp="{stamp}",serial_no="{self.settings.wechat_pay_serial_no}",signature="{signature}"')
        return {"Authorization": authorization, "Accept": "application/json", "Content-Type": "application/json",
                "Wechatpay-Serial": self.settings.wechat_pay_platform_serial}

    def verify(self, headers, body):
        values = {key.lower(): value for key, value in headers.items()}
        try:
            timestamp = values["wechatpay-timestamp"]
            nonce = values["wechatpay-nonce"]
            if len(nonce) > 128 or abs(int(time.time()) - int(timestamp)) > 300:
                raise ValueError("Expired signature")
            if values["wechatpay-serial"] != self.settings.wechat_pay_platform_serial:
                raise ValueError("Unknown verification key")
            signature = base64.b64decode(values["wechatpay-signature"], validate=True)
            self.public.verify(signature, timestamp.encode() + b"\n" + nonce.encode() + b"\n" + body + b"\n", padding.PKCS1v15(), hashes.SHA256())
        except (KeyError, ValueError, InvalidSignature, TypeError) as error:
            raise PaymentError("INVALID_SIGNATURE") from error

    def request(self, method, path, value=None):
        if not path.startswith("/v3/") or "\n" in path:
            raise PaymentError("INVALID_PATH")
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")) if value is not None else ""
        try:
            with httpx.Client(timeout=12, follow_redirects=False, transport=self.transport) as client:
                response = client.request(method, API_ORIGIN + path, content=body.encode(), headers=self.headers(method, path, body))
            if len(response.content) > 1048576:
                raise PaymentError("OVERSIZED_RESPONSE")
            # WeChat signs successful responses; some error responses have no signature.
            # If a signature is present it must always verify, including for errors.
            if response.is_success or response.headers.get("Wechatpay-Signature"):
                self.verify(response.headers, response.content)
            data = response.json() if response.content else {}
            if not isinstance(data, dict):
                raise PaymentError("INVALID_RESPONSE")
            if response.status_code not in (200, 201, 202, 204):
                raise PaymentError(str(data.get("code", "UNAVAILABLE")))
            return data
        except (httpx.HTTPError, ValueError) as error:
            raise PaymentError("UNAVAILABLE") from error

    def prepay(self, order, openid):
        return self.request("POST", "/v3/pay/transactions/jsapi", {
            "appid": order["appid"], "mchid": order["mchid"], "description": order["plan_name"],
            "out_trade_no": order["id"], "notify_url": configuration()["payment_callback"],
            "time_expire": datetime.fromtimestamp(order["expires_at"], timezone.utc).isoformat(),
            "amount": {"total": order["amount_fen"], "currency": "CNY"}, "payer": {"openid": openid},
        })

    def payment_parameters(self, prepay_id):
        if not isinstance(prepay_id, str) or not re.fullmatch(r"[A-Za-z0-9_=-]{1,128}", prepay_id):
            raise PaymentError("INVALID_PREPAY")
        stamp, nonce, package = str(int(time.time())), secrets.token_hex(16), "prepay_id=" + prepay_id
        return {"timeStamp": stamp, "nonceStr": nonce, "package": package, "signType": "RSA",
                "paySign": self.sign(f"{self.settings.wechat_app_id}\n{stamp}\n{nonce}\n{package}\n")}

    def query(self, order_id):
        return self.request("GET", "/v3/pay/transactions/out-trade-no/" + order_id + "?" + urlencode({"mchid": self.settings.wechat_pay_mchid}))

    def close(self, order_id):
        return self.request("POST", "/v3/pay/transactions/out-trade-no/" + order_id + "/close", {"mchid": self.settings.wechat_pay_mchid})

    def refund(self, order, refund):
        return self.request("POST", "/v3/refund/domestic/refunds", {
            "out_trade_no": order["id"], "out_refund_no": refund["id"], "reason": refund["reason"][:80],
            "notify_url": configuration()["refund_callback"],
            "amount": {"refund": order["amount_fen"], "total": order["amount_fen"], "currency": "CNY"},
        })

    def query_refund(self, refund_id):
        return self.request("GET", "/v3/refund/domestic/refunds/" + refund_id)

    def callback(self, headers, raw):
        if len(raw) > 1048576:
            raise PaymentError("OVERSIZED_RESPONSE")
        self.verify(headers, raw)
        try:
            notice = json.loads(raw)
            if not isinstance(notice, dict) or not isinstance(notice.get("resource"), dict):
                raise ValueError("Invalid resource")
            resource = notice["resource"]
            if resource["algorithm"] != "AEAD_AES_256_GCM" or not isinstance(resource.get("nonce"), str) or len(resource["nonce"].encode()) != 12:
                raise ValueError("Unknown algorithm")
            plaintext = AESGCM(self.settings.wechat_pay_api_v3_key.encode()).decrypt(
                resource["nonce"].encode(), base64.b64decode(resource["ciphertext"], validate=True), resource.get("associated_data", "").encode())
            result = json.loads(plaintext)
            if not isinstance(result, dict) or not isinstance(notice.get("event_type"), str) or not isinstance(notice["id"], str) or not 1 <= len(notice["id"]) <= 100:
                raise ValueError("Invalid callback")
            return notice["id"], notice["event_type"], result
        except (KeyError, TypeError, ValueError, AttributeError, InvalidTag) as error:
            raise PaymentError("INVALID_CALLBACK") from error

    def bill(self, bill_date, bill_type="ALL"):
        if bill_type not in ("ALL", "SUCCESS", "REFUND"):
            raise PaymentError("INVALID_BILL_TYPE")
        meta = self.request("GET", "/v3/bill/tradebill?" + urlencode({"bill_date": bill_date, "bill_type": bill_type}))
        try:
            url = urlsplit(meta["download_url"])
            if url.scheme != "https" or url.netloc != "api.mch.weixin.qq.com" or url.fragment or not (url.path == "/v3/bill/downloadurl" or url.path.startswith(("/v3/billdownload/", "/billdownload/"))):
                raise PaymentError("INVALID_BILL_URL")
            path = url.path + ("?" + url.query if url.query else "")
            content = bytearray()
            deadline = time.monotonic() + 45
            with httpx.Client(timeout=10, follow_redirects=False, transport=self.transport) as client:
                with client.stream("GET", API_ORIGIN + path, headers=self.headers("GET", path, "")) as response:
                    response.raise_for_status()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if time.monotonic() > deadline:
                            raise PaymentError("BILL_TIMEOUT")
                        if len(content) > 20 * 1024 * 1024:
                            raise PaymentError("OVERSIZED_BILL")
            algorithm = str(meta["hash_type"]).lower()
            if algorithm not in ("sha1", "sha256") or hashlib.new(algorithm, content).hexdigest() != meta["hash_value"].lower():
                raise PaymentError("INVALID_BILL_HASH")
            return content.decode("utf-8-sig")
        except (KeyError, ValueError, TypeError, httpx.HTTPError) as error:
            raise PaymentError("INVALID_BILL") from error
