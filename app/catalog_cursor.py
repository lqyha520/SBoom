"""目录分页游标绑定查询范围；签名避免客户端伪造极端排序值。"""

import base64
import hashlib
import hmac
import json

from fastapi import HTTPException

from app.security import get_secret


def encode(values: list, scope: str) -> str:
    raw = json.dumps({"v": values, "s": scope}, separators=(",", ":")).encode()
    signature = hmac.new(get_secret(), b"catalog-cursor:" + raw, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature + raw).decode().rstrip("=")


def decode(value: str, scope: str, size: int) -> list:
    try:
        if len(value) > 2048:
            raise ValueError
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        signature, payload = raw[:32], raw[32:]
        expected = hmac.new(get_secret(), b"catalog-cursor:" + payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        data = json.loads(payload)
        values = data["v"]
        if data["s"] != scope or not isinstance(values, list) or len(values) != size:
            raise ValueError
        if not all(isinstance(item, (int, str)) and not isinstance(item, bool) for item in values):
            raise ValueError
        return values
    except (ValueError, KeyError, TypeError):
        raise HTTPException(422, detail={"error": "分页游标已失效，请从第一页重新加载", "code": "invalid_cursor"}) from None
