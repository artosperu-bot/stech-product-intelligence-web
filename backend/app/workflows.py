from __future__ import annotations
import asyncio
from pathlib import Path
import shutil
import zipfile

from .browser_selector import chatgpt_session
from .serializers import serialize_preview_row, serialize_price_offer, serialize_image_record, serialize_video_record
from .v30_bridge import CORE_DIR  # noqa: F401

from excel_workflow import prepare_research, build_preview_rows, write_validated_workbook
from research_runner import run_research_for_preview_once
from price_workflow import prepare_price_research, run_price_research_v21, export_prices_xlsx
from price_web_verifier import verify_price_offers_headless
from image_workflow import prepare_image_research, run_image_research, download_image_records
from video_workflow import prepare_video_research, run_video_research, download_video_records


def inspect_template(path: Path, identifier: str) -> dict:
    prep = prepare_research(path, identifier)
    return {
        'family': prep.schema.family,
        'sheet_name': prep.schema.sheet_name,
        'category': prep.schema.category,
        'data_start_row': prep.schema.data_start_row,
        'researchable_count': prep.researchable_count,
        'fields': [field.original_name for field in prep.schema.research_fields],
    }



def discovery_source_count(discovery) -> int:
    if hasattr(discovery, 'sources'):
        return len(getattr(discovery, 'sources') or [])
    if hasattr(discovery, 'videos'):
        return len(getattr(discovery, 'videos') or [])
    return 0

def _stage_for_message(kind: str, message: str) -> tuple[int, str, str]:
    text = (message or '').casefold()
    if kind == 'characteristics':
        if 'segunda pasada' in text: return 78, '5/7', 'Segunda pasada'
        if 'json' in text or 'captur' in text: return 66, '4/7', 'Capturando respuesta'
        if 'navegador' in text or 'chromium' in text: return 24, '2/7', 'Navegador'
        return 42, '3/7', 'Investigación'
    if kind == 'prices':
        if 'pasada 3' in text: return 58, '4/7', 'Tercera pasada'
        if 'pasada 2' in text: return 38, '3/7', 'Segunda pasada'
        if 'verific' in text: return 74, '6/7', 'Verificación web'
        if 'pasada 1' in text: return 18, '2/7', 'Primera pasada'
        return 28, '2/7', 'Investigación'
    if kind == 'images':
        if 'valid' in text or 'imagen' in text: return 45, '3/5', 'Validando imágenes'
        return 25, '2/5', 'Descubriendo fuentes'
    if kind == 'videos':
        if 'valid' in text or 'video' in text: return 45, '3/5', 'Validando videos'
        return 25, '2/5', 'Descubriendo fuentes'
    return 10, '1/1', 'Procesando'


async def run_characteristics(job, identifier: str, template_path: Path, emit):
    emit(8, '1/7', 'Preparando plantilla', 'EXCEL')
    prep = prepare_research(template_path, identifier)
    emit(14, '1/7', f'{prep.researchable_count} campos investigables detectados', 'EXCEL')
    def progress(message: str):
        pct, step, label = _stage_for_message('characteristics', message)
        emit(pct, step, message, label)
    emit(20, '2/7', 'Iniciando sesión de investigación ChatGPT', 'NAVEGADOR')
    async with chatgpt_session(progress=progress, research_kind='characteristics') as session:
        result = await run_research_for_preview_once(
            prep, session.ask, min_confidence=80, output_dir=job.directory, progress=progress,
        )
    emit(92, '6/7', 'Preparando vista previa validada', 'VALIDACIÓN')
    rows = build_preview_rows(prep, result.validation)
    product = (result.validation.raw or {}).get('producto') or {}
    job.payload = {'preparation': prep, 'validation': result.validation, 'rows': rows, 'product': product, 'raw_paths': result.raw_paths}
    accepted = len(result.validation.accepted)
    return {
        'job_id': job.id,
        'product': product,
        'accepted_count': accepted,
        'total_count': prep.researchable_count,
        'rejected_count': len(result.validation.rejected),
        'followup_performed': bool(result.followup_performed),
        'preview': [serialize_preview_row(row) for row in rows],
    }


