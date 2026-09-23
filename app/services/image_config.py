"""Independent image provider credentials, encrypted using the existing secret store."""

import json

from app.db import db
from app.models.image_generation import ImageModelConfig
from app.security import decrypt_secret, encrypt_secret

KEY = "image_generation"
DEFAULTS = {"baseUrl": "", "model": "", "timeout": 300,
            "size": "1024x1536", "responseFormat": "auto"}


def _raw(conn):
    row = conn.execute("SELECT value FROM app_config WHERE key = ?", (KEY,)).fetchone()
    if not row:
        return {}
    return json.loads(row["value"])


def get_config(with_key=False):
    with db() as conn:
        raw = _raw(conn)
    result = {key: raw.get(key, default) for key, default in DEFAULTS.items()}
    result["hasKey"] = bool(raw.get("apiKeyEnc"))
    if with_key:
        result["api_key"] = decrypt_secret(raw["apiKeyEnc"]) if result["hasKey"] else ""
    return result


def save_config(value: ImageModelConfig):
    with db(serialized="accounts") as conn:
        current = _raw(conn)
        raw = value.model_dump(exclude={"apiKey"})
        raw["apiKeyEnc"] = encrypt_secret(value.apiKey) if value.apiKey else current.get("apiKeyEnc", "")
        conn.execute(
            "INSERT INTO app_config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET "
            "value = excluded.value, updated_at = datetime('now', 'localtime')",
            (KEY, json.dumps(raw, ensure_ascii=False)),
        )


def clear_config():
    with db(serialized="accounts") as conn:
        conn.execute("DELETE FROM app_config WHERE key = ?", (KEY,))
