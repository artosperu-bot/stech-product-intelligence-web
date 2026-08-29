from __future__ import annotations

import asyncio

REMOTE_CONTEXT_KWARG = "__stech_remote_context__"
REAL_COMPOSER_SELECTOR = "#prompt-textarea"
FALLBACK_COMPOSER_SELECTOR = (
    "textarea.wcDTda_fallbackTextarea, "
    "textarea[name='prompt-textarea']:not(#prompt-textarea)"
)


def composer_has_unsent_prompt(expected_prompt: str, composer_text: str) -> bool:
    expected = " ".join(str(expected_prompt or "").split())
    composer = " ".join(str(composer_text or "").split())
    if not expected or not composer:
        return False
    if len(composer) < max(40, int(len(expected) * 0.8)):
        return False
    probe = expected[: min(160, len(expected))]
    return probe in composer


async def prepare_chatgpt_composer(
    page,
    timeout_seconds: float = 30.0,
    poll_seconds: float = 0.2,
):
    """Wait until ChatGPT's real composer is actionable for the legacy browser code.

    ChatGPT can briefly expose a fallback textarea while React hydrates. The legacy
    browser selects the first accessible textbox, so a hidden fallback can win the
    lookup even after the real #prompt-textarea exists. Once the real composer is
    visible/editable/actionable, hide fallback textareas from the accessibility tree
    and verify the first textbox lookup is also actionable before returning.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(0.1, float(timeout_seconds))
    last_error = "composer real no encontrado"

    while loop.time() < deadline:
        try:
            real_locators = page.locator(REAL_COMPOSER_SELECTOR)
            real_count = await real_locators.count()
            for index in range(real_count - 1, -1, -1):
                candidate = real_locators.nth(index)
                if not await candidate.is_visible():
                    last_error = "#prompt-textarea todavía no visible"
                    continue
                if not await candidate.is_editable():
                    last_error = "#prompt-textarea todavía no editable"
                    continue

                # Trial click checks visibility, stability, enabled state and overlays
                # without mutating focus or sending user input.
                await candidate.click(trial=True, timeout=1500)

                fallbacks = page.locator(FALLBACK_COMPOSER_SELECTOR)
                if await fallbacks.count() > 0:
                    await fallbacks.evaluate_all(
                        """
                        els => els.forEach(el => {
                          el.setAttribute('aria-hidden', 'true');
                          el.setAttribute('tabindex', '-1');
                        })
                        """
                    )

                # The legacy core uses get_by_role('textbox').first. Verify that exact
                # lookup now resolves to an actionable element before handing control
                # back to it.
                legacy_textbox = page.get_by_role("textbox").first
                if not await legacy_textbox.is_visible():
                    last_error = "textbox legacy todavía no visible"
                    continue
                await legacy_textbox.click(trial=True, timeout=1500)
                return candidate
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        await asyncio.sleep(max(0.01, float(poll_seconds)))

    url = str(getattr(page, "url", "") or "")
    raise RuntimeError(
        f"CHATGPT_COMPOSER_NOT_READY: {last_error}; url={url or 'desconocida'}"
    )


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
