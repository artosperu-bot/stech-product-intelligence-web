from __future__ import annotations

import os

from .research_broker import BROKER


class RemoteChatGPTBrowserSession:
    """ChatGPT session facade whose ask() calls are executed by a trusted Windows worker."""

    def __init__(self, progress=None):
        self.progress = progress

    def _note(self, message: str) -> None:
        if self.progress:
            self.progress(message)

    async def __aenter__(self):
        status = await BROKER.status()
        if not status.get("online"):
            raise RuntimeError(
                "RESEARCH_WORKER_OFFLINE: inicia STECH Research Worker en la PC con Chrome antes de buscar."
            )
        self._note(f"Worker Windows conectado: {status.get('worker_id') or 'STECH-PC'}.")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def ask(self, *args, **kwargs):
        timeout = float(os.getenv("STECH_RESEARCH_WORKER_TASK_TIMEOUT", "360"))
        self._note("Enviando consulta de ChatGPT al Chrome real del worker...")
        result = await BROKER.submit(list(args), dict(kwargs), timeout_seconds=timeout)
        self._note("Respuesta de ChatGPT recibida desde el worker Windows.")
        return result
