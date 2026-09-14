from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
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


@app.get('/api/jobs/{job_id}')
async def job_status(job_id: str):
    return _job_status_payload(_job_or_404(job_id))


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
