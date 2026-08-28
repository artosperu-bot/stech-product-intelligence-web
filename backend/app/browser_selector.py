from __future__ import annotations

import os

from .cloud_browser import CloudChatGPTBrowserSession
from .remote_browser import RemoteChatGPTBrowserSession


def chatgpt_session(progress=None, research_kind: str | None = None):
    mode = os.getenv("STECH_CHATGPT_MODE", "server").strip().casefold()
    if mode in {"remote", "worker", "windows"}:
        return RemoteChatGPTBrowserSession(progress=progress, research_kind=research_kind)
    return CloudChatGPTBrowserSession(progress=progress)
