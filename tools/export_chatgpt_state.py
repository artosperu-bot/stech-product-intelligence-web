from __future__ import annotations
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT = Path(__file__).resolve().parents[1] / 'chatgpt_storage_state.json'

async def main():
    print('Abriendo Chromium. Inicia sesión en ChatGPT manualmente.')
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(locale='es-PE')
        page = await context.new_page()
        await page.goto('https://chatgpt.com/', wait_until='domcontentloaded')
        print('Cuando ChatGPT esté listo y veas tu sesión, vuelve a esta consola y presiona ENTER.')
        await asyncio.to_thread(input)
        await context.storage_state(path=str(OUTPUT))
        await browser.close()
    print(f'Estado guardado en: {OUTPUT}')
    print('IMPORTANTE: contiene cookies/sesión. No lo subas a GitHub ni lo compartas.')

if __name__ == '__main__':
    asyncio.run(main())
