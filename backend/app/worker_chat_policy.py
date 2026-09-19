from __future__ import annotations

import asyncio
import os

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


async def _composer_state(locator) -> dict:
    """Return DOM state without triggering Playwright actionability checks."""
    state = await locator.evaluate(
        """
        el => {
          const rect = el.getBoundingClientRect();
          const cx = rect.left + rect.width / 2;
          const cy = rect.top + rect.height / 2;
          const hit = rect.width > 0 && rect.height > 0
            ? document.elementFromPoint(cx, cy)
            : null;
          return {
            connected: !!el.isConnected,
            id: el.id || '',
            role: el.getAttribute('role') || '',
            contenteditable: el.getAttribute('contenteditable') || '',
            ariaHidden: el.getAttribute('aria-hidden') || '',
            rect: [rect.x, rect.y, rect.width, rect.height],
            hitInside: !!hit && (hit === el || el.contains(hit)),
          };
        }
        """
    )
    return state if isinstance(state, dict) else {}


def _rect_stable(previous, current, tolerance: float = 0.75) -> bool:
    if not previous or not current or len(previous) != 4 or len(current) != 4:
        return True
    try:
        return all(abs(float(a) - float(b)) <= tolerance for a, b in zip(previous, current))
    except Exception:
        return False


async def ensure_chatgpt_composer_alias(page) -> dict:
    """Expose the current visible ChatGPT composer through the legacy #prompt-textarea id.

    ChatGPT changes the editor DOM periodically. The V30 browser core still expects
    #prompt-textarea, so the Windows worker installs a tiny compatibility shim that
    locates the best visible editable candidate and aliases it with that id. A
    MutationObserver reapplies the alias when React replaces the composer node.
    """
    try:
        result = await page.evaluate(
            r"""() => {
              const isVisibleEditable = (el) => {
                if (!el || !el.isConnected) return false;
                const rect = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                if (rect.width < 80 || rect.height < 18) return false;
                if (style.display === 'none' || style.visibility === 'hidden') return false;
                if (el.getAttribute('aria-hidden') === 'true') return false;
                if (el.matches('textarea, input')) {
                  return !el.disabled && !el.readOnly;
                }
                return el.getAttribute('contenteditable') === 'true';
              };

              const score = (el) => {
                const rect = el.getBoundingClientRect();
                const vh = Math.max(window.innerHeight || 0, 1);
                const vw = Math.max(window.innerWidth || 0, 1);
                const attrs = [
                  el.id,
                  el.getAttribute('role'),
                  el.getAttribute('aria-label'),
                  el.getAttribute('placeholder'),
                  el.getAttribute('data-placeholder'),
                  el.getAttribute('name'),
                  el.className,
                ].filter(Boolean).join(' ').toLowerCase();

                let points = 0;
                if (el.id === 'prompt-textarea') points += 1000;
                if (el.getAttribute('contenteditable') === 'true') points += 260;
                if (el.getAttribute('role') === 'textbox') points += 180;
                if (/message|mensaje|chatgpt|prompt|ask|pregunta|enviar/.test(attrs)) points += 260;
                if (el.closest('form')) points += 100;
                if (rect.width > 250) points += 80;
                if (rect.width > vw * 0.35) points += 60;
                if (rect.top > vh * 0.40) points += 120;
                if (rect.bottom > vh * 0.62) points += 100;
                if (el.matches('textarea')) points += 40;
                if (/search|buscar/.test(attrs)) points -= 500;
                if (el.closest('aside, nav, [role="navigation"]')) points -= 350;
                return points;
              };

              const findBest = () => {
                const selectors = [
                  '#prompt-textarea',
                  '[contenteditable="true"][role="textbox"]',
                  '[contenteditable="true"][data-placeholder]',
                  '.ProseMirror[contenteditable="true"]',
                  'div[contenteditable="true"]',
                  'textarea[name="prompt-textarea"]',
                  'textarea[placeholder]',
                  'textarea'
                ];
                const seen = new Set();
                const candidates = [];
                for (const selector of selectors) {
                  for (const el of document.querySelectorAll(selector)) {
                    if (seen.has(el)) continue;
                    seen.add(el);
                    if (isVisibleEditable(el)) candidates.push(el);
                  }
                }
                candidates.sort((a, b) => score(b) - score(a));
                return candidates[0] || null;
              };

              const alias = () => {
                const best = findBest();
                if (!best) {
                  return {ok:false, candidates:0};
                }

                for (const old of document.querySelectorAll('#prompt-textarea')) {
                  if (old !== best) old.removeAttribute('id');
                }
                best.id = 'prompt-textarea';
                if (!best.getAttribute('role')) best.setAttribute('role', 'textbox');
                best.setAttribute('data-stech-composer-active', '1');

                const rect = best.getBoundingClientRect();
                return {
                  ok: true,
                  tag: best.tagName,
                  role: best.getAttribute('role') || '',
                  contenteditable: best.getAttribute('contenteditable') || '',
                  placeholder: best.getAttribute('placeholder') || best.getAttribute('data-placeholder') || '',
                  rect: [rect.x, rect.y, rect.width, rect.height],
                  score: score(best),
                };
              };

              window.__stechEnsureComposer = alias;
              if (!window.__stechComposerObserver) {
                let queued = false;
                window.__stechComposerObserver = new MutationObserver(() => {
                  if (queued) return;
                  queued = true;
                  queueMicrotask(() => {
                    queued = false;
                    try { alias(); } catch (_) {}
                  });
                });
                window.__stechComposerObserver.observe(document.documentElement, {
                  childList: true,
                  subtree: true,
                });
              }
              return alias();
            }"""
        )
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


