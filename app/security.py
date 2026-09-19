"""安全模块 —— 密码哈希 / 会话令牌 / 敏感字段加密

依赖策略：
- 密码哈希与令牌签名均使用标准库（hashlib/hmac），无第三方依赖
- API Key 静态加密使用 cryptography.Fernet；缺失时禁止保存新密钥
- 兼容读取旧版 base64 数据，不再写入未加密的密钥
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from pathlib import Path
from typing import Optional
from app.config import get_settings

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent
_DATA_DIR = _BASE_DIR / "data"
_SECRET_FILE = _DATA_DIR / "secret_key.txt"

# ─── 密钥加载 ───

_cached_secret: Optional[bytes] = None


def get_secret() -> bytes:
    """加载签名/加密密钥：优先配置（环境变量或 .env），否则用随机密钥文件。

    密钥文件在首次启动时自动生成，保证重启后所有会话令牌仍然有效。
    """
    global _cached_secret
    if _cached_secret is not None:
        return _cached_secret

    env = get_settings().secret_key.strip()
    if env:
        _cached_secret = env.encode("utf-8")
        return _cached_secret

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_urlsafe(48)
    created = False
    try:
        with _SECRET_FILE.open("x", encoding="utf-8") as file:
            file.write(generated)
        created = True
    except FileExistsError:
        # Another worker may have created the file but not finished its first write.
        for _ in range(20):
            generated = _SECRET_FILE.read_text(encoding="utf-8").strip()
            if generated:
                break
            time.sleep(0.05)
        if not generated:
            raise RuntimeError("服务密钥文件为空，请检查 data/secret_key.txt；不会覆盖已有文件")
    try:
        import os
        os.chmod(_SECRET_FILE, 0o600)
    except Exception:
        pass  # Windows 权限模型不同，忽略
    _cached_secret = generated.encode("utf-8")
    if created:
        logger.info("已自动生成服务密钥 data/secret_key.txt（可设置 SECRET_KEY 固定它）")
    return _cached_secret


# ─── 密码哈希（PBKDF2-SHA256） ───

_PBKDF2_ITER = 240_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITER)
    return f"pbkdf2_sha256${_PBKDF2_ITER}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


# ─── 会话令牌（JWT HS256 兼容格式） ───

_TOKEN_TTL_SECONDS = 30 * 24 * 3600  # 30 天


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def create_token(user_id: int, ttl_seconds: int = _TOKEN_TTL_SECONDS) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    now = int(time.time())
    payload = _b64url(json.dumps(
        {"sub": str(user_id), "iat": now, "exp": now + ttl_seconds},
        separators=(",", ":"),
    ).encode())
    signing_input = f"{header}.{payload}".encode("ascii")
    sig = hmac.new(get_secret(), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(sig)}"


def parse_token(token: str) -> Optional[dict]:
    """校验签名与过期时间，返回 payload（含 sub/iat/exp）；无效返回 None。"""
    try:
        header, payload, sig = token.split(".")
        signing_input = f"{header}.{payload}".encode("ascii")
        expected = hmac.new(get_secret(), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(sig)):
            return None
        data = json.loads(_b64url_decode(payload))
        # payload 是我们自己签发的，但仍按不可信输入处理：合法 JSON 也可能是数组/标量
        if not isinstance(data, dict) or data.get("exp", 0) < time.time():
            return None
        data["sub"] = int(data["sub"])
        return data
    except Exception:
        return None


# ─── 敏感字段加密（API Key 静态存储） ───

try:
    from cryptography.fernet import Fernet, InvalidToken

    def _fernet(secret: Optional[bytes] = None) -> Fernet:
        key = hashlib.sha256(b"llm-key:" + (secret if secret is not None else get_secret())).digest()
        return Fernet(base64.urlsafe_b64encode(key))

    def encrypt_secret(plain: str) -> str:
        if not plain:
            return ""
        return "enc:" + _fernet().encrypt(plain.encode("utf-8")).decode("ascii")

    def decrypt_secret(stored: str) -> str:
        if not stored:
            return ""
        if stored.startswith("b64:"):
            try:
                return base64.b64decode(stored[4:], validate=True).decode("utf-8")
            except (ValueError, UnicodeError):
                return ""
        if not stored.startswith("enc:"):
            return stored
        try:
            return _fernet().decrypt(stored[4:].encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeError, ValueError):
            # Older builds ignored SECRET_KEY in .env and encrypted with this file.
            # Only decrypt historical values with it; new sessions use the configured key.
            if get_settings().secret_key.strip() and _SECRET_FILE.exists():
                legacy = _SECRET_FILE.read_text(encoding="utf-8").strip().encode("utf-8")
                if legacy and legacy != get_secret():
                    try:
                        return _fernet(legacy).decrypt(stored[4:].encode("ascii")).decode("utf-8")
                    except (InvalidToken, UnicodeError, ValueError):
                        pass
            logger.error("解密 API Key 失败（密钥可能已更换），请重新保存密钥")
            return ""

    _HAS_FERNET = True
except ImportError:  # pragma: no cover - cryptography 未安装时的降级
    _HAS_FERNET = False
    logger.warning("未安装 cryptography：禁止保存新模型密钥，请安装 requirements.txt 中的依赖")

    def encrypt_secret(plain: str) -> str:
        if not plain:
            return ""
        raise RuntimeError("cryptography is required to store API keys")

    def decrypt_secret(stored: str) -> str:
        if not stored:
            return ""
        if stored.startswith("b64:"):
            try:
                return base64.b64decode(stored[4:], validate=True).decode("utf-8")
            except (ValueError, UnicodeError):
                return ""
        if stored.startswith("enc:"):
            return ""
        return stored


def encryption_backend() -> str:
    return "fernet" if _HAS_FERNET else "unavailable"


def security_warnings() -> list[str]:
    settings = get_settings()
    warnings = []
    if not _HAS_FERNET:
        warnings.append("缺少 cryptography，禁止保存新的模型密钥")
    if settings.secret_key and len(settings.secret_key.encode("utf-8")) < 32:
        warnings.append("SECRET_KEY 少于 32 字节，建议使用足够长的随机密钥")
    if settings.host not in ("127.0.0.1", "localhost", "::1") and not settings.force_https:
        warnings.append("非回环地址未启用 FORCE_HTTPS，生产部署请配置 HTTPS 和 Secure Cookie")
    return warnings
