from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class _PendingTask:
    task_id: str
    args: list[Any]
    kwargs: dict[str, Any]
    future: asyncio.Future
    created_monotonic: float
    claimed_by: str | None = None


class ResearchBroker:
    """In-memory request/reply bridge between Render and one Windows research worker."""

    def __init__(self, worker_ttl_seconds: int = 45):
        self.worker_ttl_seconds = max(5, int(worker_ttl_seconds))
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._tasks: dict[str, _PendingTask] = {}
        self._lock = asyncio.Lock()
        self._worker_id: str | None = None
        self._worker_seen_monotonic: float | None = None

    async def heartbeat(self, worker_id: str) -> None:
        async with self._lock:
            self._worker_id = str(worker_id)
            self._worker_seen_monotonic = time.monotonic()

    async def status(self) -> dict[str, Any]:
        async with self._lock:
            seen = self._worker_seen_monotonic
            worker_id = self._worker_id
            pending = sum(1 for task in self._tasks.values() if not task.future.done())
        age = None if seen is None else max(0.0, time.monotonic() - seen)
        return {
            "online": bool(age is not None and age <= self.worker_ttl_seconds),
            "worker_id": worker_id,
            "last_seen_seconds": age,
            "pending": pending,
        }

    async def submit(self, args: list[Any], kwargs: dict[str, Any], timeout_seconds: float = 240) -> Any:
        json.dumps({"args": args, "kwargs": kwargs})
        loop = asyncio.get_running_loop()
        task_id = uuid.uuid4().hex
        future = loop.create_future()
        pending = _PendingTask(task_id, list(args), dict(kwargs), future, time.monotonic())
        async with self._lock:
            self._tasks[task_id] = pending
        await self._queue.put(task_id)
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=max(1.0, float(timeout_seconds)))
        except asyncio.TimeoutError as exc:
            if not future.done():
                future.cancel()
            raise TimeoutError(f"RESEARCH_WORKER_TIMEOUT task={task_id}") from exc
        finally:
            async with self._lock:
                self._tasks.pop(task_id, None)

    async def claim(self, worker_id: str, wait_seconds: float = 20) -> dict[str, Any] | None:
        await self.heartbeat(worker_id)
        deadline = time.monotonic() + max(0.0, float(wait_seconds))
        while True:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                task_id = await asyncio.wait_for(self._queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                return None
            async with self._lock:
                task = self._tasks.get(task_id)
                if task is None or task.future.done():
                    task = None
                else:
                    task.claimed_by = str(worker_id)
            if task is not None:
                return {"task_id": task.task_id, "args": task.args, "kwargs": task.kwargs}
            if time.monotonic() >= deadline:
                return None

    async def complete(self, task_id: str, result: Any, worker_id: str) -> None:
        await self.heartbeat(worker_id)
        async with self._lock:
            task = self._tasks.get(str(task_id))
            if task is None:
                raise KeyError(task_id)
            if task.claimed_by and task.claimed_by != str(worker_id):
                raise PermissionError("WORKER_TASK_OWNER_MISMATCH")
            if not task.future.done():
                task.future.set_result(result)

    async def fail(self, task_id: str, message: str, worker_id: str) -> None:
        await self.heartbeat(worker_id)
        async with self._lock:
            task = self._tasks.get(str(task_id))
            if task is None:
                raise KeyError(task_id)
            if task.claimed_by and task.claimed_by != str(worker_id):
                raise PermissionError("WORKER_TASK_OWNER_MISMATCH")
            if not task.future.done():
                task.future.set_exception(RuntimeError(str(message)))


BROKER = ResearchBroker()
