from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request

import httpx
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
CORE_DIR = ROOT / "backend" / "legacy_core"
BUNDLE_DIR = ROOT / "legacy_core_bundle_v2"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.chatgpt_dom_capture import extract_json_payload
from app.chatgpt_usage_guard import (
    ChatGPTUsageLimitError,
    detect_chatgpt_usage_limit,
    raise_if_chatgpt_usage_limited,
)
from app.remote_protocol import decode_remote_value
from app.worker_chat_policy import (
    WorkerChatRouter,
    composer_has_unsent_prompt,
    pop_remote_context,
    prepare_chatgpt_composer,
)
from app.worker_runtime import register_worker_with_retry


def ensure_legacy_core() -> None:
    parts = sorted(BUNDLE_DIR.glob("part-*.b64"))
    if not parts:
        raise RuntimeError("No encuentro legacy_core_bundle_v2. Ejecuta el worker desde el repositorio STECH.")

    encoded = "".join(p.read_text(encoding="ascii") for p in parts)
    archive = base64.b64decode(encoded)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tf:
        names = set(tf.getnames())
        if "backend/legacy_core/chatgpt_browser.py" not in names:
            raise RuntimeError("legacy_core_bundle_v2 no contiene backend/legacy_core/chatgpt_browser.py")
        if CORE_DIR.exists():
            shutil.rmtree(CORE_DIR)
        tf.extractall(ROOT, filter="data")

    if not (CORE_DIR / "chatgpt_browser.py").exists():
        raise RuntimeError("legacy_core se extrajo pero falta chatgpt_browser.py")
    print("[CORE] legacy_core sincronizado desde el bundle versionado.", flush=True)


