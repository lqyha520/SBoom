"""有界、脱敏的单次生成追踪；沿用生成请求的保留期与账号隔离。"""

import json
import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass, field

from app.blocking import run_sync
from app.db import db

logger = logging.getLogger(__name__)


@dataclass
class GenerationTrace:
    user_id: int
    request_id: str
    instance_id: str
    revision: str
    started: float = field(default_factory=time.monotonic)
    phase: str = "preparing"
    stages: list[dict] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)
    rejections: list[dict] = field(default_factory=list)
    progress: dict = field(default_factory=dict)

    def snapshot(self) -> dict:
        return {"version": 1, "source": "model", "revision": self.revision,
                "phase": self.phase, "elapsed_ms": round((time.monotonic() - self.started) * 1000),
                "stages": self.stages, "calls": self.calls, "rejections": self.rejections,
                "progress": self.progress}


current_trace: ContextVar[GenerationTrace | None] = ContextVar("generation_trace", default=None)
current_call: ContextVar[dict | None] = ContextVar("generation_trace_call", default=None)


def attempt(model: str) -> None:
    trace, operation = current_trace.get(), current_call.get()
    if trace is None or len(trace.calls) >= 64:
        return
    call = {"model": model[:120], "stage": trace.phase, "status": "running",
            "started_ms": round((time.monotonic() - trace.started) * 1000),
            "prompt_tokens": None, "completion_tokens": None}
    trace.calls.append(call)
    if operation is not None:
        operation["calls"].append(call)


def tokens(prompt: int, completion: int) -> None:
    operation = current_call.get()
    if operation and operation["calls"]:
        operation["calls"][-1].update(prompt_tokens=prompt, completion_tokens=completion)


def begin_call():
    return current_call.set({"calls": [], "started": time.monotonic()})


def end_call(token, status: str) -> None:
    operation = current_call.get()
    if operation:
        trace = current_trace.get()
        elapsed = round((time.monotonic() - trace.started) * 1000) if trace else 0
        for index, call in enumerate(operation["calls"]):
            # 同一 provider 操作内部重试时，前一次结束于下一次尝试。
            following = operation["calls"][index + 1: index + 2]
            call.update(status="retried" if following else status,
                        duration_ms=max(0, (following[0]["started_ms"] if following else elapsed) - call["started_ms"]))
    current_call.reset(token)


def rejected(stage: str, reason: str, count: int = 1) -> None:
    trace = current_trace.get()
    if trace is not None and len(trace.rejections) < 40:
        trace.rejections.append({"stage": stage, "reason": reason[:300], "count": count})


def persist(trace: GenerationTrace) -> None:
    with db() as conn:
        conn.execute("UPDATE generation_requests SET trace_json = ? WHERE user_id = ? AND request_id = ? "
                     "AND instance_id = ? AND status = 'running'",
                     (json.dumps(trace.snapshot(), ensure_ascii=False), trace.user_id, trace.request_id, trace.instance_id))


async def flush() -> None:
    trace = current_trace.get()
    if trace is not None:
        try:
            await run_sync(persist, trace)
        except Exception:
            # 观测写入失败不能触发二次付费或丢弃已生成的题目。
            logger.warning("生成追踪暂时无法保存", exc_info=False)


async def progress(batch: int, total: int, completed: int) -> None:
    trace = current_trace.get()
    if trace is not None:
        trace.progress = {"batch": batch, "total_batches": total, "completed_questions": completed}
        await flush()
