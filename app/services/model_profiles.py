"""文本与图片配置共用的密钥绑定、旧配置适配与脱敏。"""

import hashlib
import json
import uuid

from fastapi import HTTPException

from app.provider_policy import require_new_key, validate_endpoint
from app.security import decrypt_secret, encrypt_secret


def revision(raw: dict) -> str:
    return str(raw.get("revision") or hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest())


def check_revision(raw: dict, expected: str | None) -> None:
    if expected != revision(raw):
        raise HTTPException(409, detail={"code": "model_config_conflict",
                                        "error": "模型配置已在其他窗口更新，本次修改未保存；请先核对最新配置"})


def public_config(raw: dict, defaults: dict, *, with_key: bool = False) -> dict:
    models = [public_profile(profile, defaults, with_key=with_key) for profile in entries(raw)]
    primary = next((profile for profile in models if profile["enabled"]), {})
    return {**defaults, "hasKey": False, **primary, "models": models, "revision": revision(raw)}


def entries(raw: dict) -> list[dict]:
    if "models" in raw:
        return list(raw["models"])
    if raw.get("baseUrl") or raw.get("model") or raw.get("apiKeyEnc") or raw.get("hasKey"):
        return [{**raw, "id": "legacy", "name": "", "enabled": True}]
    return []


def public_profile(raw: dict, defaults: dict, *, with_key: bool = False) -> dict:
    result = {key: raw.get(key, default) for key, default in defaults.items()}
    result.update(id=raw.get("id", "legacy"), name=raw.get("name", ""), enabled=raw.get("enabled", True),
                  hasKey=bool(raw.get("apiKeyEnc")))
    if with_key:
        result["api_key"] = decrypt_secret(raw.get("apiKeyEnc", ""))
    return result


def encode_profiles(profiles: list, current: dict) -> dict:
    existing = {profile["id"]: profile for profile in entries(current)}
    encoded = []
    for profile in profiles:
        raw = profile.model_dump(exclude={"apiKey"})
        raw["baseUrl"] = validate_endpoint(profile.baseUrl, resolve=False)
        previous = existing.get(profile.id, {})
        if previous.get("apiKeyEnc"):
            require_new_key(previous.get("baseUrl", ""), raw["baseUrl"], profile.apiKey)
        raw["apiKeyEnc"] = encrypt_secret(profile.apiKey) if profile.apiKey else previous.get("apiKeyEnc", "")
        if profile.enabled and not raw["apiKeyEnc"]:
            raise HTTPException(400, detail={"error": "每个启用的模型都需要配置自己的 API 密钥"})
        encoded.append(raw)
    return {"models": encoded, "revision": uuid.uuid4().hex}


def require_legacy_config(raw: dict) -> None:
    if "models" in raw:
        raise HTTPException(409, detail={"error": "配置已升级为多模型，请刷新后台后重新保存"})
