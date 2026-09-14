from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
import shutil
from typing import Callable, Awaitable

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .frontend_compat import FRONTEND_COMPAT_JS, inject_frontend_compat, normalize_frontend_identifier
from .jobs import JobStore
from .progress import ProgressEvent, encode_ndjson
from .settings import APP_NAME, APP_VERSION, WORKFLOWS, STATIC_DIR, RUNTIME_DIR
from .worker_api import router as worker_router
from .workflows import (
    inspect_template, run_characteristics, run_prices, run_images, run_videos,
    generate_excel, generate_prices_xlsx, generate_images_zip, generate_videos_zip,
)

STORE = JobStore(RUNTIME_DIR / 'jobs', ttl_minutes=int(os.getenv('ARTIFACT_TTL_MINUTES', '30')))


def health_payload() -> dict:
    return {'ok': True, 'app': APP_NAME, 'version': APP_VERSION, 'workflows': WORKFLOWS}

app = FastAPI(title=APP_NAME, version=APP_VERSION)
app.include_router(worker_router)

@app.get('/api/health')
async def health():
    return health_payload()


def _safe_name(name: str) -> str:
    base = Path(name or 'template.xlsx').name
    return base if base.lower().endswith('.xlsx') else base + '.xlsx'

async def _save_upload(upload: UploadFile, directory: Path) -> Path:
    path = directory / _safe_name(upload.filename or 'template.xlsx')
    with path.open('wb') as out:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk: break
            out.write(chunk)
    return path

async def _stream_job(kind: str, runner: Callable, *args, job=None):
    job = job or STORE.create(kind)
    queue: asyncio.Queue[dict] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    STORE.mark_running(job.id)

    def emit(percent: int, step: str, message: str, category: str = 'PROCESO', detail: str = ''):
        event = ProgressEvent(percent, step, message, category, detail).to_dict()
        try:
            if asyncio.get_running_loop() is loop:
                queue.put_nowait(event)
            else:
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except RuntimeError:
            loop.call_soon_threadsafe(queue.put_nowait, event)

    async def work():
        try:
            await queue.put({'type': 'start', 'job_id': job.id, 'kind': kind})
            result = await runner(job, *args, emit)
            STORE.set_public_data(job.id, result if isinstance(result, dict) else {'result': result})
            STORE.mark_completed(job.id)
            await queue.put({'type': 'result', 'percent': 100, 'job_id': job.id, 'data': result})
        except Exception as exc:
            STORE.mark_error(job.id, str(exc))
            await queue.put({'type': 'error', 'job_id': job.id, 'message': str(exc)})

    task = asyncio.create_task(work())
    while True:
        event = await queue.get()
        yield encode_ndjson(event)
        if event.get('type') in {'result', 'error'}:
            break
    await task

@app.post('/api/template/inspect')
async def template_inspect(identifier: str = Form(''), template: UploadFile = File(...)):
    identifier = normalize_frontend_identifier(identifier)
    job = STORE.create('inspect')
    STORE.mark_running(job.id)
    path = await _save_upload(template, job.directory)
    try:
        result = inspect_template(path, identifier)
        STORE.set_public_data(job.id, result)
        STORE.mark_completed(job.id)
        return result
    except Exception as exc:
        STORE.mark_error(job.id, str(exc))
        raise HTTPException(400, str(exc))

@app.post('/api/run/characteristics')
async def run_characteristics_api(identifier: str = Form(''), template: UploadFile = File(...)):
    identifier = normalize_frontend_identifier(identifier)
    job = STORE.create('characteristics')
    path = await _save_upload(template, job.directory)
    return StreamingResponse(_stream_job('characteristics', run_characteristics, identifier, path, job=job), media_type='application/x-ndjson')

@app.post('/api/run/prices')
async def run_prices_api(identifier: str = Form(...)):
    return StreamingResponse(_stream_job('prices', run_prices, identifier), media_type='application/x-ndjson')

@app.post('/api/run/images')
async def run_images_api(identifier: str = Form(...)):
    return StreamingResponse(_stream_job('images', run_images, identifier), media_type='application/x-ndjson')

@app.post('/api/run/videos')
async def run_videos_api(identifier: str = Form(...)):
    return StreamingResponse(_stream_job('videos', run_videos, identifier), media_type='application/x-ndjson')

class SelectionRequest(BaseModel):
    indices: list[int] = []

def _job_or_404(job_id: str):
    try: return STORE.get(job_id)
    except KeyError: raise HTTPException(404, 'El trabajo ya no existe o expiró. Vuelve a ejecutar la búsqueda.')