async def run_prices(job, identifier: str, emit):
    prep = prepare_price_research(identifier)
    emit(8, '1/7', 'Preparando búsqueda de precios Perú', 'PRECIOS')
    def progress(message: str):
        pct, step, label = _stage_for_message('prices', message)
        emit(pct, step, message, label)
    def discovery_ready(validation):
        emit(70, '5/7', f'{len(validation.offers)} ofertas descubiertas', 'RESULTADO')
    def verifier_update(validation, done, total):
        pct = 74 + int(22 * (done / max(1, total)))
        emit(pct, '6/7', f'Verificando oferta {done}/{total}', 'VERIFICACIÓN')
    async with chatgpt_session(progress=progress, research_kind='prices') as session:
        run = await run_price_research_v21(
            prep, session.ask, verifier_fn=verify_price_offers_headless,
            min_match_confidence=80, output_dir=job.directory, progress=progress,
            discovery_ready=discovery_ready, verifier_update=verifier_update,
        )
    job.payload = {'preparation': prep, 'validation': run.validation, 'run': run}
    product = (run.validation.raw or {}).get('producto') or {}
    offers = [serialize_price_offer(o, i) for i, o in enumerate(run.validation.offers)]
    return {'job_id': job.id, 'product': product, 'offers': offers, 'count': len(offers)}


async def run_images(job, identifier: str, emit):
    prep = prepare_image_research(identifier)
    emit(8, '1/5', 'Preparando búsqueda global de imágenes', 'IMÁGENES')
    def progress(message: str):
        pct, step, label = _stage_for_message('images', message)
        emit(pct, step, message, label)
    def discovery_ready(discovery):
        emit(34, '2/5', f'{discovery_source_count(discovery)} fuentes descubiertas', 'FUENTES')
    def image_ready(record, done, total):
        pct = 40 + int(55 * (done / max(1, total)))
        emit(pct, '4/5', f'Imagen {done}/{total}: {record.source_name or record.source_type}', 'VALIDACIÓN')
    async with chatgpt_session(progress=progress, research_kind='images') as session:
        run = await run_image_research(prep, session.ask, progress=progress, discovery_ready=discovery_ready, image_ready=image_ready)
    job.payload = {'run': run}
    product = run.discovery.product or {}
    images = [serialize_image_record(r, i) for i, r in enumerate(run.images)]
    return {'job_id': job.id, 'product': product, 'images': images, 'count': len(images), 'scan_error': run.scan_error}


async def run_videos(job, identifier: str, emit):
    prep = prepare_video_research(identifier)
    emit(8, '1/5', 'Preparando búsqueda global de videos', 'VIDEOS')
    def progress(message: str):
        pct, step, label = _stage_for_message('videos', message)
        emit(pct, step, message, label)
    def discovery_ready(discovery):
        emit(34, '2/5', f'{discovery_source_count(discovery)} fuentes descubiertas', 'FUENTES')
    def video_ready(record, done, total):
        pct = 40 + int(55 * (done / max(1, total)))
        emit(pct, '4/5', f'Video {done}/{total}: {record.title or record.source_name}', 'VALIDACIÓN')
    async with chatgpt_session(progress=progress, research_kind='videos') as session:
        run = await run_video_research(prep, session.ask, progress=progress, discovery_ready=discovery_ready, video_ready=video_ready)
    job.payload = {'run': run}
    product = run.discovery.product or {}
    videos = [serialize_video_record(r, i) for i, r in enumerate(run.videos)]
    return {'job_id': job.id, 'product': product, 'videos': videos, 'count': len(videos), 'scan_error': run.scan_error}


def generate_excel(job) -> Path:
    prep = job.payload['preparation']; validation = job.payload['validation']
    return write_validated_workbook(prep, validation, output_dir=job.directory)


def generate_prices_xlsx(job) -> Path:
    prep = job.payload['preparation']; validation = job.payload['validation']
    return export_prices_xlsx(prep, validation, output_dir=job.directory)


def _zip_folder(folder: Path, target: Path) -> Path:
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(folder.rglob('*')):
            if path.is_file() and path != target:
                zf.write(path, path.relative_to(folder))
    return target


def generate_images_zip(job, indices: list[int]) -> Path:
    run = job.payload['run']
    selected = [run.images[i] for i in indices if 0 <= i < len(run.images)]
    if not selected:
        selected = [r for r in run.images if int(getattr(r, 'relevance_score', 0) or 0) >= 80][:6]
    folder = download_image_records(run.discovery.product or {}, run.preparation.identifier, selected, job.directory / 'images')
    return _zip_folder(folder, job.directory / 'IMAGENES_PRODUCTO.zip')


def generate_videos_zip(job, indices: list[int]) -> Path:
    run = job.payload['run']
    selected = [run.videos[i] for i in indices if 0 <= i < len(run.videos)]
    if not selected:
        selected = [r for r in run.videos if int(getattr(r, 'relevance_score', 0) or 0) >= 80][:6]
    folder = download_video_records(run.discovery.product or {}, run.preparation.identifier, selected, job.directory / 'videos')
    return _zip_folder(folder, job.directory / 'VIDEOS_PRODUCTO.zip')
