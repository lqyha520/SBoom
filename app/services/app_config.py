"""全局应用配置 —— 管理员在后台统一设置的系统级配置（当前：LLM 服务）

模型配置收归后台管理：所有用户共用管理员配置的全局 LLM 服务；
密钥加密存储在 app_config 表，接口绝不回传明文。

普通读取保留 TTL 内存缓存（默认 60s）；新生成任务通过 fresh=True 直接读库，
随后在任务内复用快照，所有 worker 的新任务立即采用最新配置。
"""

import json
import logging
import threading
import time
from copy import deepcopy

from app.config import get_settings
from app.db import db
from app.provider_policy import require_new_key, validate_endpoint
from app.security import decrypt_secret, encrypt_secret
from app.services.model_profiles import (
    check_revision,
    encode_profiles,
    public_config,
    public_profile,
    require_legacy_config,
    revision,
)

logger = logging.getLogger(__name__)

_LLM_KEY = "llm"
_CACHE_TTL_SECONDS = 60.0

_EMPTY = {"baseUrl": "", "model": "", "timeout": 120, "maxTokens": get_settings().llm_max_tokens,
          "samplingMode": "configured", "tokenParameter": "max_tokens", "hasKey": False, "api_key": ""}

# ─── 缓存（进程内；管理员保存时失效，重启即空） ───
#
# 读路径 stale-while-revalidate：
# - 缓存新鲜：只在 _cache_lock 下拷一份就返回，不碰 DB；
# - 缓存过期但有旧值：抢到 _refresh_lock 的那个线程去查库，其他线程直接用旧值继续服务；
# - 完全没有值（冷启动 / 刚被失效）：所有线程都在 _refresh_lock 上排队，等首个加载完成后复用结果，
#   保证 DB 只查一次、每个调用方拿到的都是完整快照。
# _cache_gen 是失效代数：加载期间如果有人调用 _invalidate_cache（管理员保存），
# 加载结果作废不发布，避免用刚查到的旧值盖掉失效。
# 加载失败时异常原样抛给发起刷新的调用方，缓存内容与时间戳都不动。

_cache_raw: dict | None = None
_cache_ts: float = 0.0
_cache_gen: int = 0
_cache_lock = threading.RLock()   # 保护上面三个字段（只在极短的读写窗口内持有）
_refresh_lock = threading.Lock()  # 同一时刻只允许一个线程查库


def _invalidate_cache() -> None:
    global _cache_raw, _cache_ts, _cache_gen
    with _cache_lock:
        _cache_raw = None
        _cache_ts = 0.0
        _cache_gen += 1


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


def _snapshot() -> tuple[dict | None, bool]:
    """返回 (缓存值拷贝或 None, 是否新鲜)。"""
    with _cache_lock:
        if _cache_raw is None:
            return None, False
        return deepcopy(_cache_raw), time.monotonic() - _cache_ts < _CACHE_TTL_SECONDS


def _refresh() -> dict:
    """查库并发布到缓存；加载期间发生过失效则只返回、不发布。调用方须持有 _refresh_lock。"""
    global _cache_raw, _cache_ts
    with _cache_lock:
        generation = _cache_gen
    loaded = _load_llm_raw()
    with _cache_lock:
        if _cache_gen == generation:
            _cache_raw = deepcopy(loaded)
            _cache_ts = time.monotonic()
    return deepcopy(loaded)


# ─── 全局 LLM 配置 ───

