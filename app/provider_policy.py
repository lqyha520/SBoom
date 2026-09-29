"""模型凭据绑定到服务来源；配置写入和连通性探测共用校验。"""

import ipaddress
import socket
from urllib.parse import urlsplit

from fastapi import HTTPException

from app.config import get_settings


def origin(url: str) -> tuple[str, str, int]:
    try:
        parts = urlsplit(url.strip())
        return parts.scheme.lower(), (parts.hostname or "").lower(), parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise HTTPException(422, detail={"error": "模型接口地址无效"}) from exc


def validate_endpoint(url: str, *, resolve: bool = True) -> str:
    url = url.strip().rstrip("/")
    parts = urlsplit(url)
    scheme, host, port = origin(url)
    private = get_settings().provider_allow_private
    if (not host or scheme not in (("http", "https") if private else ("https",))
            or parts.username or parts.password or parts.query or parts.fragment):
        raise HTTPException(422, detail={"error": "接口须为 HTTPS 地址，不能包含账号密码、查询参数或片段"})
    if resolve and not private:
        try:
            addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(str(entry[4][0])).is_global for entry in addresses):
                raise ValueError("private address")
        except (OSError, ValueError) as exc:
            raise HTTPException(422, detail={"error": "模型接口必须解析到公网地址"}) from exc
    return url


def require_new_key(previous: str, requested: str, supplied: str) -> None:
    if origin(previous) != origin(requested) and not supplied.strip():
        raise HTTPException(422, detail={"code": "provider_key_required", "error": "更换模型服务的协议、主机或端口后，请重新填写密钥"})
