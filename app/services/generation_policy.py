"""后台模型配置是任务时限的唯一来源；每个请求固定一份最新配置快照。"""

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal, cast

from app.config import get_settings
from app.services import app_config, image_config
from app.services.model_profiles import entries

QUALITY_REVIEW_TIMEOUT = 120.0
TRANSPORT_GRACE_SECONDS = 30


@dataclass
class GenerationPolicy:
    kind: Literal["text", "image"]
    config: dict
    timeout_seconds: float

    def public(self) -> dict:
        return {"revision": self.config["revision"],
                "timeout_ms": int((self.timeout_seconds + TRANSPORT_GRACE_SECONDS) * 1000),
                "task_timeout_seconds": self.timeout_seconds}


current_policy: ContextVar[GenerationPolicy | None] = ContextVar("generation_policy", default=None)


def latest_config(kind: str) -> dict:
    if kind == "image":
        return cast(dict, image_config.get_config(with_key=True))
    # 每个新任务直接读数据库；多 worker 无需等待各自的 TTL 缓存到期。
    return app_config.get_llm(with_key=True, fresh=True)


def runtime_config(kind: str) -> dict:
    policy = current_policy.get()
    return policy.config if policy is not None and policy.kind == kind else latest_config(kind)


def load_policy(kind: str) -> GenerationPolicy:
    category: Literal["text", "image"] = "image" if kind == "image" else "text"
    config = latest_config(category)
    candidates = [profile for profile in entries(config) if profile.get("enabled", True)]
    chain = sum(float(profile["timeout"]) for profile in candidates) or float(config["timeout"])
    if category == "text" and "models" not in config:
        chain = float(config.get("timeout") or 120)
    # 一次出题 + 受现有上限约束的补题 + 独立复核，另留本地整理时间。
    seconds = chain if kind in ("image", "validate", "stream") else (
        chain * (1 + get_settings().generation_repair_limit) + min(chain, QUALITY_REVIEW_TIMEOUT))
    seconds = min(seconds + TRANSPORT_GRACE_SECONDS, get_settings().generation_lease_seconds - 5)
    return GenerationPolicy(category, config, seconds)
