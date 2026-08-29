from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
from typing import Callable, Awaitable

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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
            await queue.put({'type': 'result', 'percent': 100, 'job_id': job.id, 'data': result})
        except Exception as exc:
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
    job = STORE.create('inspect')
    path = await _save_upload(template, job.directory)
    try:
        return inspect_template(path, identifier)
    except Exception as exc:
        raise HTTPException(400, str(exc))

@app.post('/api/run/characteristics')
async def run_characteristics_api(identifier: str = Form(''), template: UploadFile = File(...)):
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

@app.post('/api/jobs/{job_id}/excel')
async def excel_artifact(job_id: str):
    job = _job_or_404(job_id)
    try: path = await asyncio.to_thread(generate_excel, job)
    except Exception as exc: raise HTTPException(400, str(exc))
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

@app.get('/{full_path:path}')
async def spa(full_path: str):
    index = STATIC_DIR / 'index.html'
    if index.exists(): return FileResponse(index)
    return health_payload()
