"""LLM 客户端 —— 统一封装 OpenAI 兼容接口的调用（含流式）

连接池按 (base_url, api_key) 维度缓存复用，避免每次请求重建 TLS 连接；
单次请求的超时通过 httpx 的 per-request timeout 传入，不影响池化。
"""

import asyncio
import json
import logging
from collections import OrderedDict
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import HTTPException

from app.blocking import run_sync
from app.config import get_settings
from app.http_limits import limited_lines
from app.metrics import observe_provider
from app.provider_policy import pin_provider_request
from app.services.generation_budget import reserve
from app.services.generation_control import current_usage, record_attempt, record_usage

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


def _check_text_completion(message: dict, reason: str | None) -> None:
    """拒绝与工具调用都不是题目文本；兼容未返回 finish_reason 的中转接口。"""
    if message.get("refusal") or reason == "content_filter":
        raise HTTPException(502, detail={"code": "provider_content_filtered", "error": "模型拒绝生成本次内容"})
    if message.get("tool_calls") or message.get("function_call") or reason not in (None, "stop", "length"):
        raise ValueError("模型未完成文本响应")


class OutputTruncated(HTTPException):
    """保留原始残片供服务端校验；错误响应只公开已验证的大题。"""

    def __init__(self, partial_text: str):
        super().__init__(422, detail={
            "code": "generation_truncated",
            "error": "生成内容达到模型输出上限，请减少单次题量后重试；查询原请求不会再次调用模型",
        })
        self.partial_text = partial_text


def parse_stream_chunk(text: str, *, on_usage: Callable[[dict], None] | None = None) -> tuple[str, str | None, dict | None]:
    """只接受兼容聊天协议；错误页、错误事件及非文本 delta 不算连通成功。"""
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("invalid stream event")
        usage = data.get("usage")
        # 先保存累计用量，随后拒绝/异常结束也不能漏记这一轮已上报的费用。
        if isinstance(usage, dict) and on_usage is not None:
            on_usage(usage)
        if "error" in data or not isinstance(data.get("choices"), list):
            raise ValueError("invalid stream event")
        if not data["choices"]:
            if not isinstance(usage, dict):
                raise ValueError("empty stream event")
            return "", None, usage
        choice = data["choices"][0]
        delta = choice.get("delta", {})
        if not isinstance(delta, dict):
            raise ValueError("invalid stream delta")
        content = delta.get("content")
        if content is None:
            content = ""
        if not isinstance(content, str):
            raise ValueError("non-text stream event")
        reason = choice.get("finish_reason")
        if reason is not None and not isinstance(reason, str):
            raise ValueError("invalid finish reason")
        _check_text_completion(delta, reason)
        return content, reason, usage if isinstance(usage, dict) else None
    except (ValueError, TypeError, AttributeError, IndexError, RecursionError) as exc:
        raise HTTPException(502, detail={"code": "provider_invalid_stream", "error": "模型未返回有效的流式文本"}) from exc


