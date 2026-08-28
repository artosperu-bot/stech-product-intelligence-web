from __future__ import annotations

import os

from .cloud_browser import CloudChatGPTBrowserSession
from .remote_browser import RemoteChatGPTBrowserSession


def chatgpt_session(progress=None):
    mode = os.getenv("STECH_CHATGPT_MODE", "server").strip().casefold()
    if mode in {"remote", "worker", "windows"}:
        return RemoteChatGPTBrowserSession(progress=progress)
    return CloudChatGPTBrowserSession(progress=progress)