def get_llm(with_key: bool = False, *, fresh: bool = False) -> dict:
    """读取全局 LLM 配置（TTL 缓存，过期后 stale-while-revalidate）。

    with_key=True 时附带解密后的 api_key（仅供后端调用 LLM 使用，绝不下发前端）。
    """
    raw, cached_fresh = (_load_llm_raw(), True) if fresh else _snapshot()
    if not cached_fresh:
        if raw is None:
            # 没有任何可用值：排队等首个加载，醒来后先看别人是否已经装好
            with _refresh_lock:
                raw, fresh = _snapshot()
                if raw is None or not fresh:
                    raw = _refresh()
        elif _refresh_lock.acquire(blocking=False):
            # 有过期旧值：只让一个线程刷新，其余线程拿旧值直接走
            try:
                raw = _refresh()
            finally:
                _refresh_lock.release()
    if not raw:
        return {**_EMPTY, "revision": revision({})}
    if "models" in raw:
        defaults = {key: value for key, value in _EMPTY.items() if key not in ("hasKey", "api_key")}
        models = [public_profile(profile, defaults, with_key=with_key) for profile in raw["models"]]
        primary = next((profile for profile in models if profile["enabled"]), {})
        return {**_EMPTY, **primary, "models": models, "revision": revision(raw)}
    key_enc = raw.get("apiKeyEnc", "")
    return {
        "baseUrl": raw.get("baseUrl", ""),
        "model": raw.get("model", ""),
        "timeout": raw.get("timeout", 120),
        "maxTokens": raw.get("maxTokens", get_settings().llm_max_tokens),
        "hasKey": bool(key_enc),
        "api_key": decrypt_secret(key_enc) if with_key else "",
        "samplingMode": raw.get("samplingMode", "configured"),
        "tokenParameter": raw.get("tokenParameter", "max_tokens"),
        "revision": revision(raw),
    }


def _save_llm_raw(conn, base_url: str, model: str, key_enc: str, timeout: int, max_tokens: int | None = None,
                  sampling_mode: str = "configured", token_parameter: str = "max_tokens") -> None:
    payload = json.dumps(
        {"baseUrl": base_url, "model": model, "apiKeyEnc": key_enc, "timeout": timeout, "maxTokens": max_tokens or get_settings().llm_max_tokens,
         "samplingMode": sampling_mode, "tokenParameter": token_parameter},
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


def save_llm(base_url: str, model: str, api_key: str, timeout: int, max_tokens: int | None = None,
             sampling_mode: str = "configured", token_parameter: str = "max_tokens") -> None:
    """保存全局 LLM 配置。api_key 为空字符串表示保留已存密钥不变。

    写路径不再持有缓存锁（否则一次 DB 写会卡住所有读请求）；
    事务提交后再失效缓存，加载中的旧值由 _cache_gen 机制作废。
    """
    base_url = validate_endpoint(base_url, resolve=False)
    with db(serialized="accounts") as conn:
        row = conn.execute("SELECT value FROM app_config WHERE key = ?", (_LLM_KEY,)).fetchone()
        try:
            current = json.loads(row["value"]) if row else {}
        except (json.JSONDecodeError, TypeError):
            current = {}
        if not isinstance(current, dict):
            current = {}
        require_legacy_config(current)
        if current.get("apiKeyEnc") or get_settings().llm_api_key:
            require_new_key(current.get("baseUrl") or get_settings().llm_base_url, base_url, api_key)
        key_enc = encrypt_secret(api_key) if api_key else current.get("apiKeyEnc", "")
        _save_llm_raw(conn, base_url, model, key_enc, timeout, max_tokens, sampling_mode, token_parameter)
    _invalidate_cache()


def _admin_snapshot(raw: dict, *, with_key: bool = False) -> dict:
    defaults = {key: value for key, value in _EMPTY.items() if key not in ("hasKey", "api_key")}
    result = public_config(raw, defaults, with_key=with_key)
    if with_key:
        result["managed"] = "models" in raw
    return result


def get_admin_config(with_key: bool = False) -> dict:
    # 编辑基线必须直接读库，不能复用生成请求允许的短期旧缓存。
    return _admin_snapshot(_load_llm_raw(), with_key=with_key)


def save_llm_models(profiles: list, *, expected_revision: str | None = None, require_revision: bool = False) -> dict:
    with db(serialized="accounts") as conn:
        row = conn.execute("SELECT value FROM app_config WHERE key = ?", (_LLM_KEY,)).fetchone()
        current = json.loads(row["value"]) if row else {}
        if require_revision or expected_revision is not None:
            check_revision(current, expected_revision)
        raw = encode_profiles(profiles, current)
        conn.execute(
            "INSERT INTO app_config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET "
            "value = excluded.value, updated_at = datetime('now', 'localtime')",
            (_LLM_KEY, json.dumps(raw, ensure_ascii=False)),
        )
    _invalidate_cache()
    return _admin_snapshot(raw)


def clear_llm() -> None:
    """删除配置行，恢复旧版环境兜底；仅用于迁移与测试还原。"""
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