def _existing_artifact(job, name: str) -> Path | None:
    path = job.artifacts.get(name)
    if path is None:
        return None
    path = Path(path)
    return path if path.exists() and path.is_file() else None


def _job_status_payload(job) -> dict:
    data = dict(job.public_data or {})
    excel = _existing_artifact(job, 'excel')
    data.update({
        'job_id': job.id,
        'kind': job.kind,
        'state': job.state,
        'created_at': job.created_at.isoformat(),
        'updated_at': job.updated_at.isoformat(),
        'finished_at': job.finished_at.isoformat() if job.finished_at else None,
        'error': job.error or data.get('error', ''),
        'products': list(data.get('products') or []),
        'product_count': int(data.get('product_count') or len(data.get('products') or [])),
        'excel_ready': bool(excel),
        'excel_download_url': f'/api/jobs/{job.id}/excel' if excel else data.get('excel_download_url'),
        'artifacts': {
            name: bool(_existing_artifact(job, name))
            for name in job.artifacts
        },
    })
    return data


class _RetryStepJob:
    """Ephemeral adapter so a retry step can reuse the characteristics workflow
    without replacing the parent retry job's persisted batch status."""

    def __init__(self, job_id: str, directory: Path):
        self.id = job_id
        self.directory = Path(directory)
        self.payload: dict = {}
        self.public_data: dict = {}
        self.artifacts: dict[str, Path] = {}

    def set_public_data(self, data: dict) -> None:
        self.public_data = dict(data or {})

    def add_artifact(self, name: str, path: Path) -> None:
        self.artifacts[str(name)] = Path(path)


def _retry_public_payload(job, source_job_id: str, products: list[dict], excel_path: Path | None) -> dict:
    completed = sum(1 for item in products if str(item.get('status') or '').upper() == 'COMPLETED')
    errors = sum(1 for item in products if str(item.get('status') or '').upper() == 'ERROR')
    running = sum(1 for item in products if str(item.get('status') or '').upper() == 'RUNNING')
    pending = sum(1 for item in products if str(item.get('status') or '').upper() == 'PENDING')
    ready = bool(excel_path and Path(excel_path).exists())
    return {
        'job_id': job.id,
        'retry_of': source_job_id,
        'product_count': len(products),
        'completed_count': completed,
        'error_count': errors,
        'running_count': running,
        'pending_count': pending,
        'partial': errors > 0,
        'products': products,
        'excel_ready': ready,
        'excel_download_url': f'/api/jobs/{job.id}/excel' if ready else None,
    }


async def _run_retry_failed(job, source_job_id: str, emit):
    source = _job_or_404(source_job_id)
    source_data = _job_status_payload(source)
    products = [dict(item) for item in (source_data.get('products') or [])]
    failed_indices = [
        index for index, item in enumerate(products)
        if str(item.get('status') or '').upper() == 'ERROR'
    ]
    source_excel = _existing_artifact(source, 'excel')
    if source_excel is None:
        raise RuntimeError('No existe un Excel parcial recuperable para reintentar los productos fallidos.')

    base_name = Path(source_excel).name
    current_excel = job.directory / f'retry_base_{base_name}'
    await asyncio.to_thread(shutil.copy2, source_excel, current_excel)
    job.add_artifact('excel', current_excel)
    job.set_public_data(_retry_public_payload(job, source_job_id, products, current_excel))

    if not failed_indices:
        emit(100, '1/1', 'No hay productos fallidos para reintentar', 'REINTENTO')
        return _retry_public_payload(job, source_job_id, products, current_excel)

    total = len(failed_indices)
    for position, product_index in enumerate(failed_indices, start=1):
        item = products[product_index]
        identifier = str(item.get('detected_identifier') or item.get('identifier') or '').strip()
        if not identifier:
            item['status'] = 'ERROR'
            item['error'] = 'No se pudo determinar el identificador del producto para el reintento.'
            job.set_public_data(_retry_public_payload(job, source_job_id, products, current_excel))
            continue

        item['status'] = 'RUNNING'
        item['error'] = ''
        job.set_public_data(_retry_public_payload(job, source_job_id, products, current_excel))
        emit(
            5 + int(85 * ((position - 1) / max(1, total))),
            f'{position}/{total}',
            f'Reintentando {identifier} ({position}/{total})',
            'REINTENTO',
        )

        input_path = job.directory / f'retry_input_{position:02d}.xlsx'
        await asyncio.to_thread(shutil.copy2, current_excel, input_path)
        step_job = _RetryStepJob(job.id, job.directory)

        def step_emit(percent: int, step: str, message: str, category: str = 'PROCESO', detail: str = ''):
            start = 5 + int(85 * ((position - 1) / max(1, total)))
            end = 5 + int(85 * (position / max(1, total)))
            scaled = start + int((end - start) * max(0, min(100, int(percent))) / 100)
            emit(scaled, f'{position}/{total}', f'{identifier}: {message}', category, detail)

        try:
            result = await run_characteristics(step_job, identifier, input_path, step_emit)
            retry_products = list(result.get('products') or [])
            retry_item = dict(retry_products[0]) if retry_products else dict(item)
            retry_item['status'] = 'COMPLETED'
            retry_item['error'] = ''
            products[product_index] = retry_item
            step_excel = step_job.artifacts.get('excel')
            if step_excel is not None and Path(step_excel).exists():
                current_excel = Path(step_excel)
                job.add_artifact('excel', current_excel)
        except Exception as exc:
            item['status'] = 'ERROR'
            item['error'] = f'Reintento fallido: {exc}'
            products[product_index] = item

        job.set_public_data(_retry_public_payload(job, source_job_id, products, current_excel))

    final = _retry_public_payload(job, source_job_id, products, current_excel)
    emit(96, 'FINAL', 'Reintento finalizado; preparando Excel recuperado', 'REINTENTO')
    job.add_artifact('excel', current_excel)
    job.set_public_data(final)
    return final


