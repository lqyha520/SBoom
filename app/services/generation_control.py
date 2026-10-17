"""Database-backed request deduplication, admission limits, and reported LLM usage."""

import asyncio
import contextlib
import hashlib
import json
import logging
import re
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from typing import cast

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.blocking import run_sync
from app.config import get_settings
from app.db import db
from app.metrics import generation_requests_total, llm_attempts_total, llm_tokens_total, provider_model


@dataclass
class Usage:
    model_calls: int = 0
    reported_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    repairs: int = 0


_INSTANCE = uuid.uuid4().hex
logger = logging.getLogger(__name__)
_finishes: set[asyncio.Task] = set()
LEASE_EXPIRED_ERROR = json.dumps({
    "code": "generation_lease_expired",
    "error": "任务心跳超时，结果尚不确定，请稍后查询原请求",
}, ensure_ascii=False)


async def finish(*args):
    task = asyncio.create_task(run_sync(_finish, *args))
    _finishes.add(task)
    task.add_done_callback(_finishes.discard)
    await asyncio.shield(task)


async def shutdown_generation():
    if _finishes:
        await asyncio.gather(*list(_finishes), return_exceptions=True)


def _renew(user_id, request_id):
    with db() as conn:
        conn.execute("UPDATE generation_requests SET lease_expires_at = ? WHERE user_id = ? AND request_id = ? AND status = 'running' AND instance_id = ?",
                     (int(time.time()) + get_settings().generation_heartbeat_seconds, user_id, request_id, _INSTANCE))


async def heartbeat(user_id, request_id):
    while True:
        await asyncio.sleep(get_settings().generation_heartbeat_seconds / 3)
        try:
            await run_sync(_renew, user_id, request_id)
        except Exception:
            # 暂时数据库不可用时继续尝试；过期记录不会永久占满准入。
            logger.warning("生成任务续租失败，将在下个心跳重试", exc_info=False)


def reclaim_expired(limit: int | None = None):
    with db() as conn:
        now = int(time.time())
        query = ("UPDATE generation_requests SET status = 'unknown', finished_at = ?, error_json = ? "
                 "WHERE (user_id, request_id) IN (SELECT user_id, request_id FROM generation_requests "
                 "WHERE status = 'running' AND COALESCE(NULLIF(lease_expires_at, 0), created_at + 90) < ? "
                 "ORDER BY created_at, user_id, request_id")
        params = [now, LEASE_EXPIRED_ERROR, now]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        # 等待行锁后再次核对状态与租约，不能覆盖刚完成或刚续租的任务。
        conn.execute(query + ") AND status = 'running' AND COALESCE(NULLIF(lease_expires_at, 0), created_at + 90) < ?", [*params, now])


current_usage: ContextVar[Usage | None] = ContextVar("generation_usage", default=None)


def record_attempt() -> None:
    llm_attempts_total.labels(provider_model.get()).inc()
    usage = current_usage.get()
    if usage is not None:
        usage.model_calls += 1


def record_usage(value) -> None:
    usage = current_usage.get()
    if not isinstance(value, dict):
        return
    prompt, completion = value.get("prompt_tokens"), value.get("completion_tokens")
    if type(prompt) is not int or type(completion) is not int or min(prompt, completion) < 0:
        return
    llm_tokens_total.labels(provider_model.get(), "prompt").inc(prompt)
    llm_tokens_total.labels(provider_model.get(), "completion").inc(completion)
    if usage is None:
        return
    usage.reported_calls += 1
    usage.prompt_tokens += prompt
    usage.completion_tokens += completion


def reserve_repairs(count: int) -> int:
    usage = current_usage.get()
    limit = get_settings().generation_repair_limit
    remaining = max(0, limit - (usage.repairs if usage else 0))
    count = max(0, min(count, remaining))
    if usage is not None:
        usage.repairs += count
    return count


