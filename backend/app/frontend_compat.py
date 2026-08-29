from __future__ import annotations

AUTO_IDENTIFIER_SENTINEL = '__STECH_AUTO__'
FRONTEND_COMPAT_SRC = '/stech-auto-identifier.js?v=1'
FRONTEND_COMPAT_TAG = f'<script src="{FRONTEND_COMPAT_SRC}" defer></script>'


FRONTEND_COMPAT_JS = r"""(() => {
  'use strict';

  const SENTINEL = '__STECH_AUTO__';
  const HELPER_ID = 'stech-auto-identifier-help';
  let replaying = false;

  const clean = (value) => (value || '').trim();

  function isCharacteristics() {
    return Array.from(document.querySelectorAll('h1,h2,h3'))
      .some((el) => clean(el.textContent) === 'Características');
  }

  function findIdentifierInput() {
    return document.querySelector(
      'input[placeholder*="MPN / EAN / UPC / GTIN / SKU / modelo"], input[placeholder*="MPN"]'
    );
  }

  function setNativeValue(input, value) {
    const descriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
    if (descriptor && descriptor.set) descriptor.set.call(input, value);
    else input.value = value;
  }

  function notifyReact(input) {
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function applyCharacteristicsCopy() {
    if (!isCharacteristics()) return;

    const input = findIdentifierInput();
    if (!input) return;

    input.placeholder = 'Opcional: MPN / EAN / UPC / GTIN / SKU / modelo';

    for (const el of document.querySelectorAll('label,span,p,div')) {
      if (clean(el.textContent) === 'IDENTIFICADOR DEL PRODUCTO' && el.children.length === 0) {
        el.textContent = 'IDENTIFICADOR DEL PRODUCTO (OPCIONAL)';
        break;
      }
    }

    if (!document.getElementById(HELPER_ID)) {
      const help = document.createElement('div');
      help.id = HELPER_ID;
      help.textContent = 'Déjalo vacío para detectar automáticamente el Part Number desde el Excel.';
      help.style.fontSize = '11px';
      help.style.opacity = '0.72';
      help.style.marginTop = '6px';
      input.insertAdjacentElement('afterend', help);
    }
  }

  document.addEventListener('click', (event) => {
    if (replaying || !isCharacteristics()) return;

    const button = event.target && event.target.closest ? event.target.closest('button') : null;
    if (!button || clean(button.textContent).toUpperCase() !== 'INVESTIGAR') return;

    const input = findIdentifierInput();
    if (!input || clean(input.value)) return;

    event.preventDefault();
    event.stopImmediatePropagation();

    setNativeValue(input, SENTINEL);
    notifyReact(input);
    replaying = true;

    setTimeout(() => {
      button.click();
      setTimeout(() => {
        setNativeValue(input, '');
        notifyReact(input);
        replaying = false;
      }, 500);
    }, 0);
  }, true);

  const observer = new MutationObserver(applyCharacteristicsCopy);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  applyCharacteristicsCopy();
})();
"""


def normalize_frontend_identifier(value: str | None) -> str:
    text = str(value or '').strip()
    return '' if text == AUTO_IDENTIFIER_SENTINEL else text


def inject_frontend_compat(html: str) -> str:
    if FRONTEND_COMPAT_SRC in html:
        return html
    if '</body>' in html:
        return html.replace('</body>', f'{FRONTEND_COMPAT_TAG}</body>', 1)
    return html + FRONTEND_COMPAT_TAG
