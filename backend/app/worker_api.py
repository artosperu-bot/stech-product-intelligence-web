from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, Field

from .research_broker import BROKER

router = APIRouter(prefix="/api/research-worker", tags=["research-worker"])


class WorkerIdentity(BaseModel):
    worker_id: str = Field(min_length=1, max_length=120)


class WorkerClaim(WorkerIdentity):
    wait_seconds: float = Field(default=20.0, ge=0.0, le=25.0)


class WorkerResult(WorkerIdentity):
    result: Any


class WorkerFailure(WorkerIdentity):
    message: str = Field(min_length=1, max_length=4000)


def _require_worker_token(authorization: str | None) -> None:
    expected = os.getenv("STECH_RESEARCH_WORKER_TOKEN", "").strip()
    if not expected:
        raise HTTPException(503, "STECH_RESEARCH_WORKER_TOKEN no configurado en Render.")
    prefix = "Bearer "
    supplied = authorization[len(prefix):].strip() if authorization and authorization.startswith(prefix) else ""
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, "RESEARCH_WORKER_UNAUTHORIZED")


@router.get("/status")
async def worker_status():
    status = await BROKER.status()
    status["configured"] = bool(os.getenv("STECH_RESEARCH_WORKER_TOKEN", "").strip())
    return status


@router.post("/heartbeat")
async def worker_heartbeat(body: WorkerIdentity, authorization: str | None = Header(default=None)):
    _require_worker_token(authorization)
    await BROKER.heartbeat(body.worker_id)
    return {"ok": True, "worker_id": body.worker_id}


@router.post("/claim")
async def worker_claim(body: WorkerClaim, authorization: str | None = Header(default=None)):
    _require_worker_token(authorization)
    task = await BROKER.claim(body.worker_id, wait_seconds=body.wait_seconds)
    if task is None:
        return Response(status_code=204)
    return task


@router.post("/tasks/{task_id}/complete")
async def worker_complete(task_id: str, body: WorkerResult, authorization: str | None = Header(default=None)):
    _require_worker_token(authorization)
    try:
        await BROKER.complete(task_id, body.result, body.worker_id)
    except KeyError:
        raise HTTPException(404, "RESEARCH_TASK_NOT_FOUND")
    except PermissionError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}


@router.post("/tasks/{task_id}/fail")
async def worker_fail(task_id: str, body: WorkerFailure, authorization: str | None = Header(default=None)):
    _require_worker_token(authorization)
    try:
        await BROKER.fail(task_id, body.message, body.worker_id)
    except KeyError:
        raise HTTPException(404, "RESEARCH_TASK_NOT_FOUND")
    except PermissionError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}