def _begin(user_id: int, request_id: str, kind: str, payload: dict) -> dict | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", request_id):
        raise HTTPException(400, detail={"error": "无效的请求 ID"})
    # 空的新增可选字段不改变旧请求指纹，部署后仍能重放原请求。
    if kind == "batch" and not payload.get("previous_request_ids"):
        payload = {key: value for key, value in payload.items() if key != "previous_request_ids"}
    fingerprint = hashlib.sha256(json.dumps(
        {"kind": kind, "payload": payload}, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"),
    ).encode()).hexdigest()
    settings = get_settings()
    now = int(time.time())
    # One short transaction serializes admission across workers, including PostgreSQL.
    with db(serialized="generation") as conn:
        if conn.execute("SELECT 1 FROM generation_tombstones WHERE user_id = ? AND request_id = ?", (user_id, request_id)).fetchone():
            raise HTTPException(410, detail={"error": "该请求已归档，不会再次调用模型"})
        row = conn.execute(
            "SELECT * FROM generation_requests WHERE user_id = ? AND request_id = ?",
            (user_id, request_id),
        ).fetchone()
        if row:
            if row["payload_hash"] != fingerprint:
                raise HTTPException(409, detail={"error": "请求 ID 已用于其他出题条件"})
            if row["status"] == "succeeded":
                if row["result_json"] and row["finished_at"] >= now - settings.generation_result_days * 86400:
                    # 缓存由 _finish 用 json.dumps 写入，必然是对象；cast 只补类型、不改行为
                    return cast(dict, json.loads(row["result_json"]))
                raise HTTPException(410, detail={"error": "该请求已完成，结果缓存已过期或不支持重放，不会再次调用模型"})
            if row["error_status"]:
                raise HTTPException(row["error_status"], detail=json.loads(row["error_json"]))
            raise HTTPException(409, detail={
                "error": "该请求仍在处理或结果尚不确定，不会重复调用模型",
                "code": "generation_pending", "request_id": request_id,
            })
        total = conn.execute("SELECT COUNT(*) FROM generation_requests WHERE status = 'running' AND COALESCE(NULLIF(lease_expires_at, 0), created_at + 90) >= ?", (now,)).fetchone()[0]
        active = conn.execute(
            "SELECT COUNT(*) FROM generation_requests WHERE user_id = ? AND status = 'running' AND COALESCE(NULLIF(lease_expires_at, 0), created_at + 90) >= ?", (user_id, now),
        ).fetchone()[0]
        if settings.generation_daily_limit > 0:
            used = conn.execute(
                "SELECT COUNT(*) FROM generation_requests WHERE user_id = ? AND created_at >= ?",
                (user_id, now - 86400),
            ).fetchone()[0]
            if used >= settings.generation_daily_limit:
                raise HTTPException(429, detail={"error": "已达到过去 24 小时的生成请求额度", "code": "generation_quota"})
        if total >= settings.generation_global_concurrency or active >= settings.generation_user_concurrency:
            raise HTTPException(429, detail={"error": "生成任务繁忙，请稍后再试", "code": "generation_busy"}, headers={"Retry-After": "5"})
        if kind == "image":
            from app.services.image_assets import admit
            admit(conn, user_id)
        conn.execute(
            "INSERT INTO generation_requests (user_id, request_id, kind, payload_hash, status, created_at, lease_expires_at, instance_id) "
            "VALUES (?, ?, ?, ?, 'running', ?, ?, ?)", (user_id, request_id, kind, fingerprint, now, now + settings.generation_heartbeat_seconds, _INSTANCE),
        )
    return None


def _finish(user_id: int, request_id: str, usage: Usage, status: str, result=None, error=None) -> None:
    error_status, detail = error if error else (0, {})
    with db() as conn:
        # 仅原实例可补交清理任务标记为未知的结果，真实终态不会被覆盖。
        completed = conn.execute(
            "UPDATE generation_requests SET status = ?, finished_at = ?, result_json = ?, "
            "error_json = ?, error_status = ?, model_calls = ?, reported_calls = ?, "
            "prompt_tokens = ?, completion_tokens = ? WHERE user_id = ? AND request_id = ? AND instance_id = ? "
            "AND (status = 'running' OR (status = 'unknown' AND error_status = 0 AND error_json = ?)) RETURNING kind",
            (status, int(time.time()), json.dumps(result, ensure_ascii=False) if result is not None else "",
             json.dumps(detail, ensure_ascii=False), error_status, usage.model_calls, usage.reported_calls,
             usage.prompt_tokens, usage.completion_tokens, user_id, request_id, _INSTANCE, LEASE_EXPIRED_ERROR),
        ).fetchone()
    if completed:
        generation_requests_total.labels(completed["kind"], status).inc()