async def prepare_chatgpt_composer(
    page,
    timeout_seconds: float | None = None,
    poll_seconds: float = 0.2,
    stable_checks: int = 3,
):
    """Wait for the real ChatGPT composer to survive hydration and become usable.

    This intentionally avoids click()/trial-click as a readiness probe. ChatGPT can
    expose the correct ProseMirror editor while React is still moving/replacing it;
    Playwright then reports the element as not stable even though identity, visibility
    and editability are already correct. Instead we require the same DOM node marker,
    accessible textbox identity, visibility/editability and stable geometry for several
    consecutive samples. Fallback textareas are removed from the accessibility tree.
    """
    loop = asyncio.get_running_loop()
    if timeout_seconds is None:
        timeout_seconds = float(os.getenv("STECH_CHATGPT_COMPOSER_TIMEOUT_SECONDS", "180"))
    deadline = loop.time() + max(0.1, float(timeout_seconds))
    poll = max(0.01, float(poll_seconds))
    required_stable = max(1, int(stable_checks))
    last_error = "composer real no encontrado"
    probe_serial = 0

    while loop.time() < deadline:
        try:
            compat = await ensure_chatgpt_composer_alias(page)
            real_locators = page.locator(REAL_COMPOSER_SELECTOR)
            real_count = await real_locators.count()
            if real_count < 1:
                detail = f"; compat={compat}" if compat else ""
                last_error = f"compositor visible no localizado todavía{detail}"
                await asyncio.sleep(poll)
                continue

            candidate = real_locators.nth(real_count - 1)
            if not await candidate.is_visible():
                last_error = "#prompt-textarea todavía no visible"
                await asyncio.sleep(poll)
                continue
            if not await candidate.is_editable():
                last_error = "#prompt-textarea todavía no editable"
                await asyncio.sleep(poll)
                continue

            state = await _composer_state(candidate)
            if not state.get("connected", True):
                last_error = "#prompt-textarea fue desconectado durante hidratación"
                await asyncio.sleep(poll)
                continue
            if state.get("id") not in (None, "", "prompt-textarea"):
                last_error = f"composer inesperado id={state.get('id')}"
                await asyncio.sleep(poll)
                continue
            if str(state.get("ariaHidden") or "").casefold() == "true":
                last_error = "#prompt-textarea está aria-hidden"
                await asyncio.sleep(poll)
                continue

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

            legacy_textbox = page.get_by_role("textbox").first
            if not await legacy_textbox.is_visible():
                last_error = "textbox accesible todavía no visible"
                await asyncio.sleep(poll)
                continue
            if not await legacy_textbox.is_editable():
                last_error = "textbox accesible todavía no editable"
                await asyncio.sleep(poll)
                continue
            legacy_state = await _composer_state(legacy_textbox)
            if legacy_state.get("id") != "prompt-textarea":
                last_error = f"textbox accesible aún apunta a otro nodo id={legacy_state.get('id') or '-'}"
                await asyncio.sleep(poll)
                continue

            probe_serial += 1
            probe_token = f"stech-composer-{probe_serial}"
            await candidate.evaluate(
                "(el, token) => { el.setAttribute('data-stech-composer-probe', token); return true; }",
                probe_token,
            )

            previous_rect = state.get("rect")
            stable_count = 0
            stable_candidate = candidate

            while stable_count < required_stable and loop.time() < deadline:
                await asyncio.sleep(poll)
                current_locators = page.locator(REAL_COMPOSER_SELECTOR)
                current_count = await current_locators.count()
                if current_count < 1:
                    last_error = "React retiró #prompt-textarea durante hidratación"
                    break
                current = current_locators.nth(current_count - 1)
                if await current.get_attribute("data-stech-composer-probe") != probe_token:
                    last_error = "React reemplazó el nodo #prompt-textarea durante hidratación"
                    break
                if not await current.is_visible() or not await current.is_editable():
                    last_error = "#prompt-textarea cambió de visibilidad/editabilidad durante hidratación"
                    break

                current_state = await _composer_state(current)
                if not current_state.get("connected", True):
                    last_error = "#prompt-textarea se desconectó durante estabilización"
                    break
                if current_state.get("id") != "prompt-textarea":
                    last_error = "#prompt-textarea cambió de identidad durante estabilización"
                    break
                if current_state.get("hitInside") is False:
                    last_error = "#prompt-textarea todavía está cubierto por otra capa"
                    stable_count = 0
                    previous_rect = current_state.get("rect")
                    continue

                current_legacy = page.get_by_role("textbox").first
                if not await current_legacy.is_visible() or not await current_legacy.is_editable():
                    last_error = "textbox accesible perdió visibilidad/editabilidad"
                    stable_count = 0
                    previous_rect = current_state.get("rect")
                    continue
                current_legacy_state = await _composer_state(current_legacy)
                if current_legacy_state.get("id") != "prompt-textarea":
                    last_error = "textbox accesible cambió a otro nodo durante hidratación"
                    break

                current_rect = current_state.get("rect")
                if _rect_stable(previous_rect, current_rect):
                    stable_count += 1
                else:
                    last_error = "#prompt-textarea todavía está cambiando de geometría"
                    stable_count = 0
                previous_rect = current_rect
                stable_candidate = current

            if stable_count >= required_stable:
                try:
                    await stable_candidate.evaluate(
                        "el => { el.removeAttribute('data-stech-composer-probe'); return true; }"
                    )
                except Exception:
                    pass
                return stable_candidate

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        await asyncio.sleep(poll)

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
                timeout_ms = int(os.getenv("STECH_CHATGPT_NAV_TIMEOUT_MS", "120000"))
                await page.goto(known_url, wait_until="commit", timeout=timeout_ms)
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=30000)
                except Exception:
                    pass
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
