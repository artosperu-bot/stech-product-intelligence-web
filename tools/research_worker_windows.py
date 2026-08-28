from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request

import httpx
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = ROOT / "backend" / "legacy_core"
BUNDLE_DIR = ROOT / "legacy_core_bundle_v2"


def ensure_legacy_core() -> None:
    if (CORE_DIR / "chatgpt_browser.py").exists():
        return
    parts = sorted(BUNDLE_DIR.glob("part-*.b64"))
    if not parts:
        raise RuntimeError("No encuentro legacy_core_bundle_v2. Ejecuta el worker desde el repositorio STECH.")
    encoded = "".join(p.read_text(encoding="ascii") for p in parts)
    archive = base64.b64decode(encoded)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tf:
        tf.extractall(ROOT)
    if not (CORE_DIR / "chatgpt_browser.py").exists():
        raise RuntimeError("legacy_core se extrajo pero falta chatgpt_browser.py")


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

    def progress(message: str):
        print(f"[CHATGPT] {message}", flush=True)

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
                    args = task.get("args") or []
                    kwargs = task.get("kwargs") or {}
                    print(f"[WORKER] trabajo {task_id[:8]} recibido | args={len(args)}")
                    try:
                        result = await session.ask(*args, **kwargs)
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
