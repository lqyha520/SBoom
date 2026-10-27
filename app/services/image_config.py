"""Independent image provider credentials, encrypted using the existing secret store."""

import json

from app.db import db
from app.models.image_generation import ImageModelConfig
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

KEY = "image_generation"
DEFAULTS = {"baseUrl": "", "model": "", "timeout": 300,
            "size": "1024x1536", "responseFormat": "auto", "requestMode": "auto"}


def _raw(conn):
    row = conn.execute("SELECT value FROM app_config WHERE key = ?", (KEY,)).fetchone()
    if not row:
        return {}
    return json.loads(row["value"])


def get_config(with_key=False):
    with db() as conn:
        raw = _raw(conn)
    if "models" in raw:
        models = [public_profile(profile, DEFAULTS, with_key=with_key) for profile in raw["models"]]
        primary = next((profile for profile in models if profile["enabled"]), {})
        return {**DEFAULTS, "hasKey": False, **({"api_key": ""} if with_key else {}), **primary,
                "models": models, "revision": revision(raw)}
    result = {key: raw.get(key, default) for key, default in DEFAULTS.items()}
    result["hasKey"] = bool(raw.get("apiKeyEnc"))
    result["revision"] = revision(raw)
    if with_key:
        result["api_key"] = decrypt_secret(raw["apiKeyEnc"]) if result["hasKey"] else ""
    return result


def save_config(value: ImageModelConfig):
    endpoint = validate_endpoint(value.baseUrl, resolve=False)
    with db(serialized="accounts") as conn:
        current = _raw(conn)
        require_legacy_config(current)
        if current.get("apiKeyEnc"):
            require_new_key(current.get("baseUrl", ""), endpoint, value.apiKey)
        raw = value.model_dump(exclude={"apiKey"})
        raw["baseUrl"] = endpoint
        raw["apiKeyEnc"] = encrypt_secret(value.apiKey) if value.apiKey else current.get("apiKeyEnc", "")
        conn.execute(
            "INSERT INTO app_config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET "
            "value = excluded.value, updated_at = datetime('now', 'localtime')",
            (KEY, json.dumps(raw, ensure_ascii=False)),
        )


def get_admin_config():
    with db() as conn:
        return public_config(_raw(conn), DEFAULTS)


def save_models(profiles: list, *, expected_revision: str | None = None, require_revision: bool = False):
    with db(serialized="accounts") as conn:
        current = _raw(conn)
        if require_revision or expected_revision is not None:
            check_revision(current, expected_revision)
        raw = encode_profiles(profiles, current)
        conn.execute(
            "INSERT INTO app_config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET "
            "value = excluded.value, updated_at = datetime('now', 'localtime')",
            (KEY, json.dumps(raw, ensure_ascii=False)),
        )
    return public_config(raw, DEFAULTS)


def clear_config(*, expected_revision: str | None = None, check_current: bool = False):
    with db(serialized="accounts") as conn:
        current = _raw(conn)
        if expected_revision is not None or (check_current and "models" in current):
            check_revision(current, expected_revision)
        conn.execute("DELETE FROM app_config WHERE key = ?", (KEY,))
    return public_config({}, DEFAULTS)
