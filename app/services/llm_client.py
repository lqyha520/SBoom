"""LLM 客户端 —— 统一封装 OpenAI 兼容接口的调用（含流式）"""

import json
from typing import AsyncGenerator, Optional

import httpx
from app.config import get_settings

settings = get_settings()


class LLMClient:
    """OpenAI 兼容的 LLM API 客户端"""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.llm_base_url,
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(60.0),
            )
        return self._client

    async def chat(
        self,
        messages: list[dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
    ) -> str:
        """非流式调用，返回完整响应文本"""
        client = await self._get_client()

        payload = {
            "model": settings.llm_model,
            "messages": messages,
            "temperature": temperature or settings.llm_temperature,
            "max_tokens": max_tokens or settings.llm_max_tokens,
            "top_p": top_p or settings.llm_top_p,
            "stream": False,
        }

        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def chat_stream(
        self,
        messages: list[dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
    ) -> AsyncGenerator[str, None]:
        """流式调用，逐 token 产出文本"""
        client = await self._get_client()

        payload = {
            "model": settings.llm_model,
            "messages": messages,
            "temperature": temperature or settings.llm_temperature,
            "max_tokens": max_tokens or settings.llm_max_tokens,
            "top_p": top_p or settings.llm_top_p,
            "stream": True,
        }

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

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


# 全局单例
llm_client = LLMClient()
