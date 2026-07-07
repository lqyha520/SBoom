"""题目缓存模块 —— 基于内存的 LRU 缓存，避免重复调用 LLM"""

import hashlib
import json
import time
from collections import OrderedDict
from typing import Optional

from app.config import get_settings


class QuestionCache:
    """
    内存缓存，LRU 淘汰策略
    cache_key = hash(grade + subject + keyword + game_type + difficulty + count)
    """

    def __init__(self, max_size: int = 500, ttl_seconds: int = 86400):
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds  # 默认 24 小时

    @staticmethod
    def generate_key(
        grade: str, subject: str, keyword: str,
        game_type: str, difficulty: str, count: int,
    ) -> str:
        """生成缓存 key"""
        raw = f"{grade}|{subject}|{keyword}|{game_type}|{difficulty}|{count}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[dict]:
        """获取缓存，过期返回 None"""
        if key not in self._cache:
            return None

        entry = self._cache[key]
        if time.time() - entry["timestamp"] > self._ttl_seconds:
            del self._cache[key]
            return None

        # 移到队尾（最近使用）
        self._cache.move_to_end(key)
        return entry["data"]

    def set(self, key: str, data: dict) -> None:
        """写入缓存"""
        # LRU 淘汰
        if len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)

        self._cache[key] = {
            "data": data,
            "timestamp": time.time(),
        }
        self._cache.move_to_end(key)

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()

    def stats(self) -> dict:
        """缓存统计"""
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "ttl_seconds": self._ttl_seconds,
        }


# 全局单例
settings = get_settings()
question_cache = QuestionCache(
    max_size=settings.cache_max_size,
    ttl_seconds=settings.cache_ttl_seconds,
)
