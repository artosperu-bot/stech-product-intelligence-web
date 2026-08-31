from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class ChatGPTUsageLimitState:
    message: str
    reset_hint: str = ""
    suggests_new_chat: bool = False


class ChatGPTUsageLimitError(RuntimeError):
    def __init__(self, message: str, reset_hint: str = "", suggests_new_chat: bool = False):
        self.message = str(message or "ChatGPT temporalmente limitado").strip()
        self.reset_hint = str(reset_hint or "").strip()
        self.suggests_new_chat = bool(suggests_new_chat)
        detail = f"CHATGPT_USAGE_LIMIT: {self.message}"
        if self.reset_hint:
            detail += f"; reset={self.reset_hint}"
        if self.suggests_new_chat:
            detail += "; new_chat_available=true"
        super().__init__(detail)


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def detect_chatgpt_usage_limit_text(text: str) -> ChatGPTUsageLimitState | None:
    raw = " ".join(str(text or "").split())
    if not raw:
        return None
    normalized = _normalize(raw)

    strong_markers = (
        "chat en pausa",
        "has alcanzado el limite de chats",
        "se restablezca el uso",
        "limite de chats que incluyen analisis de datos",
        "chat paused",
        "you've reached the limit",
        "you have reached the limit",
        "usage resets",
        "limit for chats with data analysis",
    )
    if not any(marker in normalized for marker in strong_markers):
        return None

    reset_hint = ""
    match = re.search(
        r"(?i)(?:a\s+las|hasta\s+las|at)\s+([0-2]?\d:[0-5]\d(?:\s*[ap]\.?m\.?)?)",
        raw,
    )
    if match:
        reset_hint = match.group(1).strip()

    suggests_new_chat = any(
        marker in normalized
        for marker in (
            "nuevo chat",
            "inicia un chat nuevo",
            "new chat",
            "start a new chat",
        )
    )
    return ChatGPTUsageLimitState(
        message=raw[:700],
        reset_hint=reset_hint,
        suggests_new_chat=suggests_new_chat,
    )


async def detect_chatgpt_usage_limit(page) -> ChatGPTUsageLimitState | None:
    try:
        body = page.locator("body")
        if await body.count() < 1:
            return None
        text = await body.first.inner_text(timeout=2500)
    except Exception:
        return None
    return detect_chatgpt_usage_limit_text(text)


async def raise_if_chatgpt_usage_limited(page) -> None:
    state = await detect_chatgpt_usage_limit(page)
    if state is None:
        return
    raise ChatGPTUsageLimitError(
        state.message,
        reset_hint=state.reset_hint,
        suggests_new_chat=state.suggests_new_chat,
    )
