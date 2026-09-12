"""安全模块 —— 密码哈希 / 会话令牌 / 敏感字段加密

依赖策略：
- 密码哈希与令牌签名均使用标准库（hashlib/hmac），无第三方依赖
- API Key 静态加密优先使用 cryptography.Fernet；未安装时降级为
  base64 存储（仅混淆，不加密）并记录警告日志
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

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent
_DATA_DIR = _BASE_DIR / "data"
_SECRET_FILE = _DATA_DIR / "secret_key.txt"

# ─── 密钥加载 ───

_cached_secret: Optional[bytes] = None


def get_secret() -> bytes:
    """加载签名/加密密钥：优先 SECRET_KEY 环境变量，否则用持久化的随机密钥文件。

    密钥文件在首次启动时自动生成，保证重启后所有会话令牌仍然有效。
    """
    global _cached_secret
    if _cached_secret is not None:
        return _cached_secret

    import os
    env = os.environ.get("SECRET_KEY", "").strip()
    if env:
        _cached_secret = env.encode("utf-8")
        return _cached_secret

    if _SECRET_FILE.exists():
        _cached_secret = _SECRET_FILE.read_text(encoding="utf-8").strip().encode("utf-8")
        return _cached_secret

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_urlsafe(48)
    _SECRET_FILE.write_text(generated, encoding="utf-8")
    try:
        import os
        os.chmod(_SECRET_FILE, 0o600)
    except Exception:
        pass  # Windows 权限模型不同，忽略
    _cached_secret = generated.encode("utf-8")
    logger.info("已自动生成服务密钥 data/secret_key.txt（可设置 SECRET_KEY 环境变量固定它）")
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
        if data.get("exp", 0) < time.time():
            return None
        data["sub"] = int(data["sub"])
        return data
    except Exception:
        return None


# ─── 敏感字段加密（API Key 静态存储） ───

try:
    from cryptography.fernet import Fernet, InvalidToken

    def _fernet() -> Fernet:
        key = hashlib.sha256(b"llm-key:" + get_secret()).digest()
        return Fernet(base64.urlsafe_b64encode(key))

    def encrypt_secret(plain: str) -> str:
        if not plain:
            return ""
        return "enc:" + _fernet().encrypt(plain.encode("utf-8")).decode("ascii")

    def decrypt_secret(stored: str) -> str:
        if not stored:
            return ""
        if not stored.startswith("enc:"):
            return stored  # 兼容历史明文/base64 值
        try:
            return _fernet().decrypt(stored[4:].encode("ascii")).decode("utf-8")
        except InvalidToken:
            logger.error("解密 API Key 失败（密钥可能已更换），请重新保存密钥")
            return ""

    _HAS_FERNET = True
except ImportError:  # pragma: no cover - cryptography 未安装时的降级
    _HAS_FERNET = False
    logger.warning(
        "未安装 cryptography 库：API Key 将仅做 base64 混淆存储（非加密）。"
        "建议 pip install cryptography"
    )

    def encrypt_secret(plain: str) -> str:
        if not plain:
            return ""
        return "b64:" + base64.b64encode(plain.encode("utf-8")).decode("ascii")

    def decrypt_secret(stored: str) -> str:
        if not stored:
            return ""
        if stored.startswith("b64:"):
            return base64.b64decode(stored[4:]).decode("utf-8")
        return stored


def encryption_backend() -> str:
    return "fernet" if _HAS_FERNET else "base64(降级)"
