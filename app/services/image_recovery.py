"""原生图任务的加密检查点；恢复只能查询和下载，不能提交生成请求。"""

import asyncio
import json
import logging
import time
import uuid
from contextvars import ContextVar
from urllib.parse import urlsplit

from fastapi import HTTPException

from app.blocking import run_sync, run_sync_in
from app.config import get_settings
from app.db import db
from app.security import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)
current_request: ContextVar[tuple[int, str] | None] = ContextVar("image_recovery_request", default=None)
MAX_RECOVERY_ATTEMPTS = 8
RECOVERY_SECONDS = 60
_tasks: set[asyncio.Task] = set()


def _encode(state: dict, attempts: int = 0, retry_at: int = 0) -> str:
    plain = json.dumps(state, ensure_ascii=False)
    if len(plain.encode()) > 64 * 1024:
        raise ValueError("Image checkpoint exceeds limit")
    return json.dumps({"image_recovery": encrypt_secret(plain), "attempts": attempts, "retry_at": retry_at})


def available(row: dict) -> bool:
    if row["kind"] != "image" or row["status"] == "succeeded":
        return False
    if row["created_at"] < time.time() - get_settings().generation_result_days * 86400:
        return False
    try:
        envelope = json.loads(row["result_json"] or "{}")
        if not envelope.get("image_recovery") or envelope.get("attempts", 0) >= MAX_RECOVERY_ATTEMPTS:
            return False
        state = json.loads(decrypt_secret(envelope["image_recovery"]))
        return bool(state.get("task") or state.get("asset_url") or state.get("saved_asset"))
    except (ValueError, TypeError, KeyError):
        return False


def _save(owner: tuple[int, str], state: dict) -> None:
    from app.services.generation_control import _INSTANCE
    with db() as conn:
        updated = conn.execute(
            "UPDATE generation_requests SET result_json = ? WHERE user_id = ? AND request_id = ? "
            "AND status = 'running' AND instance_id = ? RETURNING request_id",
            (_encode(state), *owner, _INSTANCE),
        ).fetchone()
    if not updated:
        raise HTTPException(503, detail={"code": "image_checkpoint_unavailable", "failover_safe": False,
                                        "error": "生图请求记录已变更，已停止继续调用模型，请查询原请求"})


async def checkpoint(config: dict, prompt: str, *, task: dict | None = None, asset_url: str = "") -> None:
    owner = current_request.get()
    if owner is None:
        return
    from app.services.image_generation import generation_url
    state = {"profile_id": config.get("id") or "legacy", "endpoint": generation_url(config["baseUrl"]),
             "model": config["model"], "prompt": prompt, "task": task, "asset_url": asset_url}
    try:
        await run_sync(_save, owner, state)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("生图检查点保存失败（%s）", type(exc).__name__)
        raise HTTPException(503, detail={"code": "image_checkpoint_unavailable", "failover_safe": False,
                                        "error": "生图状态记录保存失败，已停止继续调用模型，请查询原请求"}) from exc


def checkpoint_saved(result: dict) -> None:
    """识图检查前记录已落盘的原图；中断恢复不重复发起收费检查。"""
    owner = current_request.get()
    if owner is not None:
        _save(owner, {"saved_asset": True, "prompt": result.get("prompt", ""),
                      "quality_review": result["quality_review"]})


def _claim(user_id: int, request_id: str) -> dict | None:
    now = int(time.time())
    with db(serialized="generation") as conn:
        row = conn.execute("SELECT * FROM generation_requests WHERE user_id = ? AND request_id = ? FOR UPDATE",
                           (user_id, request_id)).fetchone()
        if not row or not available(dict(row)):
            return None
        if row["status"] == "running" and (row["lease_expires_at"] or row["created_at"] + 90) >= now:
            return None
        envelope = json.loads(row["result_json"])
        if envelope.get("retry_at", 0) > now:
            return None
        state = json.loads(decrypt_secret(envelope["image_recovery"]))
        attempts = envelope.get("attempts", 0) + 1
        token = "image-recovery-" + uuid.uuid4().hex
        conn.execute("UPDATE generation_requests SET status = 'running', lease_expires_at = ?, instance_id = ?, "
                     "result_json = ? WHERE user_id = ? AND request_id = ?",
                     (now + RECOVERY_SECONDS + 30, token, _encode(state, attempts), user_id, request_id))
        return {"user_id": user_id, "request_id": request_id, "token": token, "state": state, "attempts": attempts}


def _save_claim(lease: dict) -> None:
    with db() as conn:
        conn.execute("UPDATE generation_requests SET result_json = ? WHERE user_id = ? AND request_id = ? "
                     "AND instance_id = ? AND status = 'running'",
                     (_encode(lease["state"], lease["attempts"]), lease["user_id"], lease["request_id"], lease["token"]))


def _complete(lease: dict, result: dict | None, error: dict | None = None, *, terminal: bool = False) -> None:
    now = int(time.time())
    status = "succeeded" if result is not None else "unknown"
    checkpoint_json = _encode(lease["state"], MAX_RECOVERY_ATTEMPTS if terminal else lease["attempts"],
                              now + min(300, 5 * 2 ** lease["attempts"]))
    with db() as conn:
        conn.execute("UPDATE generation_requests SET status = ?, finished_at = ?, lease_expires_at = 0, "
                     "result_json = ?, error_json = ?, error_status = ? WHERE user_id = ? AND request_id = ? "
                     "AND instance_id = ? AND status IN ('running', 'unknown')",
                     (status, now, json.dumps(result, ensure_ascii=False) if result is not None else checkpoint_json,
                      json.dumps(error or {}, ensure_ascii=False), 0 if result is not None else 502,
                      lease["user_id"], lease["request_id"], lease["token"]))


