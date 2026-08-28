from __future__ import annotations

REMOTE_CONTEXT_KWARG = "__stech_remote_context__"


def composer_has_unsent_prompt(expected_prompt: str, composer_text: str) -> bool:
    expected = " ".join(str(expected_prompt or "").split())
    composer = " ".join(str(composer_text or "").split())
    if not expected or not composer:
        return False
    if len(composer) < max(40, int(len(expected) * 0.8)):
        return False
    probe = expected[: min(160, len(expected))]
    return probe in composer


def pop_remote_context(kwargs: dict) -> dict:
    raw = kwargs.pop(REMOTE_CONTEXT_KWARG, {})
    return raw if isinstance(raw, dict) else {}


class WorkerChatRouter:
    """Route multiple remote ask() calls from one research job to one ChatGPT conversation."""

    def __init__(self):
        self._conversation_urls: dict[str, str] = {}
        self._active_key: str | None = None

    async def prepare(self, chat_key: str | None, session, open_new, recover):
        key = str(chat_key or "").strip()
        if not key:
            return await open_new(session)

        if self._active_key == key:
            return await recover(session)

        known_url = self._conversation_urls.get(key)
        if known_url:
            page = await recover(session)
            if (getattr(page, "url", "") or "") != known_url:
                await page.goto(known_url, wait_until="domcontentloaded", timeout=60000)
            session.page = page
            self._active_key = key
            return page

        page = await open_new(session)
        self._active_key = key
        return page

    def remember(self, chat_key: str | None, session) -> None:
        key = str(chat_key or "").strip()
        if not key:
            return
        self._active_key = key
        page = getattr(session, "page", None)
        url = str(getattr(page, "url", "") or "").strip()
        if url.startswith("https://chatgpt.com/") and url.rstrip("/") != "https://chatgpt.com":
            self._conversation_urls[key] = url

    def reset(self, chat_key: str | None) -> None:
        key = str(chat_key or "").strip()
        if not key:
            return
        self._conversation_urls.pop(key, None)
        if self._active_key == key:
            self._active_key = None