class LLMClient:
    """OpenAI 兼容的 LLM API 客户端"""

    MAX_ATTEMPTS = 3  # 首次 + 重试 2 次（仅网络层错误；见 _should_retry）
    DEFAULT_TIMEOUT = 120.0
    MAX_CACHED_CLIENTS = 8  # 连接池缓存上限（LRU 淘汰），防止 key/地址变化导致无限增长

    def __init__(self):
        self._clients: OrderedDict[tuple[str, str], httpx.AsyncClient] = OrderedDict()
        self._busy: dict[httpx.AsyncClient, int] = {}
        self._closing: set[asyncio.Task[None]] = set()

    def _evict_oldest(self, free_slots: int = 1) -> None:
        """缓存超限时淘汰最久未用的 client（连接在后台异步关闭，不阻塞调用方）。"""
        while len(self._clients) > LLMClient.MAX_CACHED_CLIENTS - free_slots:
            idle = next((key for key, value in self._clients.items() if not self._busy.get(value)), None)
            if idle is None:
                break
            old_client = self._clients.pop(idle)
            try:
                loop = asyncio.get_running_loop()
                task = loop.create_task(self._aclose_quietly(old_client))
                self._closing.add(task)
                task.add_done_callback(self._closing.discard)
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
            trust_env=False,
            event_hooks={"request": [pin_provider_request]},
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
        max_attempts: int | None = None,
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
            response_content: bytearray | None = None
            attempts = max_attempts if max_attempts is not None else self.MAX_ATTEMPTS
            for attempt in range(1, attempts + 1):
                try:
                    if current_usage.get() is not None:
                        await run_sync(reserve, tokens=len(json.dumps(messages, ensure_ascii=False).encode()) + (max_tokens if max_tokens is not None else settings.llm_max_tokens) + 2048)
                    record_attempt()
                    async with client.stream("POST", "/chat/completions", json=payload, timeout=self._req_timeout(timeout)) as streamed:
                        streamed.raise_for_status()
                        raw = bytearray()
                        async for chunk in streamed.aiter_bytes(chunk_size=64 * 1024):
                            if len(raw) + len(chunk) > settings.provider_max_response_bytes:
                                raise HTTPException(502, detail={"code": "provider_response_too_large", "error": "模型响应超过安全上限，请减少题量"})
                            raw.extend(chunk)
                        # aiter_bytes 已解压；直接解析正文，不能携带原压缩头再次构造响应。
                        response_content = raw
                    break
                except Exception as e:
                    if attempt == attempts or not _should_retry(e):
                        raise
                    wait = 2 ** attempt
                    logger.warning("模型连接失败（第 %s 次，%s），%s 秒后重试", attempt, type(e).__name__, wait)
                    await asyncio.sleep(wait)
                    # httpx retires broken connections; closing this shared client
                    # would interrupt other users' in-flight requests.

            if response_content is None:
                # 上面的循环要么 break（正文已赋值）要么抛出；这里只是让类型收窄
                raise RuntimeError("LLM 请求未返回响应")
            try:
                data = await run_sync(json.loads, response_content)
                if not isinstance(data, dict):
                    raise ValueError("模型响应不是对象")
                record_usage(data.get("usage"))
                choices = data.get("choices")
                if "error" in data or not isinstance(choices, list) or not choices:
                    raise ValueError("模型返回错误或缺少候选")
                choice = choices[0]
                message = choice["message"]
                if not isinstance(message, dict):
                    raise ValueError("模型消息格式错误")
                _check_text_completion(message, choice.get("finish_reason"))
                content = message.get("content")
                if choice.get("finish_reason") == "length":
                    raise OutputTruncated(content if isinstance(content, str) else "")
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("模型未返回文本")
                return content
            except (ValueError, KeyError, IndexError, TypeError, AttributeError, RecursionError) as e:
                # LLM 返回了非 JSON 错误页或结构异常——翻译成统一异常，由调用方按 502 处理
                logger.error("模型响应结构异常: %s", type(e).__name__)
                raise HTTPException(502, detail={"code": "provider_invalid_response", "error": "模型响应结构异常"}) from e

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
            if current_usage.get() is not None:
                await run_sync(reserve, tokens=len(json.dumps(messages, ensure_ascii=False).encode()) + (max_tokens if max_tokens is not None else settings.llm_max_tokens) + 2048)
            record_attempt()
            final_usage = None

            def remember_usage(usage: dict) -> None:
                nonlocal final_usage
                if all(type(usage.get(key)) is int and usage[key] >= 0 for key in ("prompt_tokens", "completion_tokens")):
                    final_usage = usage

            completed = received = False
            try:
                async with client.stream(
                    "POST", "/chat/completions", json=payload, timeout=self._req_timeout(timeout)) as response:
                    response.raise_for_status()
                    async for line in limited_lines(response, settings.provider_max_response_bytes):
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            completed = True
                            break
                        content, finished, _ = parse_stream_chunk(data_str, on_usage=remember_usage)
                        if finished == "length":
                            raise OutputTruncated("")
                        completed = completed or finished == "stop"
                        if content.strip():
                            received = True
                        if content:
                            yield content
                if not received or not completed:
                    raise HTTPException(502, detail={"code": "provider_incomplete_stream", "error": "模型流式响应为空或未完整结束"})
            finally:
                # 有些服务在多个事件中重复累计用量，一次模型调用只能累计一次。
                record_usage(final_usage)

    async def close(self) -> None:
        """关闭全部缓存的连接池（应用关停时调用）。"""
        for client in self._clients.values():
            try:
                await client.aclose()
            except Exception:
                pass
        self._clients.clear()
        if self._closing:
            await asyncio.gather(*self._closing)


# 全局单例
llm_client = LLMClient()