@app.get('/api/jobs/{job_id}')
async def job_status(job_id: str):
    return _job_status_payload(_job_or_404(job_id))


@app.post('/api/jobs/{job_id}/retry-failed')
async def retry_failed_artifact(job_id: str):
    source = _job_or_404(job_id)
    data = _job_status_payload(source)
    failed = [item for item in data.get('products', []) if str(item.get('status') or '').upper() == 'ERROR']
    if not failed:
        raise HTTPException(400, 'Este trabajo no tiene productos fallidos para reintentar.')
    if _existing_artifact(source, 'excel') is None:
        raise HTTPException(400, 'No existe un Excel parcial para conservar los productos ya completados.')
    retry_job = STORE.create('characteristics-retry')
    return StreamingResponse(
        _stream_job('characteristics-retry', _run_retry_failed, job_id, job=retry_job),
        media_type='application/x-ndjson',
    )


@app.get('/api/jobs/{job_id}/excel')
@app.post('/api/jobs/{job_id}/excel')
async def excel_artifact(job_id: str):
    job = _job_or_404(job_id)
    path = _existing_artifact(job, 'excel')
    if path is None:
        try:
            path = await asyncio.to_thread(generate_excel, job)
            STORE.add_artifact(job.id, 'excel', path)
        except Exception as exc:
            raise HTTPException(400, str(exc))
    return FileResponse(path, filename=path.name, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.post('/api/jobs/{job_id}/prices.xlsx')
async def prices_artifact(job_id: str):
    job = _job_or_404(job_id)
    try: path = await asyncio.to_thread(generate_prices_xlsx, job)
    except Exception as exc: raise HTTPException(400, str(exc))
    return FileResponse(path, filename=path.name, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.post('/api/jobs/{job_id}/images.zip')
async def images_artifact(job_id: str, selection: SelectionRequest):
    job = _job_or_404(job_id)
    try: path = await asyncio.to_thread(generate_images_zip, job, selection.indices)
    except Exception as exc: raise HTTPException(400, str(exc))
    return FileResponse(path, filename=path.name, media_type='application/zip')

@app.post('/api/jobs/{job_id}/videos.zip')
async def videos_artifact(job_id: str, selection: SelectionRequest):
    job = _job_or_404(job_id)
    try: path = await asyncio.to_thread(generate_videos_zip, job, selection.indices)
    except Exception as exc: raise HTTPException(400, str(exc))
    return FileResponse(path, filename=path.name, media_type='application/zip')

if STATIC_DIR.exists():
    assets = STATIC_DIR / 'assets'
    if assets.exists(): app.mount('/assets', StaticFiles(directory=assets), name='assets')

@app.get('/stech-auto-identifier.js', include_in_schema=False)
async def frontend_auto_identifier_script():
    return Response(
        FRONTEND_COMPAT_JS,
        media_type='application/javascript',
        headers={'Cache-Control': 'no-store'},
    )

@app.get('/{full_path:path}')
async def spa(full_path: str):
    index = STATIC_DIR / 'index.html'
    if index.exists():
        html = inject_frontend_compat(index.read_text(encoding='utf-8'))
        return HTMLResponse(html, headers={'Cache-Control': 'no-store'})
    return health_payload()
