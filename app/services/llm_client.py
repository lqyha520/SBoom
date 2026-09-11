"""LLM 客户端 —— 统一封装 OpenAI 兼容接口的调用（含流式）"""

import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, List, Optional

import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

RETRYABLE = (httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError, httpx.ConnectError)  # 连接层故障可安全重试
# 注意：ReadTimeout/ConnectTimeout 不在重试之列——超时意味着请求很可能已到达
# 服务端并计费，盲目重发会造成重复扣费（中转站按次计费场景尤其敏感）


def _should_retry(e: Exception) -> bool:
    """只有确定请求未到达服务端的错误才值得重试（不产生二次计费）。"""
    return isinstance(e, RETRYABLE)


class LLMClient:
    """OpenAI 兼容的 LLM API 客户端"""

    MAX_ATTEMPTS = 3  # 首次 + 重试 2 次（仅网络层错误；见 _should_retry）

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._timeout = 120.0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.llm_base_url,
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(self._timeout),
            )
        return self._client

    async def _get_client_for(self, base_url: str, api_key: str, timeout: float = None) -> httpx.AsyncClient:
        """按 base_url+api_key 创建新 client（不缓存，每次请求独立）"""
        return httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(float(timeout) if timeout else self._timeout),
        )

    async def chat(
        self,
        messages: List[Dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        base_url: str = None,
        model: str = None,
        api_key: str = None,
        timeout: float = None,
    ) -> str:
        """非流式调用，返回完整响应文本。可选传入 base_url/model/api_key/timeout 覆盖默认配置。"""
        url = base_url or settings.llm_base_url
        key = api_key or settings.llm_api_key
        mdl = model or settings.llm_model

        payload = {
            "model": mdl,
            "messages": messages,
            "temperature": temperature or settings.llm_temperature,
            "max_tokens": max_tokens or settings.llm_max_tokens,
            "top_p": top_p or settings.llm_top_p,
            "stream": False,
        }

        client = await self._get_client_for(url, key, timeout)
        try:
            response = None
            for attempt in range(1, self.MAX_ATTEMPTS + 1):
                try:
                    response = await client.post("/chat/completions", json=payload)
                    response.raise_for_status()
                    break
                except Exception as e:
                    if attempt == self.MAX_ATTEMPTS or not _should_retry(e):
                        raise
                    wait = 2 ** attempt
                    logger.warning(f"LLM 请求失败（第 {attempt} 次，{type(e).__name__}），{wait}s 后重试：{e}")
                    await asyncio.sleep(wait)
                    # 断连后旧连接池可能已失效，强制重建
                    await client.aclose()
                    client = await self._get_client_for(url, key, timeout)
            data = response.json()
            return data["choices"][0]["message"]["content"]
        finally:
            # 每次请求独立建 client，用完必须关闭，避免连接池泄漏
            await client.aclose()

    async def chat_stream(
        self,
        messages: List[Dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        base_url: str = None,
        model: str = None,
        api_key: str = None,
        timeout: float = None,
    ) -> AsyncGenerator[str, None]:
        """流式调用，逐 token 产出文本。可选传入 base_url/model/api_key/timeout 覆盖默认配置。"""
        # 修复：mdl 未定义导致 NameError —— 改用与 chat() 一致的 fallback
        mdl = model or settings.llm_model
        client = await self._get_client_for(base_url or settings.llm_base_url, api_key or settings.llm_api_key, timeout)

        payload = {
            "model": mdl,
            "messages": messages,
            "temperature": temperature or settings.llm_temperature,
            "max_tokens": max_tokens or settings.llm_max_tokens,
            "top_p": top_p or settings.llm_top_p,
            "stream": True,
        }

        try:
            async with client.stream("POST", "/chat/completions", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        finally:
            # 每次请求独立建 client，用完必须关闭，避免连接池泄漏
            await client.aclose()

    async def reconfigure(self, base_url: Optional[str] = None, api_key: Optional[str] = None, timeout: Optional[float] = None) -> None:
        """热更新 LLM 配置（内存生效）。关闭旧连接池并更新内部参数，避免直接替换模块级单例。"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if base_url:
            settings.llm_base_url = base_url.rstrip("/")
        if api_key:
            settings.llm_api_key = api_key
        if timeout:
            self._timeout = float(timeout)
    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


# 全局单例
llm_client = LLMClient()