def metered(kind: str):
    """Apply to paid endpoints; retries with the same ID never start a second call."""
    def decorate(handler):
        @wraps(handler)
        async def wrapped(*args, **kwargs):
            http_request = kwargs.get("http_request")
            user = kwargs["user"]
            request = kwargs["request"]
            request_id = (http_request.headers.get("X-Request-ID") if http_request else None) or uuid.uuid4().hex
            try:
                cached = await run_sync(_begin, user.id, request_id, kind, request.model_dump(mode="json"))
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, dict) else {"error": exc.detail}
                raise HTTPException(exc.status_code, {**detail, "request_id": request_id}, headers=dict(exc.headers) if exc.headers else None) from exc
            if cached is not None:
                generation_requests_total.labels(kind, "replayed").inc()
                return cached
            usage = Usage()
            token = current_usage.set(usage)
            lease_task = asyncio.create_task(heartbeat(user.id, request_id))
            deadline = asyncio.get_running_loop().time() + get_settings().generation_lease_seconds - 5
            try:
                async with asyncio.timeout_at(deadline):
                    result = await handler(*args, **kwargs)
                if isinstance(result, StreamingResponse):
                    original = result.body_iterator

                    async def tracked_stream():
                        stream_token = current_usage.set(usage)
                        stream_lease = asyncio.create_task(heartbeat(user.id, request_id))
                        outcome = "unknown"
                        try:
                            async with asyncio.timeout_at(deadline):
                                async for chunk in original:
                                    text = chunk.decode() if isinstance(chunk, bytes) else str(chunk)
                                    if text.startswith("data: "):
                                        event = text[6:].strip()
                                        if event == "[DONE]" and outcome != "failed":
                                            outcome = "succeeded"
                                        elif event.startswith("{") and "error" in json.loads(event):
                                            outcome = "failed"
                                    yield chunk
                        finally:
                            current_usage.reset(stream_token)
                            stream_lease.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await stream_lease
                            await finish(user.id, request_id, usage, outcome)

                    result.body_iterator = tracked_stream()
                    result.headers["X-Request-ID"] = request_id
                    return result
                data = result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result)
                if kind == "image":
                    from app.services.image_assets import persist
                    data = await run_sync(persist, user.id, request_id, data)
                data["request_id"] = request_id
                await finish(user.id, request_id, usage, "succeeded", data)
                return data
            except (Exception, asyncio.CancelledError) as exc:
                status_code = exc.status_code if isinstance(exc, HTTPException) else 503
                # 不复用上面 except 分支的 detail：那里的 detail 已被收窄为 dict，而这里可能是 str
                failure_detail = exc.detail if isinstance(exc, HTTPException) else {"error": "生成中断，结果尚不确定，请先查询请求状态"}
                if isinstance(failure_detail, dict):
                    failure_detail = {**failure_detail, "request_id": request_id}
                await finish( user.id, request_id, usage,
                    "unknown" if status_code >= 500 else "failed", None, (status_code, failure_detail),
                )
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise HTTPException(status_code, detail=failure_detail,
                                    headers=dict(exc.headers) if isinstance(exc, HTTPException) and exc.headers else None) from exc
            except BaseException:
                # KeyboardInterrupt / SystemExit 等进程级信号：只把请求标记为结果未知，原样上抛，
                # 不能翻译成 503——那会把 Ctrl+C 吞成一次普通失败
                await finish( user.id, request_id, usage, "unknown", None,
                    (503, {"error": "服务中断，结果尚不确定，请先查询请求状态", "request_id": request_id}),
                )
                raise
            finally:
                current_usage.reset(token)
                lease_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await lease_task
        return wrapped
    return decorate


def usage_summary(user_id: int | None = None) -> dict:
    since = int(time.time()) - 86400
    lease_cutoff = int(time.time())
    where = "created_at >= ?" + (" AND user_id = ?" if user_id is not None else "")
    params = (since, user_id) if user_id is not None else (since,)
    with db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS requests, "
            "COALESCE(SUM(CASE WHEN status = 'succeeded' THEN 1 ELSE 0 END), 0) AS succeeded, "
            "COALESCE(SUM(CASE WHEN status = 'running' AND COALESCE(NULLIF(lease_expires_at, 0), created_at + 90) >= ? THEN 1 ELSE 0 END), 0) AS running, "
            "COALESCE(SUM(CASE WHEN status = 'unknown' OR (status = 'running' AND COALESCE(NULLIF(lease_expires_at, 0), created_at + 90) < ?) THEN 1 ELSE 0 END), 0) AS unknown, "
            "COALESCE(SUM(model_calls), 0) AS model_calls, COALESCE(SUM(reported_calls), 0) AS reported_calls, "
            "COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens, COALESCE(SUM(completion_tokens), 0) AS completion_tokens "
            "FROM generation_requests WHERE " + where, (lease_cutoff, lease_cutoff, *params),
        ).fetchone()
    return {**dict(row), "daily_limit": get_settings().generation_daily_limit}


def request_status(user_id: int, request_id: str) -> dict:
    with db() as conn:
        row = conn.execute(
            "SELECT request_id, kind, status, created_at, lease_expires_at, finished_at, result_json, error_json, error_status, "
            "model_calls, reported_calls, prompt_tokens, completion_tokens "
            "FROM generation_requests "
            "WHERE user_id = ? AND request_id = ?", (user_id, request_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, detail={"error": "请求不存在"})
    now, settings = int(time.time()), get_settings()
    status = row["status"]
    if status == "running" and (row["lease_expires_at"] or row["created_at"] + settings.generation_heartbeat_seconds) < now:
        status = "unknown"
    expired = bool(row["finished_at"] and row["finished_at"] < now - settings.generation_result_days * 86400)
    return {"request_id": row["request_id"], "kind": row["kind"], "status": status,
            "result": json.loads(row["result_json"]) if row["result_json"] and not expired else None,
            "error": json.loads(row["error_json"]) if row["error_json"] else None,
            "error_status": row["error_status"], "cache_expired": expired,
            "usage": {key: row[key] for key in ("model_calls", "reported_calls", "prompt_tokens", "completion_tokens")}}
