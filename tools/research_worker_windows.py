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
from app.remote_protocol import decode_remote_value
from app.worker_chat_policy import (
    WorkerChatRouter,
    composer_has_unsent_prompt,
    pop_remote_context,
    prepare_chatgpt_composer,
)


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


def chrome_candidates() -> list[Path]:
    candidates = []
    for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.getenv(key)
        if base:
            candidates.append(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe")
    return candidates


def cdp_alive(cdp_url: str) -> bool:
    url = cdp_url.rstrip("/") + "/json/version"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def ensure_chrome(cdp_url: str, profile_dir: Path) -> None:
    if cdp_alive(cdp_url):
        print(f"[CHROME] CDP disponible: {cdp_url}")
        return
    chrome = next((p for p in chrome_candidates() if p.exists()), None)
    if chrome is None:
        raise RuntimeError("No encontré Google Chrome instalado en Windows.")
    profile_dir.mkdir(parents=True, exist_ok=True)
    print(f"[CHROME] Iniciando Chrome real con perfil: {profile_dir}")
    subprocess.Popen(
        [
            str(chrome),
            "--remote-debugging-port=9222",
            f"--user-data-dir={profile_dir}",
            "https://chatgpt.com/",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        if cdp_alive(cdp_url):
            return
        time.sleep(0.5)
    raise RuntimeError("Chrome abrió pero CDP 9222 no respondió.")


def json_safe(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


async def recover_chatgpt_page(session):
    page = getattr(session, "page", None)
    try:
        if page is not None and not page.is_closed():
            return page
    except Exception:
        pass

    context = getattr(session, "context", None)
    if context is None:
        raise RuntimeError("Chrome conectado pero el worker perdió el contexto de navegador.")

    for candidate in list(context.pages):
        try:
            if not candidate.is_closed() and "chatgpt.com" in (candidate.url or ""):
                session.page = candidate
                session._note("Pestaña ChatGPT recuperada desde Chrome real.")
                return candidate
        except Exception:
            continue

    page = await context.new_page()
    await page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
    session.page = page
    session._note("Nueva pestaña ChatGPT creada en Chrome real.")
    return page


async def open_fresh_chat(session):
    """Start a clean ChatGPT conversation for a new research job or a retry."""
    page = await recover_chatgpt_page(session)
    try:
        await page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        session.page = None
        page = await recover_chatgpt_page(session)
        await page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
    session.page = page
    session._note("Nuevo chat de ChatGPT listo para este trabajo de investigación.")
    return page


async def guard_unsent_prompt(session, expected_prompt: str, delay_seconds: float = 2.5) -> None:
    """Click Send only when the complete prompt is still sitting unsent in the composer."""
    try:
        await asyncio.sleep(max(0.5, float(delay_seconds)))
        page = await recover_chatgpt_page(session)
        await prepare_chatgpt_composer(page, timeout_seconds=5.0)
        composer = page.locator("#prompt-textarea")
        if await composer.count() < 1:
            return
        text = await composer.first.inner_text(timeout=3000)
        if not composer_has_unsent_prompt(expected_prompt, text):
            return

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
    except Exception:
        return


async def assistant_message_count(session) -> int:
    try:
        page = await recover_chatgpt_page(session)
        return await page.locator('[data-message-author-role="assistant"]').count()
    except Exception:
        return 0


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
        try:
            page = await router.prepare(chat_key, session, open_fresh_chat, recover_chatgpt_page)
            await prepare_chatgpt_composer(page)
            session._note("Compositor real de ChatGPT estable y listo.")
            baseline_count = await assistant_message_count(session)

            if expected_prompt:
                guard = asyncio.create_task(guard_unsent_prompt(session, expected_prompt))
            ask_task = asyncio.create_task(session.ask(*args, **kwargs))
            dom_task = asyncio.create_task(wait_for_new_assistant_json(session, baseline_count))

            done, _ = await asyncio.wait({ask_task, dom_task}, return_when=asyncio.FIRST_COMPLETED)
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
            if attempt >= attempts:
                raise
            session._note(
                f"La consulta de ChatGPT falló ({type(exc).__name__}); reintentando una vez en un chat nuevo..."
            )
        finally:
            if guard is not None:
                guard.cancel()
                await asyncio.gather(guard, return_exceptions=True)
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

    class ExistingChromeChatGPTSession(ChatGPTBrowserSession):
        async def __aenter__(self):
            self._playwright = await async_playwright().start()
            self.browser = await self._playwright.chromium.connect_over_cdp(self._cdp_url)
            if not self.browser.contexts:
                raise RuntimeError("Chrome conectado por CDP pero no tiene contexto.")
            self.context = self.browser.contexts[0]
            pages = [p for p in self.context.pages if "chatgpt.com" in p.url]
            self.page = pages[0] if pages else await self.context.new_page()
            self._owns_context = False
            await self.page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
            self._note("Chrome real conectado por CDP.")
            return self

        async def __aexit__(self, exc_type, exc, tb):
            if self._playwright is not None:
                await self._playwright.stop()
            self._playwright = self.browser = self.context = self.page = None
            self._owns_context = False

    return ExistingChromeChatGPTSession


async def run_worker(server: str, token: str, worker_id: str, cdp_url: str, profile_dir: Path) -> None:
    ensure_chrome(cdp_url, profile_dir)
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
            heartbeat = await client.post(f"{server}/api/research-worker/heartbeat", json={"worker_id": worker_id})
            heartbeat.raise_for_status()
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
    parser = argparse.ArgumentParser(description="STECH V7 Research Worker - ChatGPT por Chrome real")
    parser.add_argument("--server", default=os.getenv("STECH_RENDER_URL", "https://stech-product-intelligence-web.onrender.com"))
    parser.add_argument("--token", default=os.getenv("STECH_RESEARCH_WORKER_TOKEN", ""))
    parser.add_argument("--worker-id", default=os.getenv("STECH_RESEARCH_WORKER_ID", socket.gethostname()))
    parser.add_argument("--cdp", default=os.getenv("STECH_CHROME_CDP", "http://127.0.0.1:9222"))
    parser.add_argument("--profile", default=os.getenv("STECH_CHROME_PROFILE", r"C:\STECH_CHATGPT_CHROME"))
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.token:
        raise SystemExit("Falta STECH_RESEARCH_WORKER_TOKEN. Configúralo igual que en Render.")
    asyncio.run(run_worker(args.server, args.token, args.worker_id, args.cdp, Path(args.profile)))


if __name__ == "__main__":
    main()
