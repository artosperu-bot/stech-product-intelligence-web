from __future__ import annotations

import json
import os
import uuid
from typing import Any

from .remote_protocol import encode_remote_value
from .research_broker import BROKER
from .research_prompts import guidance_for
from .result_sanitizer import sanitize_research_result
from .worker_chat_policy import REMOTE_CONTEXT_KWARG


class RemoteChatGPTBrowserSession:
    """ChatGPT session facade whose ask() calls are executed by a trusted Windows worker."""

    def __init__(self, progress=None, research_kind: str | None = None):
        self.progress = progress
        self.research_kind = (research_kind or "").strip().casefold() or None
        self.chat_key = uuid.uuid4().hex
        self._research_responses: list[str] = []

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

    def _guidance(self) -> str:
        turn = len(self._research_responses) + 1
        return guidance_for(self.research_kind, turn)

    def _state_block(self) -> str:
        if not self._research_responses:
            return ""
        payload = {
            "research_kind": self.research_kind,
            "completed_turns": len(self._research_responses),
            "previous_responses": self._research_responses,
        }
        return (
            "STECH_RESEARCH_STATE\n"
            "Este estado viene de respuestas anteriores del MISMO trabajo/producto. Úsalo como memoria explícita y respaldo si hubo retry.\n"
            "No cambies el contrato JSON del prompt original y no repitas investigación ya resuelta salvo para validar/mejorar evidencia.\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )

    def _augment_args(self, args: tuple[Any, ...]) -> list[Any]:
        wire_args = list(args)
        if not wire_args or not isinstance(wire_args[0], str):
            return wire_args
        blocks = [wire_args[0], self._guidance()]
        state = self._state_block()
        if state:
            blocks.append(state)
        wire_args[0] = "\n\n".join(block for block in blocks if block)
        return wire_args

    def _remember(self, result: Any) -> None:
        max_total = max(4000, int(os.getenv("STECH_RESEARCH_STATE_MAX_CHARS", "22000")))
        max_item = max(2000, max_total // 2)
        if isinstance(result, str):
            text = result
        else:
            try:
                text = json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str)
            except Exception:
                text = str(result)
        if len(text) > max_item:
            text = text[:max_item] + "…[TRUNCATED]"
        self._research_responses.append(text)
        while len(self._research_responses) > 1 and sum(len(item) for item in self._research_responses) > max_total:
            self._research_responses.pop(0)
        if sum(len(item) for item in self._research_responses) > max_total:
            self._research_responses[-1] = self._research_responses[-1][:max_total] + "…[TRUNCATED]"

    async def ask(self, *args, **kwargs):
        timeout = float(os.getenv("STECH_RESEARCH_WORKER_TASK_TIMEOUT", "720"))
        turn = len(self._research_responses) + 1
        self._note("Enviando consulta de ChatGPT al Chrome real del worker...")
        augmented_args = self._augment_args(args)
        wire_args = encode_remote_value(augmented_args)
        wire_kwargs_raw = dict(kwargs)
        wire_kwargs_raw[REMOTE_CONTEXT_KWARG] = {
            "chat_key": self.chat_key,
            "research_kind": self.research_kind or "research",
            "turn": turn,
        }
        wire_kwargs = encode_remote_value(wire_kwargs_raw)
        result = await BROKER.submit(wire_args, wire_kwargs, timeout_seconds=timeout)
        result = sanitize_research_result(result)
        self._remember(result)
        self._note("Respuesta de ChatGPT recibida desde el worker Windows.")
        return result
