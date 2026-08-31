from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

import httpx


_RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


def _is_retryable_registration_error(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS_CODES
    return False


async def register_worker_with_retry(
    client,
    server: str,
    worker_id: str,
    *,
    retry_delay_seconds: float = 5.0,
    heartbeat_timeout_seconds: float = 60.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    log: Callable[[str], None] | None = None,
):
    """Register a Windows research worker and survive transient Render/network failures.

    Authentication/configuration failures remain fatal; timeouts, network failures and
    transient gateway/server statuses are retried indefinitely because those conditions
    can recover without restarting Chrome or the worker process.
    """
    server = str(server or "").rstrip("/")
    delay = max(0.1, float(retry_delay_seconds))
    timeout = max(5.0, float(heartbeat_timeout_seconds))

    while True:
        try:
            response = await client.post(
                f"{server}/api/research-worker/heartbeat",
                json={"worker_id": worker_id},
                timeout=timeout,
            )
            response.raise_for_status()
            return response
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not _is_retryable_registration_error(exc):
                raise
            if log:
                log(
                    f"[WORKER] registro pendiente: {type(exc).__name__}: {exc}; "
                    f"reintento en {delay:g}s"
                )
            await sleep(delay)