def _existing_asset(lease: dict) -> dict | None:
    # 文件入库后、请求完成前进程中断时，下一次恢复复用已保存的资产。
    with db() as conn:
        row = conn.execute("SELECT id, byte_size, width, height, expires_at FROM image_assets "
                           "WHERE user_id = ? AND request_id = ? AND expires_at > ? ORDER BY expires_at DESC LIMIT 1",
                           (lease["user_id"], lease["request_id"], int(time.time()))).fetchone()
    if not row:
        return None
    from app.services.image_review import pending
    return {"request_id": lease["request_id"], "asset_id": row["id"],
            "url": f"/api/v1/image-generation/assets/{row['id']}", "mime_type": "image/png",
            "width": row["width"], "height": row["height"], "byte_size": row["byte_size"],
            "expires_at": row["expires_at"], "prompt": lease["state"]["prompt"],
            "quality_review": lease["state"].get("quality_review") or pending("原图已恢复，尚未完成内容检查")}


async def recover(lease: dict) -> None:
    from app.services import image_config
    from app.services.image_assets import persist
    from app.services.image_generation import (
        _image_task_result,
        _normalize_when_available,
        _provider_json,
        _public_image,
        _task_poll_url,
        generation_url,
    )
    from app.services.model_profiles import entries
    from app.services.provider_http import borrow_client
    state = lease["state"]
    stage = "task_query"
    raw = b""
    try:
        async with asyncio.timeout(RECOVERY_SECONDS):
            existing = await run_sync(_existing_asset, lease)
            if existing is not None:
                await run_sync(_complete, lease, existing)
                return
            if not state.get("asset_url"):
                candidates = entries(await run_sync(image_config.get_config, True))
                config = next((p for p in candidates if p.get("id") == state.get("profile_id")
                               and generation_url(p["baseUrl"]) == state["endpoint"] and p["model"] == state["model"]), None)
                if config is None or not config.get("api_key"):
                    raise HTTPException(409, detail={"error": "原生图模型配置已变更，无法自动查询原任务，请联系管理员"})
                task_id, poll_url = _task_poll_url(state["task"], state["endpoint"])
                async with borrow_client("image-generation", 20, base_url=state["endpoint"]) as client:
                    data = await _provider_json(client, "GET", poll_url, {"Authorization": "Bearer " + config["api_key"]})
                result_data = _image_task_result(data, task_id)
                if result_data is None:
                    raise HTTPException(409, detail={"code": "image_task_pending", "error": "原生图任务仍在处理中，将继续查询原任务"})
                item = result_data["data"][0]
                if item.get("b64_json"):
                    import base64
                    raw = await run_sync_in("media", base64.b64decode, item["b64_json"], validate=True)
                else:
                    state["asset_url"] = item["url"]
                    await run_sync(_save_claim, lease)
            if state.get("asset_url"):
                stage = "asset_download"
                logger.info("恢复原生图成品（域名 %s）", urlsplit(state["asset_url"]).hostname)
                raw = await _public_image(state["asset_url"])
            stage = "image_processing"
            image = await _normalize_when_available(raw)
            from app.services.image_review import pending
            result = await run_sync(persist, lease["user_id"], lease["request_id"],
                                    {**image, "prompt": state["prompt"], "quality_review": pending("原图已恢复，尚未完成内容检查")})
            await run_sync(_complete, lease, {**result, "request_id": lease["request_id"]})
            logger.info("原生图结果恢复成功")
    except (Exception, asyncio.CancelledError) as exc:
        detail: dict = exc.detail if isinstance(exc, HTTPException) and isinstance(exc.detail, dict) else {}
        terminal = detail.get("code") == "image_task_failed" or (isinstance(exc, HTTPException) and exc.status_code == 409
                                                                 and detail.get("code") != "image_task_pending")
        error = {"code": "image_recovery_pending", "failover_safe": False, "request_id": lease["request_id"],
                 "error": detail.get("error") or "原图片结果暂时未取回，已保留原任务继续查询；重新生成可能产生新的费用"}
        if lease["attempts"] >= MAX_RECOVERY_ATTEMPTS:
            error["error"] = "原图片自动恢复次数已用完，请联系管理员检查原任务；重新生成可能产生新的费用"
        logger.warning("原生图结果恢复未完成（阶段 %s，异常 %s）", stage, type(exc).__name__)
        await run_sync(_complete, lease, None, error, terminal=terminal)
        if isinstance(exc, asyncio.CancelledError):
            raise


async def schedule(user_id: int, request_id: str) -> None:
    lease = await run_sync(_claim, user_id, request_id)
    if lease is not None:
        task = asyncio.create_task(recover(lease))
        _tasks.add(task)
        task.add_done_callback(_done)


def _done(task: asyncio.Task) -> None:
    _tasks.discard(task)
    if not task.cancelled() and task.exception() is not None:
        logger.warning("原生图恢复任务中断（%s）", type(task.exception()).__name__)


async def shutdown() -> None:
    tasks = list(_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
