"""模型凭据绑定到服务来源；配置写入和连通性探测共用校验。"""

import ipaddress
import socket
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from app.blocking import run_sync
from app.config import get_settings


def origin(url: str) -> tuple[str, str, int]:
    try:
        parts = urlsplit(url.strip())
        return parts.scheme.lower(), (parts.hostname or "").lower(), parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise HTTPException(422, detail={"error": "模型接口地址无效"}) from exc


def validate_endpoint(url: str, *, resolve: bool = True) -> str:
    url = url.strip().rstrip("/")
    try:
        parts = urlsplit(url)
        if (parts.port is not None and not 1 <= parts.port <= 65535) or any(char.isspace() or ord(char) < 32 for char in url):
            raise ValueError("invalid URL")
    except ValueError as exc:
        raise HTTPException(422, detail={"error": "模型接口地址无效"}) from exc
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


async def pin_provider_request(request: httpx.Request) -> None:
    """Resolve once per request; retain the original Host and TLS certificate name."""
    # 配置地址仍禁止查询参数；实际请求允许任务查询参数，并继续校验来源及固定公网 IP。
    validate_endpoint(str(request.url.copy_with(query=None)), resolve=False)
    if get_settings().provider_allow_private:
        return
    host = request.url.host
    try:
        addresses = await run_sync(socket.getaddrinfo, host, request.url.port or 443, type=socket.SOCK_STREAM)
        ips = [str(entry[4][0]) for entry in addresses]
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise ValueError("private address")
    except OSError as exc:
        raise HTTPException(502, detail={"code": "provider_dns_error", "error": "模型服务域名暂时无法解析，未发送请求"}) from exc
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "provider_address_rejected", "error": "模型接口当前未解析到公网地址，未发送请求"}) from exc
    request.headers["Host"] = request.url.netloc.decode("ascii")
    request.extensions["sni_hostname"] = host
    request.url = request.url.copy_with(host=ips[0])
