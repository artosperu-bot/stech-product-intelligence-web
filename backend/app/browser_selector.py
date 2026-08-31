from __future__ import annotations

import os

from .cloud_browser import CloudChatGPTBrowserSession
from .remote_browser import RemoteChatGPTBrowserSession


class PromptContextSession:
    """Append deterministic per-product context to every text prompt sent by a session."""

    def __init__(self, inner, prompt_context: str = ''):
        self.inner = inner
        self.prompt_context = str(prompt_context or '').strip()

    async def __aenter__(self):
        await self.inner.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return await self.inner.__aexit__(exc_type, exc, tb)

    async def ask(self, *args, **kwargs):
        if not self.prompt_context or not args or not isinstance(args[0], str):
            return await self.inner.ask(*args, **kwargs)
        merged = list(args)
        merged[0] = f"{merged[0]}\n\n{self.prompt_context}"
        return await self.inner.ask(*merged, **kwargs)


def chatgpt_session(
    progress=None,
    research_kind: str | None = None,
    prompt_context: str | None = None,
):
    mode = os.getenv("STECH_CHATGPT_MODE", "server").strip().casefold()
    if mode in {"remote", "worker", "windows"}:
        session = RemoteChatGPTBrowserSession(progress=progress, research_kind=research_kind)
    else:
        session = CloudChatGPTBrowserSession(progress=progress)
    if str(prompt_context or '').strip():
        return PromptContextSession(session, str(prompt_context))
    return session
