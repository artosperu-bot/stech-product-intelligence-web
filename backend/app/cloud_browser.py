from __future__ import annotations
import json
import os
from pathlib import Path

from .v30_bridge import CORE_DIR  # noqa: F401
from chatgpt_browser import ChatGPTBrowserSession
from playwright.async_api import async_playwright


def _truthy(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return str(value).strip().casefold() not in {'0', 'false', 'no', 'off'}


def cloud_browser_config() -> dict:
    return {
        'headless': _truthy(os.getenv('STECH_HEADLESS'), True),
        'args': [
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--no-first-run',
            '--no-default-browser-check',
            # Keep Chromium lean enough for small container instances (Render Free).
            '--no-zygote',
            '--disable-extensions',
            '--disable-background-networking',
            '--disable-renderer-backgrounding',
            '--disable-background-timer-throttling',
            '--disable-component-update',
            '--disable-sync',
            '--metrics-recording-only',
            '--disable-features=Translate,MediaRouter,OptimizationHints,ProcessPerSiteUpToMainFrameThreshold',
            '--js-flags=--max-old-space-size=128',
        ],
    }


def runtime_storage_state_path() -> Path:
    custom = os.getenv('STECH_CHATGPT_RUNTIME_STATE', '').strip()
    if custom:
        return Path(custom)
    base = Path(os.getenv('STECH_RUNTIME_DIR', '/tmp/stech-product-intelligence'))
    return base / 'chatgpt_runtime_state.json'


def resolve_storage_state():
    runtime = runtime_storage_state_path()
    if runtime.exists():
        try:
            data = json.loads(runtime.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    raw = os.getenv('CHATGPT_STORAGE_STATE_JSON', '').strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


class CloudChatGPTBrowserSession(ChatGPTBrowserSession):
    """V30 ChatGPT DOM/capture logic with a Cloud Run-friendly headless browser shell."""

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        cfg = cloud_browser_config()
        self.browser = await self._playwright.chromium.launch(headless=cfg['headless'], args=cfg['args'])
        kwargs = {'locale': 'es-PE', 'viewport': {'width': 1440, 'height': 1000}}
        state = resolve_storage_state()
        if state:
            kwargs['storage_state'] = state
        self.context = await self.browser.new_context(**kwargs)
        self.page = await self.context.new_page()
        self._owns_context = True
        self._note('Chromium de servidor iniciado en modo headless.' if cfg['headless'] else 'Chromium de servidor iniciado.')
        await self.page.goto('https://chatgpt.com/', wait_until='domcontentloaded', timeout=60000)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        try:
            if self.context is not None:
                try:
                    runtime = runtime_storage_state_path()
                    runtime.parent.mkdir(parents=True, exist_ok=True)
                    await self.context.storage_state(path=str(runtime))
                except Exception:
                    pass
                await self.context.close()
            if self.browser is not None:
                await self.browser.close()
        finally:
            if self._playwright is not None:
                await self._playwright.stop()
            self._playwright = self.browser = self.context = self.page = None
            self._owns_context = False
