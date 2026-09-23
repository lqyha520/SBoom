"""LLM 客户端 —— 统一封装 OpenAI 兼容接口的调用（含流式）

连接池按 (base_url, api_key) 维度缓存复用，避免每次请求重建 TLS 连接；
单次请求的超时通过 httpx 的 per-request timeout 传入，不影响池化。
"""

import asyncio
import json
import logging
from collections import OrderedDict
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx

from app.config import get_settings
from app.metrics import observe_provider
from app.services.generation_control import record_attempt, record_usage

logger = logging.getLogger(__name__)

settings = get_settings()

RETRYABLE = (httpx.ConnectError, httpx.ConnectTimeout)  # Read/write/protocol errors may occur after the provider billed the request.
# 注意：ReadTimeout 不在重试之列——读超时意味着请求很可能已到达服务端并计费，
# 盲目重发会造成重复扣费（中转站按次计费场景尤其敏感）。
# ConnectTimeout 则可以安全重试：TCP/TLS 握手都没完成，请求体根本没发出去，不可能被计费。

# 连接/取池超时单独收紧：整体超时可配到 600s，但握手 10s 还不通就该报错，
# 否则一个不可达的中转站会把生成请求挂满整个超时窗口。
CONNECT_TIMEOUT = 10.0
POOL_TIMEOUT = 10.0
# 单个 (base_url, api_key) 的连接池上限；全局并发由 generation_global_concurrency 限制，这里只兜底
CLIENT_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)


def _should_retry(e: Exception) -> bool:
    """只有确定请求未到达服务端的错误才值得重试（不产生二次计费）。"""
    return isinstance(e, RETRYABLE)


class LLMClient:
    """OpenAI 兼容的 LLM API 客户端"""

    MAX_ATTEMPTS = 3  # 首次 + 重试 2 次（仅网络层错误；见 _should_retry）
    DEFAULT_TIMEOUT = 120.0
    MAX_CACHED_CLIENTS = 8  # 连接池缓存上限（LRU 淘汰），防止 key/地址变化导致无限增长

    def __init__(self):
        self._clients: OrderedDict[tuple[str, str], httpx.AsyncClient] = OrderedDict()
        self._busy: dict[httpx.AsyncClient, int] = {}

    def _evict_oldest(self, free_slots: int = 1) -> None:
        """缓存超限时淘汰最久未用的 client（连接在后台异步关闭，不阻塞调用方）。"""
        while len(self._clients) > LLMClient.MAX_CACHED_CLIENTS - free_slots:
            idle = next((key for key, value in self._clients.items() if not self._busy.get(value)), None)
            if idle is None:
                break
            old_client = self._clients.pop(idle)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._aclose_quietly(old_client))
            except RuntimeError:
                pass  # 无事件循环（理论上不会发生），由 GC 兜底

    @asynccontextmanager
    async def _borrow_client(self, base_url: str, api_key: str):
        client = self._get_client_for(base_url, api_key)
        self._busy[client] = self._busy.get(client, 0) + 1
        try:
            yield client
        finally:
            self._busy[client] -= 1
            if not self._busy[client]:
                del self._busy[client]
            self._evict_oldest(free_slots=0)

    def _get_client_for(self, base_url: str, api_key: str) -> httpx.AsyncClient:
        """按 base_url+api_key 复用（或创建）长连接 client，LRU 上限内复用。"""
        cache_key = (base_url, api_key)
        client = self._clients.get(cache_key)
        if client is not None and not client.is_closed:
            self._clients.move_to_end(cache_key)  # LRU 触碰
            return client
        self._evict_oldest()
        client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(self.DEFAULT_TIMEOUT, connect=CONNECT_TIMEOUT, pool=POOL_TIMEOUT),
            limits=CLIENT_LIMITS,
        )
        self._clients[cache_key] = client
        return client

    @staticmethod
    async def _aclose_quietly(client: httpx.AsyncClient) -> None:
        try:
            await client.aclose()
        except Exception:
            pass

    @staticmethod
    def _req_timeout(timeout: float | None) -> httpx.Timeout:
        """单次请求的超时覆盖（连接池 client 的默认超时较长，按调用方配置收紧）。

        read/write 用调用方配置的整体超时；connect/pool 固定收紧为 10s——
        否则 timeout=600 时，连不上的地址也要等满 600s 才报错。
        """
        total = float(timeout) if timeout else LLMClient.DEFAULT_TIMEOUT
        return httpx.Timeout(total, connect=CONNECT_TIMEOUT, pool=POOL_TIMEOUT)

    @observe_provider
    async def chat(
        self,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> str:
        """非流式调用，返回完整响应文本。可选传入 base_url/model/api_key/timeout 覆盖默认配置。"""
        url = base_url or settings.llm_base_url
        key = api_key or settings.llm_api_key
        mdl = model or settings.llm_model

        payload = {
            "model": mdl,
            "messages": messages,
            # is not None 判断：显式传 0 是合法值，不能被 or 吃掉
            "temperature": temperature if temperature is not None else settings.llm_temperature,
            "max_tokens": max_tokens if max_tokens is not None else settings.llm_max_tokens,
            "top_p": top_p if top_p is not None else settings.llm_top_p,
            "stream": False,
        }

        async with self._borrow_client(url, key) as client:
            response: httpx.Response | None = None
            for attempt in range(1, self.MAX_ATTEMPTS + 1):
                try:
                    record_attempt()
                    response = await client.post(
                        "/chat/completions", json=payload, timeout=self._req_timeout(timeout))
                    response.raise_for_status()
                    break
                except Exception as e:
                    if attempt == self.MAX_ATTEMPTS or not _should_retry(e):
                        raise
                    wait = 2 ** attempt
                    logger.warning("模型连接失败（第 %s 次，%s），%s 秒后重试", attempt, type(e).__name__, wait)
                    await asyncio.sleep(wait)
                    # httpx retires broken connections; closing this shared client
                    # would interrupt other users' in-flight requests.

            if response is None:
                # 上面的循环要么 break（response 已赋值）要么抛出；这里只是让类型收窄
                raise RuntimeError("LLM 请求未返回响应")
            try:
                data = response.json()
                record_usage(data.get("usage"))
                return str(data["choices"][0]["message"]["content"])
            except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
                # LLM 返回了非 JSON 错误页或结构异常——翻译成统一异常，由调用方按 502 处理
                logger.error("模型响应结构异常: %s", type(e).__name__)
                raise RuntimeError(f"LLM 响应结构异常: {e}") from e

    @observe_provider
    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> AsyncGenerator[str, None]:
        """流式调用，逐 token 产出文本。可选传入 base_url/model/api_key/timeout 覆盖默认配置。"""
        url = base_url or settings.llm_base_url
        key = api_key or settings.llm_api_key
        mdl = model or settings.llm_model

        payload = {
            "model": mdl,
            "messages": messages,
            "temperature": temperature if temperature is not None else settings.llm_temperature,
            "max_tokens": max_tokens if max_tokens is not None else settings.llm_max_tokens,
            "top_p": top_p if top_p is not None else settings.llm_top_p,
            "stream": True,
        }

        async with self._borrow_client(url, key) as client:
            record_attempt()
            async with client.stream(
                "POST", "/chat/completions", json=payload, timeout=self._req_timeout(timeout)) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            record_usage(chunk.get("usage"))
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue

    async def close(self) -> None:
        """关闭全部缓存的连接池（应用关停时调用）。"""
        for client in self._clients.values():
            try:
                await client.aclose()
            except Exception:
                pass
        self._clients.clear()


# 全局单例
llm_client = LLMClient()
