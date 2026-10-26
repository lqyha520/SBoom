"""模型凭据绑定到服务来源；配置写入和连通性探测共用校验。"""

import ipaddress
import socket
import time
from collections import OrderedDict
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from app.blocking import run_sync
from app.config import get_settings

# 单条地址的可达性探测上限；只在 DNS 给出多个公网地址时启用。
CONNECT_PROBE_SECONDS = 2.0

# 同一家 CDN 的 anycast 边缘在境内可达性会分化：某个主机的 DNS 可能全部落在被静默丢包的网段，
# 而同一时刻另一台边缘是通的。这里记住最近真正建连成功的边缘地址，供这种主机兜底。
EDGE_CACHE_MAX = 8
EDGE_CACHE_SECONDS = 900.0
_edges: OrderedDict[tuple[str, int], float] = OrderedDict()


def _remember_edge(ip: str, port: int) -> None:
    key = (ip, port)
    _edges[key] = time.monotonic()
    _edges.move_to_end(key)
    while len(_edges) > EDGE_CACHE_MAX:
        _edges.popitem(last=False)


def _fallback_edges(port: int, exclude: set[str]) -> list[str]:
    """种子地址优先，其余按最近成功时间倒序；私网与非法地址直接丢弃。"""
    now = time.monotonic()
    learned = [key[0] for key, seen_at in sorted(_edges.items(), key=lambda item: item[1], reverse=True)
               if key[1] == port and now - seen_at <= EDGE_CACHE_SECONDS]
    seeds = [item.strip() for item in get_settings().provider_edge_fallback_ips.split(",") if item.strip()]
    picked: list[str] = []
    for ip in seeds + learned:
        if ip in exclude or ip in picked:
            continue
        try:
            if not ipaddress.ip_address(ip).is_global:
                continue
        except ValueError:
            continue
        picked.append(ip)
    return picked

# 上游多挂在 Cloudflare/Nginx 之后，默认 python-httpx 指纹容易被按客户端策略区别对待；
# 生图提交、任务轮询、成品下载与文本模型都统一带上浏览器风格请求头。
PROVIDER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"),
    "Accept": "application/json, image/*, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Site": "cross-site",
}


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


def reachable_ip(ips: list[str], port: int) -> str:
    """在已校验为公网的地址里挑一个真能建连的，全部不通时退回第一个以保持原有报错。"""
    # 境内访问部分 Cloudflare 段会静默丢包，而 DNS 常把它排在第一个；只钉 ips[0] 会连带可用地址一起失败。
    if len(ips) == 1:
        return ips[0]
    for ip in ips:
        try:
            with socket.create_connection((ip, port), timeout=CONNECT_PROBE_SECONDS):
                _remember_edge(ip, port)
                return ip
        except OSError:
            continue
    # 解析结果整段不通（例如成品托管在 R2，而 r2.dev 只解析到黑洞网段）：
    # 换已知可达的同 CDN 边缘再试，Host/SNI 与证书校验都保持原主机，所以内容不会被替换。
    for ip in _fallback_edges(port, set(ips)):
        try:
            with socket.create_connection((ip, port), timeout=CONNECT_PROBE_SECONDS):
                _remember_edge(ip, port)
                return ip
        except OSError:
            continue
    return ips[0]


async def pick_reachable_ip(ips: list[str], port: int) -> str:
    return await run_sync(reachable_ip, ips, port)


async def pin_provider_request(request: httpx.Request) -> None:
    """Resolve once per request; retain the original Host and TLS certificate name."""
    # 配置地址仍禁止查询参数；实际请求允许任务查询参数，并继续校验来源及固定公网 IP。
    validate_endpoint(str(request.url.copy_with(query=None)), resolve=False)
    if get_settings().provider_allow_private:
        return
    host = request.url.host
    port = request.url.port or 443
    try:
        addresses = await run_sync(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM)
        ips = [str(entry[4][0]) for entry in addresses]
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise ValueError("private address")
    except OSError as exc:
        raise HTTPException(502, detail={"code": "provider_dns_error", "error": "模型服务域名暂时无法解析，未发送请求"}) from exc
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "provider_address_rejected", "error": "模型接口当前未解析到公网地址，未发送请求"}) from exc
    request.headers["Host"] = request.url.netloc.decode("ascii")
    request.extensions["sni_hostname"] = host
    request.url = request.url.copy_with(host=await pick_reachable_ip(ips, port))
