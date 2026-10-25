"""WeChat Pay API v3: fixed hosts, RSA signatures, authenticated callback decryption."""

import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
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

# ─── 进程内共享的 httpx.Client ───
# 每次调用都 new 一个 Client 意味着每次都重新握 TLS；微信支付接口固定同一台主机，
# 复用一个 Client（线程安全）即可复用连接。超时按请求单独传，不同接口耐心不同。
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


def _file_stat(path: str) -> tuple[int, int] | None:
    """(mtime_ns, size)；文件不存在/不可读返回 None。一次 stat 同时拿到两项，别 stat 两遍。"""
    try:
        st = os.stat(path)
    except (OSError, ValueError):
        return None
    return st.st_mtime_ns, st.st_size


class PaymentError(Exception):
    def __init__(self, code="UNAVAILABLE", message=None):
        self.code = code if re.fullmatch(r"[A-Z0-9_]{1,80}", code) else "UNAVAILABLE"
        super().__init__(message or "微信支付服务暂不可用，请稍后重试")


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
        paths = [str(settings.wechat_pay_private_key_path), str(settings.wechat_pay_platform_key_path)]
        stats = [_file_stat(path) for path in paths]
        if stats[0] is None or stats[1] is None:
            raise OSError("key file missing")
        private, public, certificate = _key_material(paths[0], stats[0], paths[1], stats[1], settings.wechat_pay_platform_serial)
        if certificate and not certificate.not_valid_before_utc <= datetime.now(UTC) <= certificate.not_valid_after_utc:
            raise ValueError("Expired platform certificate")
        return private, public
    except (OSError, ValueError, TypeError, UnsupportedAlgorithm) as error:
        raise PaymentError("INVALID_KEYS") from error


# configuration() 会被订单/套餐/维护任务反复调用，每次都要 stat 密钥文件 + 正则 + 解析证书。
# 缓存 5s；缓存键带上全部相关配置值和密钥文件的 (mtime, size)，
# 所以改配置（含测试里 patch settings）或换密钥文件都会立即失效，不用等 TTL。
_CONFIG_TTL_SECONDS = 5.0
_config_lock = threading.Lock()
_config_cache: tuple[float, tuple, dict] | None = None  # (过期时刻, 缓存键, 结果)


def _config_key(settings) -> tuple:
    return (
        settings.wechat_pay_enabled, settings.wechat_app_id, settings.wechat_pay_mchid,
        settings.wechat_pay_serial_no, settings.wechat_pay_private_key_path, settings.wechat_pay_platform_serial,
        settings.wechat_pay_platform_key_path, settings.wechat_pay_api_v3_key, settings.wechat_pay_notify_origin,
        settings.wechat_pay_ios_enabled,
        _file_stat(str(settings.wechat_pay_private_key_path)) if settings.wechat_pay_private_key_path else None,
        _file_stat(str(settings.wechat_pay_platform_key_path)) if settings.wechat_pay_platform_key_path else None,
    )


def configuration():
    global _config_cache
    settings = get_settings()
    key = _config_key(settings)
    now = time.monotonic()
    cached = _config_cache
    if cached is not None and cached[0] > now and cached[1] == key:
        return {**cached[2], "missing": list(cached[2]["missing"])}
    value = _compute_configuration(settings)
    with _config_lock:
        # 同时算新鲜值的线程各算各的，谁后写谁生效——结果由同一 key 决定，无所谓先后
        _config_cache = (now + _CONFIG_TTL_SECONDS, key, value)
    return {**value, "missing": list(value["missing"])}


def _compute_configuration(settings):
    def key_exists(value):
        try:
            stat = _file_stat(str(value)) if value else None
            return bool(stat is not None and Path(value).is_file() and stat[1] <= 32768)
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

    @contextmanager
    def _client(self, timeout: float):
        """默认复用进程内共享 Client；显式传 transport（测试用 MockTransport）时才单独建一个。"""
        if self.transport is not None:
            with httpx.Client(timeout=timeout, follow_redirects=False, transport=self.transport) as client:
                yield client
        else:
            yield _http_client()

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
            with self._client(12) as client:
                response = client.request(method, API_ORIGIN + path, content=body.encode(), headers=self.headers(method, path, body), timeout=12)
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
            "time_expire": datetime.fromtimestamp(order["expires_at"], UTC).isoformat(),
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
            with self._client(10) as client:
                with client.stream("GET", API_ORIGIN + path, headers=self.headers("GET", path, ""), timeout=10) as response:
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
