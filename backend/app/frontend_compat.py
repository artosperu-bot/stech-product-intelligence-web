from __future__ import annotations

AUTO_IDENTIFIER_SENTINEL = '__STECH_AUTO__'
FRONTEND_COMPAT_SRC = '/stech-auto-identifier.js?v=2'
FRONTEND_COMPAT_TAG = f'<script src="{FRONTEND_COMPAT_SRC}" defer></script>'


FRONTEND_COMPAT_JS = r"""(() => {
  'use strict';

  const SENTINEL = '__STECH_AUTO__';
  const HELPER_ID = 'stech-auto-identifier-help';
  const BATCH_PANEL_ID = 'stech-batch-results';
  const STORAGE_KEY = 'stech:last-characteristics-job';
  const POLL_MS = 2500;
  const ORIGINAL_FETCH = window.fetch.bind(window);
  let replaying = false;
  let pollGeneration = 0;
  let lastBatchData = null;
  let selectedProductIndex = 0;

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
      help.textContent = 'Déjalo vacío para detectar automáticamente todos los Part Numbers del Excel.';
      help.style.fontSize = '11px';
      help.style.opacity = '0.72';
      help.style.marginTop = '6px';
      input.insertAdjacentElement('afterend', help);
    }
  }

  function statusLabel(status) {
    const normalized = clean(status).toUpperCase();
    if (normalized === 'CREATED' || normalized === 'PENDING') return 'PENDIENTE';
    if (normalized === 'RUNNING') return 'INVESTIGANDO';
    if (normalized === 'COMPLETED') return 'COMPLETADO';
    if (normalized === 'ERROR') return 'ERROR';
    return normalized || 'PENDIENTE';
  }

  function element(tag, text) {
    const node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function stylePanel(panel) {
    panel.style.boxSizing = 'border-box';
    panel.style.width = 'min(1180px, calc(100% - 32px))';
    panel.style.margin = '24px auto 40px';
    panel.style.padding = '18px';
    panel.style.border = '1px solid rgba(127,127,127,.35)';
    panel.style.borderRadius = '12px';
    panel.style.background = 'var(--stech-batch-bg, rgba(127,127,127,.06))';
  }

  function addPreviewDetails(container, product) {
    const title = element('h4', product.detected_identifier || 'Producto');
    title.style.margin = '0 0 10px';
    container.appendChild(title);

    const identity = product.identity || {};
    const identityParts = [];
    if (identity.brand) identityParts.push(`Marca: ${identity.brand}`);
    if (identity.manufacturer_part_number) identityParts.push(`PN: ${identity.manufacturer_part_number}`);
    if (identity.commercial_model) identityParts.push(`Modelo: ${identity.commercial_model}`);
    if (identityParts.length) {
      const meta = element('div', identityParts.join(' · '));
      meta.style.fontSize = '12px';
      meta.style.opacity = '0.75';
      meta.style.marginBottom = '10px';
      container.appendChild(meta);
    }

    if (product.error) {
      const error = element('div', `Error: ${product.error}`);
      error.style.whiteSpace = 'pre-wrap';
      error.style.marginBottom = '10px';
      container.appendChild(error);
    }

    const preview = Array.isArray(product.preview) ? product.preview : [];
    if (!preview.length) {
      container.appendChild(element('div', 'Aún no hay campos disponibles para este producto.'));
      return;
    }

    const wrapper = element('div');
    wrapper.style.overflowX = 'auto';
    const table = element('table');
    table.style.width = '100%';
    table.style.borderCollapse = 'collapse';
    table.style.fontSize = '12px';

    const thead = element('thead');
    const headRow = element('tr');
    ['Campo', 'Valor', 'Estado', 'Confianza'].forEach((label) => {
      const th = element('th', label);
      th.style.textAlign = 'left';
      th.style.padding = '7px';
      th.style.borderBottom = '1px solid rgba(127,127,127,.35)';
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = element('tbody');
    preview.forEach((row) => {
      const tr = element('tr');
      const values = [
        row.field || row.original_name || row.name || '',
        row.value ?? row.valor ?? '',
        row.status || row.estado || '',
        row.confidence ?? row.confianza ?? '',
      ];
      values.forEach((value) => {
        const td = element('td', value);
        td.style.padding = '7px';
        td.style.verticalAlign = 'top';
        td.style.borderBottom = '1px solid rgba(127,127,127,.18)';
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrapper.appendChild(table);
    container.appendChild(wrapper);
  }

  function renderBatch(data) {
    if (!data || !Array.isArray(data.products)) return;
    lastBatchData = data;

    let panel = document.getElementById(BATCH_PANEL_ID);
    if (!isCharacteristics()) {
      if (panel) panel.style.display = 'none';
      return;
    }

    if (!panel) {
      panel = element('section');
      panel.id = BATCH_PANEL_ID;
      stylePanel(panel);
      document.body.appendChild(panel);
    }
    panel.style.display = 'block';
    panel.replaceChildren();

    const products = data.products;
    if (selectedProductIndex >= products.length) selectedProductIndex = 0;

    const heading = element('h3', `PRODUCTOS DETECTADOS: ${products.length}`);
    heading.style.margin = '0 0 6px';
    panel.appendChild(heading);

    const completed = Number(data.completed_count || products.filter((p) => p.status === 'COMPLETED').length);
    const errors = Number(data.error_count || products.filter((p) => p.status === 'ERROR').length);
    const running = products.filter((p) => p.status === 'RUNNING').length;
    const summaryParts = [`${completed}/${products.length} completados`];
    if (running) summaryParts.push(`${running} investigando`);
    if (errors) summaryParts.push(`${errors} con error`);
    if (data.state) summaryParts.push(`Trabajo: ${statusLabel(data.state)}`);
    const summary = element('div', summaryParts.join(' · '));
    summary.style.marginBottom = '14px';
    summary.style.fontSize = '13px';
    panel.appendChild(summary);

    const layout = element('div');
    layout.style.display = 'grid';
    layout.style.gridTemplateColumns = 'minmax(260px, 0.8fr) minmax(360px, 1.8fr)';
    layout.style.gap = '16px';
    layout.style.alignItems = 'start';

    const list = element('div');
    list.style.display = 'grid';
    list.style.gap = '6px';
    products.forEach((product, index) => {
      const row = element('button');
      row.type = 'button';
      row.style.width = '100%';
      row.style.textAlign = 'left';
      row.style.padding = '9px 10px';
      row.style.borderRadius = '8px';
      row.style.border = index === selectedProductIndex
        ? '2px solid currentColor'
        : '1px solid rgba(127,127,127,.3)';
      row.style.background = 'transparent';
      row.style.cursor = 'pointer';
      const pn = product.detected_identifier || product.identifier || `Producto ${index + 1}`;
      const rowNumber = product.source_row ? ` · fila ${product.source_row}` : '';
      row.textContent = `${pn}${rowNumber} — ${statusLabel(product.status)}`;
      row.addEventListener('click', () => {
        selectedProductIndex = index;
        renderBatch(lastBatchData);
      });
      list.appendChild(row);
    });

    const details = element('div');
    details.style.minWidth = '0';
    if (products.length) addPreviewDetails(details, products[selectedProductIndex]);
    else details.appendChild(element('div', 'No se detectaron productos.'));

    layout.appendChild(list);
    layout.appendChild(details);
    panel.appendChild(layout);

    const footer = element('div');
    footer.style.display = 'flex';
    footer.style.flexWrap = 'wrap';
    footer.style.gap = '10px';
    footer.style.alignItems = 'center';
    footer.style.marginTop = '16px';

    if (data.excel_ready && data.excel_download_url) {
      const download = element('a', 'DESCARGAR EXCEL');
      download.href = data.excel_download_url;
      download.style.display = 'inline-block';
      download.style.padding = '9px 14px';
      download.style.border = '1px solid currentColor';
      download.style.borderRadius = '8px';
      download.style.fontWeight = '700';
      download.style.textDecoration = 'none';
      footer.appendChild(download);
    } else if (clean(data.state).toUpperCase() === 'RUNNING') {
      footer.appendChild(element('span', 'El Excel se generará automáticamente al terminar el lote.'));
    }

    if (data.error) {
      const error = element('span', `Trabajo: ${data.error}`);
      error.style.whiteSpace = 'pre-wrap';
      footer.appendChild(error);
    }

    panel.appendChild(footer);
  }

  async function pollJob(jobId, generation) {
    if (!jobId || generation !== pollGeneration) return;
    try {
      const response = await ORIGINAL_FETCH(`/api/jobs/${encodeURIComponent(jobId)}`, {
        cache: 'no-store',
        headers: { Accept: 'application/json' },
      });
      if (!response.ok) return;
      const data = await response.json();
      renderBatch(data);
      const state = clean(data.state).toUpperCase();
      if (generation === pollGeneration && (state === 'CREATED' || state === 'RUNNING')) {
        setTimeout(() => pollJob(jobId, generation), POLL_MS);
      }
    } catch (_) {
      if (generation === pollGeneration) {
        setTimeout(() => pollJob(jobId, generation), POLL_MS * 2);
      }
    }
  }

  function startPolling(jobId) {
    if (!jobId) return;
    try { localStorage.setItem(STORAGE_KEY, jobId); } catch (_) {}
    pollGeneration += 1;
    pollJob(jobId, pollGeneration);
  }

  async function observeCharacteristicsResponse(response) {
    try {
      const cloned = response.clone();
      if (!cloned.body || !cloned.body.getReader) return;
      const reader = cloned.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          const text = clean(line);
          if (!text) continue;
          let event;
          try { event = JSON.parse(text); } catch (_) { continue; }
          if (event.job_id) startPolling(event.job_id);
          if (event.type === 'result' && event.data) renderBatch(event.data);
        }
        if (done) break;
      }
      const tail = clean(buffer);
      if (tail) {
        try {
          const event = JSON.parse(tail);
          if (event.job_id) startPolling(event.job_id);
          if (event.type === 'result' && event.data) renderBatch(event.data);
        } catch (_) {}
      }
    } catch (_) {}
  }

  window.fetch = async (...args) => {
    const target = args[0];
    const url = typeof target === 'string' ? target : ((target && target.url) || '');
    const response = await ORIGINAL_FETCH(...args);
    if (url.includes('/api/run/characteristics')) {
      observeCharacteristicsResponse(response);
    }
    return response;
  };

  document.addEventListener('click', (event) => {
    const button = event.target && event.target.closest ? event.target.closest('button') : null;
    if (!button) return;
    const label = clean(button.textContent).toUpperCase();

    if (label === 'NUEVO PRODUCTO') {
      pollGeneration += 1;
      lastBatchData = null;
      selectedProductIndex = 0;
      try { localStorage.removeItem(STORAGE_KEY); } catch (_) {}
      const panel = document.getElementById(BATCH_PANEL_ID);
      if (panel) panel.remove();
      return;
    }

    if (replaying || !isCharacteristics() || label !== 'INVESTIGAR') return;

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

  function refreshCompatibility() {
    applyCharacteristicsCopy();
    if (!lastBatchData) return;

    const panel = document.getElementById(BATCH_PANEL_ID);
    if (!isCharacteristics()) {
      if (panel) panel.style.display = 'none';
      return;
    }
    if (!panel || panel.style.display === 'none') renderBatch(lastBatchData);
  }

  const observer = new MutationObserver((mutations) => {
    const meaningful = mutations.some((mutation) => {
      const target = mutation.target;
      if (target && target.nodeType === 1 && target.closest && target.closest(`#${BATCH_PANEL_ID}`)) {
        return false;
      }
      return true;
    });
    if (meaningful) refreshCompatibility();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  refreshCompatibility();

  try {
    const previousJob = localStorage.getItem(STORAGE_KEY);
    if (previousJob) startPolling(previousJob);
  } catch (_) {}
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
