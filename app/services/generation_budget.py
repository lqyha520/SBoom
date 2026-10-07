"""按滚动 24 小时预留调用预算；未知计费结果也不退还预留。"""
import time
import uuid

from fastapi import HTTPException

from app.config import get_settings
from app.db import db


def reserve(tokens=0, images=0):
    settings = get_settings()
    now = int(time.time())
    with db(serialized="generation") as conn:
        row = conn.execute("SELECT COALESCE(SUM(tokens),0), COALESCE(SUM(images),0) FROM generation_budget WHERE created_at >= ?", (now - 86400,)).fetchone()
        if row[0] + tokens > settings.generation_global_daily_tokens or row[1] + images > settings.generation_global_daily_images:
            raise HTTPException(429, detail={"error": "全站今日生成预算已用尽，请稍后再试或联系管理员", "code": "generation_budget"})
        conn.execute("DELETE FROM generation_budget WHERE created_at < ?", (now - 86400,))
        conn.execute("INSERT INTO generation_budget(id, created_at, tokens, images) VALUES (?, ?, ?, ?)", (uuid.uuid4().hex, now, tokens, images))
