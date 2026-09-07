"""全局应用配置 —— 管理员在后台统一设置的系统级配置（当前：LLM 服务）

模型配置收归后台管理：所有用户共用管理员配置的全局 LLM 服务；
密钥加密存储在 app_config 表，接口绝不回传明文。
"""

import json
import logging

from app.db import db
from app.security import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

_LLM_KEY = "llm"

_EMPTY = {"baseUrl": "", "model": "", "timeout": 60, "hasKey": False, "api_key": ""}


# ─── 全局 LLM 配置 ───

def get_llm(with_key: bool = False) -> dict:
    """读取全局 LLM 配置。

    with_key=True 时附带解密后的 api_key（仅供后端调用 LLM 使用，绝不下发前端）。
    """
    with db() as conn:
        row = conn.execute(
            "SELECT value FROM app_config WHERE key = ?", (_LLM_KEY,)
        ).fetchone()
    if not row:
        return dict(_EMPTY)
    try:
        d = json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        return dict(_EMPTY)
    key_enc = d.get("apiKeyEnc", "")
    return {
        "baseUrl": d.get("baseUrl", ""),
        "model": d.get("model", ""),
        "timeout": d.get("timeout", 60),
        "hasKey": bool(key_enc),
        "api_key": decrypt_secret(key_enc) if with_key else "",
    }


def _save_llm_raw(base_url: str, model: str, key_enc: str, timeout: int) -> None:
    payload = json.dumps(
        {"baseUrl": base_url, "model": model, "apiKeyEnc": key_enc, "timeout": timeout},
        ensure_ascii=False,
    )
    with db() as conn:
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
    cur = get_llm(with_key=True)
    if api_key:
        key_enc = encrypt_secret(api_key)
    elif cur["api_key"]:
        key_enc = encrypt_secret(cur["api_key"])
    else:
        key_enc = ""
    _save_llm_raw(base_url, model, key_enc, timeout)


# ─── 存量迁移 ───

def seed_llm_from_user_configs() -> bool:
    """一次性迁移：全局配置为空时，从最近更新的用户自配 LLM 继承。

    适配「模型配置收归后台」的升级——老部署里用户各自保存的密钥
    自动变成全局配置，升级后无需重新填密钥。返回是否执行了迁移。
    """
    cur = get_llm()
    if cur["baseUrl"] or cur["hasKey"]:
        return False
    with db() as conn:
        row = conn.execute(
            """
            SELECT base_url, model, api_key_enc, timeout FROM user_llm_configs
            WHERE api_key_enc != '' OR base_url != ''
            ORDER BY updated_at DESC LIMIT 1
            """
        ).fetchone()
    if not row:
        return False
    _save_llm_raw(row["base_url"], row["model"], row["api_key_enc"], row["timeout"])
    logger.info("已将最近一次用户自配的 LLM 配置迁移为全局配置（模型配置现已收归后台管理）")
    return True