def edge_candidates() -> list[Path]:
    candidates = []
    for key in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.getenv(key)
        if base:
            candidates.append(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    return candidates


def cdp_alive(cdp_url: str) -> bool:
    url = cdp_url.rstrip("/") + "/json/version"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def ensure_edge(cdp_url: str, profile_dir: Path) -> None:
    if cdp_alive(cdp_url):
        print(f"[EDGE] CDP disponible: {cdp_url}")
        return
    edge = next((p for p in edge_candidates() if p.exists()), None)
    if edge is None:
        raise RuntimeError("No encontré Microsoft Edge instalado en Windows.")
    profile_dir.mkdir(parents=True, exist_ok=True)
    parsed_port = cdp_url.rstrip("/").rsplit(":", 1)[-1]
    try:
        port = int(parsed_port)
    except ValueError as exc:
        raise RuntimeError(f"CDP de Edge inválido: {cdp_url}") from exc
    print(f"[EDGE] Iniciando Edge dedicado con perfil: {profile_dir}")
    subprocess.Popen(
        [
            str(edge),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "https://chatgpt.com/",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(60):
        if cdp_alive(cdp_url):
            print(f"[EDGE] CDP listo: {cdp_url}")
            return
        time.sleep(0.5)
    raise RuntimeError(f"Edge abrió pero CDP {port} no respondió.")


def json_safe(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


async def navigate_chatgpt(page, attempts: int = 3):
    """Navigate to ChatGPT without killing the worker on a slow DOMContentLoaded."""
    timeout_ms = int(os.getenv("STECH_CHATGPT_NAV_TIMEOUT_MS", "120000"))
    last_error = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            await page.goto(
                "https://chatgpt.com/",
                wait_until="commit",
                timeout=timeout_ms,
            )
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                # ChatGPT can keep background resources/navigation busy; a committed
                # chatgpt.com page is enough because the composer readiness is checked later.
                pass
            if "chatgpt.com" in (page.url or ""):
                return page
        except Exception as exc:
            last_error = exc
            if "chatgpt.com" in (page.url or ""):
                return page
            if attempt < attempts:
                await asyncio.sleep(min(2.0 * attempt, 5.0))
    raise RuntimeError(
        f"No se pudo abrir ChatGPT en Edge después de {attempts} intentos "
        f"(timeout por intento: {timeout_ms} ms): {type(last_error).__name__}: {last_error}"
    )


async def recover_chatgpt_page(session):
    page = getattr(session, "page", None)
    try:
        if page is not None and not page.is_closed():
            return page
    except Exception:
        pass

    context = getattr(session, "context", None)
    if context is None:
        raise RuntimeError("Edge conectado pero el worker perdió el contexto de navegador.")

    for candidate in list(context.pages):
        try:
            if not candidate.is_closed() and "chatgpt.com" in (candidate.url or ""):
                session.page = candidate
                session._note("Pestaña ChatGPT recuperada desde Edge dedicado.")
                return candidate
        except Exception:
            continue

    page = await context.new_page()
    await navigate_chatgpt(page)
    session.page = page
    session._note("Nueva pestaña ChatGPT creada en Edge dedicado.")
    return page


async def open_fresh_chat(session):
    """Start a clean ChatGPT conversation for a new research job or a retry."""
    page = await recover_chatgpt_page(session)
    try:
        await navigate_chatgpt(page)
    except Exception:
        session.page = None
        page = await recover_chatgpt_page(session)
        await navigate_chatgpt(page)
    session.page = page
    session._note("Nuevo chat de ChatGPT listo para este trabajo de investigación.")
    return page


async def chatgpt_page_diagnostics(page) -> str:
    """Compact diagnostics for slow/login/challenge states without dumping page content."""
    try:
        data = await page.evaluate(
            """() => {
              const body = (document.body?.innerText || '').replace(/\s+/g, ' ').trim();
              const title = document.title || '';
              const editable = [...document.querySelectorAll('[contenteditable="true"], textarea')]
                .filter(el => {
                  const r = el.getBoundingClientRect();
                  const st = getComputedStyle(el);
                  return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none';
                }).length;
              const prompt = document.querySelectorAll('#prompt-textarea').length;
              return { title, prompt, editable, sample: body.slice(0, 280) };
            }"""
        )
        return (
            f"title={data.get('title')!r}; prompt={data.get('prompt')}; "
            f"editables={data.get('editable')}; sample={data.get('sample')!r}"
        )
    except Exception as exc:
        return f"diagnóstico no disponible: {type(exc).__name__}: {exc}"


async def wait_for_chatgpt_ready(session):
    """Wait/recover/reload until the real ChatGPT composer is usable."""
    total_seconds = float(os.getenv("STECH_CHATGPT_READY_TIMEOUT_SECONDS", "180"))
    slice_seconds = float(os.getenv("STECH_CHATGPT_READY_SLICE_SECONDS", "30"))
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(30.0, total_seconds)
    attempt = 0
    last_error = None

    while loop.time() < deadline:
        attempt += 1
        page = await recover_chatgpt_page(session)
        remaining = max(1.0, deadline - loop.time())
        current_slice = min(max(5.0, slice_seconds), remaining)
        try:
            await raise_if_chatgpt_usage_limited(page)
            composer = await prepare_chatgpt_composer(page, timeout_seconds=current_slice)
            session._note(
                f"Compositor de ChatGPT listo (ciclo {attempt}, espera máxima total {int(total_seconds)}s)."
            )
            return composer
        except ChatGPTUsageLimitError:
            raise
        except Exception as exc:
            last_error = exc
            diag = await chatgpt_page_diagnostics(page)
            session._note(
                f"ChatGPT aún no está listo tras {int(current_slice)}s "
                f"(ciclo {attempt}): {diag}"
            )

            if loop.time() >= deadline:
                break

            # Give login/challenge screens time to settle instead of hammering reload.
            diag_cf = diag.casefold()
            challenge_markers = (
                "just a moment", "verify you are human", "verifica que eres humano",
                "checking your browser", "cloudflare", "inicia sesión", "log in", "sign up",
            )
            if any(marker in diag_cf for marker in challenge_markers):
                await asyncio.sleep(min(15.0, max(1.0, deadline - loop.time())))
                continue

            try:
                timeout_ms = int(os.getenv("STECH_CHATGPT_NAV_TIMEOUT_MS", "120000"))
                await page.reload(wait_until="commit", timeout=min(timeout_ms, 60000))
                session._note("ChatGPT seguía sin compositor; página recargada automáticamente.")
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=30000)
                except Exception:
                    pass
            except Exception:
                try:
                    await navigate_chatgpt(page, attempts=1)
                except Exception:
                    session.page = None

            await asyncio.sleep(min(3.0, max(0.5, deadline - loop.time())))

    page = await recover_chatgpt_page(session)
    diag = await chatgpt_page_diagnostics(page)
    raise RuntimeError(
        "CHATGPT_READY_TIMEOUT: el compositor no estuvo disponible dentro de "
        f"{int(total_seconds)}s; último_error={type(last_error).__name__}: {last_error}; {diag}"
    )


async def guard_unsent_prompt(session, expected_prompt: str, delay_seconds: float = 2.5) -> None:
    """Click Send only when the complete prompt is still sitting unsent in the composer."""
    try:
        await asyncio.sleep(max(0.5, float(delay_seconds)))
        page = await recover_chatgpt_page(session)
        await raise_if_chatgpt_usage_limited(page)
        await prepare_chatgpt_composer(page, timeout_seconds=10.0)
        composer = page.locator("#prompt-textarea")
        if await composer.count() < 1:
            return
        text = await composer.first.inner_text(timeout=3000)
        if not composer_has_unsent_prompt(expected_prompt, text):
            return

        await raise_if_chatgpt_usage_limited(page)
        send = page.locator('button[data-testid="send-button"]')
        if await send.count() < 1:
            send = page.locator('button[aria-label*="Enviar"], button[aria-label*="Send"]')
        if await send.count() < 1:
            return
        button = send.first
        if await button.is_visible() and await button.is_enabled():
            session._note("El prompt seguía completo en el compositor; enviándolo automáticamente...")
            await button.click(timeout=5000)
    except asyncio.CancelledError:
        raise
    except ChatGPTUsageLimitError:
        raise
    except Exception:
        return


async def assistant_message_count(session) -> int:
    try:
        page = await recover_chatgpt_page(session)
        return await page.locator('[data-message-author-role="assistant"]').count()
    except Exception:
        return 0


async def watch_chatgpt_usage_limit(session, poll_seconds: float = 0.35) -> None:
    """Run until ChatGPT exposes an account/chat usage gate, then fail explicitly."""
    while True:
        page = await recover_chatgpt_page(session)
        state = await detect_chatgpt_usage_limit(page)
        if state is not None:
            raise ChatGPTUsageLimitError(
                state.message,
                reset_hint=state.reset_hint,
                suggests_new_chat=state.suggests_new_chat,
            )
        await asyncio.sleep(max(0.1, float(poll_seconds)))


async def wait_for_new_assistant_json(
    session,
    baseline_count: int,
    timeout_seconds: float = 240.0,
    stable_seconds: float = 1.2,
):
    """Fallback for multi-turn chats when legacy ask() leaves a finished JSON visible but keeps waiting."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(15.0, float(timeout_seconds))
    last_payload = None
    stable_since = None

    while loop.time() < deadline:
        try:
            page = await recover_chatgpt_page(session)
            await raise_if_chatgpt_usage_limited(page)
            messages = page.locator('[data-message-author-role="assistant"]')
            count = await messages.count()
            if count > baseline_count:
                text = await messages.nth(count - 1).inner_text(timeout=3000)
                payload = extract_json_payload(text)
                if payload:
                    if payload != last_payload:
                        last_payload = payload
                        stable_since = loop.time()
                    elif stable_since is not None and loop.time() - stable_since >= stable_seconds:
                        stop = page.locator(
                            'button[data-testid="stop-button"], '
                            'button[aria-label*="Detener"], button[aria-label*="Stop"]'
                        )
                        stop_visible = False
                        if await stop.count() > 0:
                            try:
                                stop_visible = await stop.first.is_visible()
                            except Exception:
                                stop_visible = False
                        if not stop_visible:
                            return payload
                else:
                    last_payload = None
                    stable_since = None
        except asyncio.CancelledError:
            raise
        except ChatGPTUsageLimitError:
            raise
        except Exception:
            pass
        await asyncio.sleep(0.4)

    return None


async def ask_in_job_chat_retry(
    session,
    args,
    kwargs,
    chat_key: str,
    router: WorkerChatRouter,
    max_attempts: int = 2,
):
    attempts = max(1, int(max_attempts))
    expected_prompt = args[0] if args and isinstance(args[0], str) else ""

    for attempt in range(1, attempts + 1):
        if attempt > 1:
            router.reset(chat_key)

        guard = None
        ask_task = None
        dom_task = None
        usage_task = None
        try:
            page = await router.prepare(chat_key, session, open_fresh_chat, recover_chatgpt_page)
            await raise_if_chatgpt_usage_limited(page)
            await wait_for_chatgpt_ready(session)
            page = await recover_chatgpt_page(session)
            await raise_if_chatgpt_usage_limited(page)
            session._note("Compositor real de ChatGPT estable y listo.")
            baseline_count = await assistant_message_count(session)

            if expected_prompt:
                guard = asyncio.create_task(guard_unsent_prompt(session, expected_prompt))
            ask_task = asyncio.create_task(session.ask(*args, **kwargs))
            dom_task = asyncio.create_task(wait_for_new_assistant_json(session, baseline_count))
            usage_task = asyncio.create_task(watch_chatgpt_usage_limit(session))

            done, _ = await asyncio.wait(
                {ask_task, dom_task, usage_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if usage_task in done:
                await usage_task
                raise RuntimeError("CHATGPT_USAGE_WATCH_UNREACHABLE")
            if ask_task in done:
                result = await ask_task
            else:
                dom_result = await dom_task
                if dom_result is None:
                    result = await ask_task
                else:
                    ask_task.cancel()
                    await asyncio.gather(ask_task, return_exceptions=True)
                    session._note(
                        "JSON final detectado directamente en el DOM; continuando sin esperar al waiter legacy."
                    )
                    result = dom_result

            router.remember(chat_key, session)
            return result
        except Exception as exc:
            classified = exc
            if not isinstance(classified, ChatGPTUsageLimitError):
                try:
                    current_page = await recover_chatgpt_page(session)
                    state = await detect_chatgpt_usage_limit(current_page)
                except Exception:
                    state = None
                if state is not None:
                    classified = ChatGPTUsageLimitError(
                        state.message,
                        reset_hint=state.reset_hint,
                        suggests_new_chat=state.suggests_new_chat,
                    )

            if isinstance(classified, ChatGPTUsageLimitError):
                router.reset(chat_key)
                reset_text = f" hasta {classified.reset_hint}" if classified.reset_hint else ""
                if attempt < attempts and classified.suggests_new_chat:
                    session._note(
                        f"ChatGPT indicó un límite temporal{reset_text}; probando una sola vez en un chat nuevo..."
                    )
                    continue
                raise classified

            if attempt >= attempts:
                raise
            session._note(
                f"La consulta de ChatGPT falló ({type(exc).__name__}); reintentando una vez en un chat nuevo..."
            )
        finally:
            if guard is not None:
                guard.cancel()
                await asyncio.gather(guard, return_exceptions=True)
            if usage_task is not None and not usage_task.done():
                usage_task.cancel()
                await asyncio.gather(usage_task, return_exceptions=True)
            if dom_task is not None and not dom_task.done():
                dom_task.cancel()
                await asyncio.gather(dom_task, return_exceptions=True)
            if ask_task is not None and not ask_task.done():
                ask_task.cancel()
                await asyncio.gather(ask_task, return_exceptions=True)

    raise RuntimeError("CHATGPT_RETRY_UNREACHABLE")


async def load_session_class():
    ensure_legacy_core()
    if str(CORE_DIR) not in sys.path:
        sys.path.insert(0, str(CORE_DIR))
    from chatgpt_browser import ChatGPTBrowserSession

    class ExistingEdgeChatGPTSession(ChatGPTBrowserSession):
        async def __aenter__(self):
            self._playwright = await async_playwright().start()
            self.browser = await self._playwright.chromium.connect_over_cdp(self._cdp_url)
            if not self.browser.contexts:
                raise RuntimeError("Edge conectado por CDP pero no tiene contexto.")
            self.context = self.browser.contexts[0]
            pages = [p for p in self.context.pages if "chatgpt.com" in p.url]
            self.page = pages[0] if pages else await self.context.new_page()
            self._owns_context = False
            await navigate_chatgpt(self.page)
            self._note("Edge dedicado conectado por CDP.")
            return self

        async def __aexit__(self, exc_type, exc, tb):
            if self._playwright is not None:
                await self._playwright.stop()
            self._playwright = self.browser = self.context = self.page = None
            self._owns_context = False

    return ExistingEdgeChatGPTSession


async def run_worker(server: str, token: str, worker_id: str, cdp_url: str, profile_dir: Path) -> None:
    ensure_edge(cdp_url, profile_dir)
    SessionClass = await load_session_class()
    headers = {"Authorization": f"Bearer {token}"}
    server = server.rstrip("/")
    chat_router = WorkerChatRouter()

    def progress(message: str):
        print(f"[CHATGPT] {message}", flush=True)

    def callback_factory(name: str, is_async: bool):
        def render_message(args, kwargs):
            pieces = [str(value) for value in args if value is not None]
            if kwargs:
                pieces.append(json.dumps(json_safe(kwargs), ensure_ascii=False))
            detail = " ".join(piece for piece in pieces if piece).strip()
            return f"{name}: {detail}" if detail else name

        if is_async:
            async def async_callback(*args, **kwargs):
                progress(render_message(args, kwargs))
                return None
            return async_callback

        def sync_callback(*args, **kwargs):
            progress(render_message(args, kwargs))
            return None
        return sync_callback

    session = SessionClass(progress=progress)
    session._cdp_url = cdp_url

    async with httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(35.0, connect=10.0)) as client:
        async with session:
            await register_worker_with_retry(
                client,
                server,
                worker_id,
                retry_delay_seconds=float(os.getenv("STECH_WORKER_REGISTER_RETRY_SECONDS", "5")),
                heartbeat_timeout_seconds=float(os.getenv("STECH_WORKER_HEARTBEAT_TIMEOUT_SECONDS", "60")),
                log=lambda message: print(message, flush=True),
            )
            print(f"[WORKER] CONECTADO a {server} como {worker_id}")
            print("[WORKER] Esperando trabajos de Render...")

            while True:
                try:
                    response = await client.post(
                        f"{server}/api/research-worker/claim",
                        json={"worker_id": worker_id, "wait_seconds": 20},
                    )
                    if response.status_code == 204:
                        print("[WORKER] listo | sin trabajos", flush=True)
                        continue
                    response.raise_for_status()
                    task = response.json()
                    task_id = task["task_id"]
                    args = decode_remote_value(task.get("args") or [], callback_factory)
                    kwargs = decode_remote_value(task.get("kwargs") or {}, callback_factory)
                    remote_context = pop_remote_context(kwargs)
                    chat_key = str(remote_context.get("chat_key") or task_id)
                    research_kind = str(remote_context.get("research_kind") or "research")
                    turn = int(remote_context.get("turn") or 1)
                    print(
                        f"[WORKER] trabajo {task_id[:8]} recibido | {research_kind} | turno={turn} | args={len(args)}"
                    )
                    try:
                        result = await ask_in_job_chat_retry(
                            session,
                            args,
                            kwargs,
                            chat_key=chat_key,
                            router=chat_router,
                            max_attempts=2,
                        )
                        done = await client.post(
                            f"{server}/api/research-worker/tasks/{task_id}/complete",
                            json={"worker_id": worker_id, "result": json_safe(result)},
                        )
                        done.raise_for_status()
                        print(f"[WORKER] trabajo {task_id[:8]} COMPLETADO")
                    except Exception as exc:
                        message = f"{type(exc).__name__}: {exc}"
                        print(f"[WORKER] trabajo {task_id[:8]} ERROR: {message}")
                        fail = await client.post(
                            f"{server}/api/research-worker/tasks/{task_id}/fail",
                            json={"worker_id": worker_id, "message": message[:4000]},
                        )
                        if fail.status_code not in (200, 404):
                            fail.raise_for_status()
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    print(f"[WORKER] conexión: {type(exc).__name__}: {exc}; reintento en 5s")
                    await asyncio.sleep(5)


def parse_args():
    parser = argparse.ArgumentParser(description="STECH V7 Research Worker - ChatGPT por Microsoft Edge dedicado")
    parser.add_argument("--server", default=os.getenv("STECH_RENDER_URL", "https://stech-product-intelligence-web.onrender.com"))
    parser.add_argument("--token", default=os.getenv("STECH_RESEARCH_WORKER_TOKEN", ""))
    parser.add_argument("--worker-id", default=os.getenv("STECH_RESEARCH_WORKER_ID", socket.gethostname()))
    parser.add_argument("--cdp", default=os.getenv("STECH_EDGE_CDP", "http://127.0.0.1:9223"))
    parser.add_argument("--profile", default=os.getenv("STECH_EDGE_PROFILE", r"C:\STECH_CHATGPT_EDGE"))
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.token:
        raise SystemExit("Falta STECH_RESEARCH_WORKER_TOKEN. Configúralo igual que en Render.")
    asyncio.run(run_worker(args.server, args.token, args.worker_id, args.cdp, Path(args.profile)))


if __name__ == "__main__":
    main()
