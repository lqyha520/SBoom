"""全局应用配置 —— 管理员在后台统一设置的系统级配置（当前：LLM 服务）

模型配置收归后台管理：所有用户共用管理员配置的全局 LLM 服务；
密钥加密存储在 app_config 表，接口绝不回传明文。

读取走 TTL 内存缓存（默认 60s），避免每次生成请求都开新 DB 连接查询；
管理员保存配置 / 启动迁移时本进程主动失效；其他 worker 最迟 60s 生效。
"""

import json
import logging
import threading
import time

from app.db import db
from app.security import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

_LLM_KEY = "llm"
_CACHE_TTL_SECONDS = 60.0

_EMPTY = {"baseUrl": "", "model": "", "timeout": 120, "hasKey": False, "api_key": ""}

# ─── 缓存（进程内；管理员保存时失效，重启即空） ───

_cache_raw: dict | None = None
_cache_ts: float = 0.0
_cache_lock = threading.RLock()


def _invalidate_cache() -> None:
    global _cache_raw, _cache_ts
    with _cache_lock:
        _cache_raw = None
        _cache_ts = 0.0


def _load_llm_raw() -> dict:
    with db() as conn:
        row = conn.execute(
            "SELECT value FROM app_config WHERE key = ?", (_LLM_KEY,)
        ).fetchone()
    if not row:
        return {}
    try:
        value = json.loads(row["value"])
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


# ─── 全局 LLM 配置 ───

def get_llm(with_key: bool = False) -> dict:
    """读取全局 LLM 配置（TTL 缓存）。

    with_key=True 时附带解密后的 api_key（仅供后端调用 LLM 使用，绝不下发前端）。
    """
    global _cache_raw, _cache_ts
    with _cache_lock:
        if _cache_raw is None or time.monotonic() - _cache_ts >= _CACHE_TTL_SECONDS:
            _cache_raw = _load_llm_raw()
            _cache_ts = time.monotonic()
        raw = dict(_cache_raw)
    if not raw:
        return dict(_EMPTY)
    key_enc = raw.get("apiKeyEnc", "")
    return {
        "baseUrl": raw.get("baseUrl", ""),
        "model": raw.get("model", ""),
        "timeout": raw.get("timeout", 120),
        "hasKey": bool(key_enc),
        "api_key": decrypt_secret(key_enc) if with_key else "",
    }


def _save_llm_raw(conn, base_url: str, model: str, key_enc: str, timeout: int) -> None:
    payload = json.dumps(
        {"baseUrl": base_url, "model": model, "apiKeyEnc": key_enc, "timeout": timeout},
        ensure_ascii=False,
    )
    conn.execute(
        """
        INSERT INTO app_config (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = datetime('now', 'localtime')
        """,
        (_LLM_KEY, payload),
    )


def save_llm(base_url: str, model: str, api_key: str, timeout: int) -> None:
    """保存全局 LLM 配置。api_key 为空字符串表示保留已存密钥不变。"""
    with _cache_lock:
        with db(serialized="accounts") as conn:
            row = conn.execute("SELECT value FROM app_config WHERE key = ?", (_LLM_KEY,)).fetchone()
            try:
                current = json.loads(row["value"]) if row else {}
            except (json.JSONDecodeError, TypeError):
                current = {}
            if not isinstance(current, dict):
                current = {}
            key_enc = encrypt_secret(api_key) if api_key else current.get("apiKeyEnc", "")
            _save_llm_raw(conn, base_url, model, key_enc, timeout)
        _invalidate_cache()


def clear_llm() -> None:
    """清除全局 LLM 配置（整行删除，含已存密钥）。用于后台重置 / 测试还原。"""
    with _cache_lock:
        with db(serialized="accounts") as conn:
            conn.execute("DELETE FROM app_config WHERE key = ?", (_LLM_KEY,))
        _invalidate_cache()
    logger.info("全局模型配置已清除")


# ─── 存量迁移 ───

def seed_llm_from_user_configs() -> bool:
    """一次性迁移：全局配置为空时，从最近更新的用户自配 LLM 继承。

    适配「模型配置收归后台」的升级——老部署里用户各自保存的密钥
    自动变成全局配置，升级后无需重新填密钥。返回是否执行了迁移。
    """
    with _cache_lock:
        with db(serialized="accounts") as conn:
            if conn.execute("SELECT 1 FROM app_config WHERE key = ?", (_LLM_KEY,)).fetchone():
                return False
            row = conn.execute(
                "SELECT base_url, model, api_key_enc, timeout FROM user_llm_configs "
                "WHERE api_key_enc != '' OR base_url != '' ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            if not row:
                return False
            _save_llm_raw(conn, row["base_url"], row["model"], row["api_key_enc"], row["timeout"])
        _invalidate_cache()
    logger.info("已将最近一次用户自配的 LLM 配置迁移为全局配置（模型配置现已收归后台管理）")
    return True
