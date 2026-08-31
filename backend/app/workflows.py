from __future__ import annotations
import asyncio
from pathlib import Path
import re
import shutil
import zipfile

from .browser_selector import chatgpt_session
from .marketplace_workbook import ProductWriteRecord, write_marketplace_workbook
from .product_characteristics import (
    CharacteristicsInput,
    build_product_intelligence,
    resolve_characteristics_input,
    resolve_characteristics_slots,
    serialize_identity,
)
from .product_workbook import assert_product_workbook_qa, finalize_product_workbook
from .serializers import serialize_preview_row, serialize_price_offer, serialize_image_record, serialize_video_record
from .v30_bridge import CORE_DIR  # noqa: F401

from excel_workflow import prepare_research, build_preview_rows, write_validated_workbook
from research_runner import run_research_for_preview_once
from price_workflow import prepare_price_research, run_price_research_v21, export_prices_xlsx
from price_web_verifier import verify_price_offers_headless
from image_workflow import prepare_image_research, run_image_research, download_image_records
from video_workflow import prepare_video_research, run_video_research, download_video_records


def inspect_template(path: Path, identifier: str | None = None) -> dict:
    resolved = resolve_characteristics_input(path, identifier)
    prep = prepare_research(path, resolved.identifier)
    response = {
        'family': prep.schema.family,
        'sheet_name': prep.schema.sheet_name,
        'category': prep.schema.category,
        'data_start_row': prep.schema.data_start_row,
        'researchable_count': prep.researchable_count,
        'fields': [field.original_name for field in prep.schema.research_fields],
        'input_mode': resolved.input_mode,
        'detected_identifier': resolved.identifier,
        'identifier_type': resolved.identifier_type,
    }
    try:
        profile, slots = resolve_characteristics_slots(path, identifier)
    except ValueError:
        return response
    response.update({
        'marketplace': profile.marketplace,
        'product_count': len(slots),
        'products': [
            {
                'row': slot.row,
                'identifier': slot.identifier,
                'identifier_type': slot.identifier_type,
                'category': slot.category,
            }
            for slot in slots
        ],
    })
    return response


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


def _product_pct(local_pct: int, index: int, total: int) -> int:
    total = max(1, total)
    start = 18 + int(70 * ((index - 1) / total))
    end = 18 + int(70 * (index / total))
    normalized = max(0.0, min(1.0, (local_pct - 20) / 60.0))
    return min(90, start + int((end - start) * normalized))


async def run_characteristics(job, identifier: str | None, template_path: Path, emit):
    emit(8, '1/7', 'Preparando plantilla', 'EXCEL')
    try:
        profile, slots = resolve_characteristics_slots(template_path, identifier)
    except ValueError as exc:
        if str(exc) == 'UNSUPPORTED_MARKETPLACE_TEMPLATE':
            profile = None
            resolved = resolve_characteristics_input(template_path, identifier)
            slots = [None]
        else:
            raise
    else:
        resolved = CharacteristicsInput(
            'manual' if str(identifier or '').strip() else 'auto',
            slots[0].identifier,
            slots[0].identifier_type,
            source_row=slots[0].row,
            marketplace=profile.marketplace,
        )

    total_products = len(slots)
    emit(10, '1/7', f'{total_products} producto(s) detectado(s) para investigación', 'IDENTIDAD')
    product_runs: list[dict] = []

    for index, slot in enumerate(slots, start=1):
        current_identifier = resolved.identifier if slot is None else slot.identifier
        current_type = resolved.identifier_type if slot is None else slot.identifier_type
        current_row = resolved.source_row if slot is None else slot.row
        emit(
            11 + int(5 * ((index - 1) / max(1, total_products))),
            '1/7',
            f'Producto {index}/{total_products} | fila {current_row or "-"} | {current_type}: {current_identifier}',
            'IDENTIDAD',
        )
        prep = prepare_research(template_path, current_identifier)
        emit(
            14 + int(4 * ((index - 1) / max(1, total_products))),
            '1/7',
            f'Producto {index}/{total_products}: {prep.researchable_count} campos investigables detectados',
            'EXCEL',
        )

        def progress(message: str, *, _index=index):
            pct, step, label = _stage_for_message('characteristics', message)
            emit(_product_pct(pct, _index, total_products), step, f'Producto {_index}/{total_products}: {message}', label)

        emit(_product_pct(20, index, total_products), '2/7', f'Producto {index}/{total_products}: iniciando sesión de investigación ChatGPT', 'NAVEGADOR')
        async with chatgpt_session(progress=progress, research_kind='characteristics') as session:
            result = await run_research_for_preview_once(
                prep,
                session.ask,
                min_confidence=80,
                output_dir=job.directory,
                progress=progress,
            )

        rows = build_preview_rows(prep, result.validation)
        raw = result.validation.raw if isinstance(result.validation.raw, dict) else {}
        product = raw.get('producto') or {}
        intelligence = build_product_intelligence(
            raw,
            template_path,
            current_identifier,
            min_confidence=80,
        )
        product_runs.append({
            'slot': slot,
            'preparation': prep,
            'validation': result.validation,
            'rows': rows,
            'product': product,
            'raw_paths': result.raw_paths,
            'identifier': current_identifier,
            'identifier_type': current_type,
            'source_row': current_row,
            'canonical_identity': intelligence.identity,
            'master_specifications': intelligence.specifications,
            'qa_warnings': intelligence.evidence_errors + intelligence.critical_errors,
            'followup_performed': bool(result.followup_performed),
        })

    emit(92, '6/7', f'Preparando vista previa validada de {total_products} producto(s)', 'VALIDACIÓN')
    first = product_runs[0]
    first_input = CharacteristicsInput(
        resolved.input_mode,
        first['identifier'],
        first['identifier_type'],
        source_row=first['source_row'],
        marketplace=profile.marketplace if profile is not None else '',
    )
    job.payload = {
        'preparation': first['preparation'],
        'validation': first['validation'],
        'rows': first['rows'],
        'product': first['product'],
        'raw_paths': first['raw_paths'],
        'template_path': template_path,
        'characteristics_input': first_input,
        'canonical_identity': first['canonical_identity'],
        'master_specifications': first['master_specifications'],
        'qa_warnings': first['qa_warnings'],
        'marketplace_profile': profile,
        'characteristic_products': product_runs,
    }

    serialized_products = []
    for item in product_runs:
        serialized_products.append({
            'source_row': item['source_row'],
            'detected_identifier': item['identifier'],
            'identifier_type': item['identifier_type'],
            'product': item['product'],
            'accepted_count': len(item['validation'].accepted),
            'total_count': item['preparation'].researchable_count,
            'rejected_count': len(item['validation'].rejected),
            'followup_performed': item['followup_performed'],
            'preview': [serialize_preview_row(row) for row in item['rows']],
            'identity': serialize_identity(item['canonical_identity']),
            'qa_ready': not item['qa_warnings'],
            'qa_warnings': item['qa_warnings'],
        })

    return {
        'job_id': job.id,
        'product': first['product'],
        'accepted_count': sum(len(item['validation'].accepted) for item in product_runs),
        'total_count': sum(item['preparation'].researchable_count for item in product_runs),
        'rejected_count': sum(len(item['validation'].rejected) for item in product_runs),
        'followup_performed': any(item['followup_performed'] for item in product_runs),
        'preview': [serialize_preview_row(row) for row in first['rows']],
        'input_mode': resolved.input_mode,
        'detected_identifier': first['identifier'],
        'identifier_type': first['identifier_type'],
        'identity': serialize_identity(first['canonical_identity']),
        'qa_ready': all(not item['qa_warnings'] for item in product_runs),
        'qa_warnings': [warning for item in product_runs for warning in item['qa_warnings']],
        'marketplace': profile.marketplace if profile is not None else '',
        'product_count': total_products,
        'products': serialized_products,
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


def _artifact_status_path(path: Path, completed: bool) -> Path:
    path = Path(path)
    stem = re.sub(r'(?i)(?:_)?COMPLETADO', '', path.stem)
    stem = re.sub(r'(?i)(?:_)?NO_VALIDADO', '', stem).rstrip('_- ')
    marker = 'COMPLETADO' if completed else 'NO_VALIDADO'
    return path.with_name(f'{stem}_{marker}{path.suffix}')


def generate_excel(job) -> Path:
    product_runs = job.payload.get('characteristic_products') or []
    profile = job.payload.get('marketplace_profile')
    template_path = job.payload.get('template_path')
    if product_runs and profile is not None and template_path is not None:
        records = [
            ProductWriteRecord(
                slot=item['slot'],
                identity=item['canonical_identity'],
                preview_rows=item['rows'],
                specifications=item.get('master_specifications') or [],
                warnings=item.get('qa_warnings') or [],
            )
            for item in product_runs
            if item.get('slot') is not None
        ]
        base = job.directory / Path(template_path).name
        provisional = _artifact_status_path(base, completed=True)
        qa = write_marketplace_workbook(Path(template_path), provisional, profile, records)
        final_path = _artifact_status_path(provisional, completed=qa.ok)
        if final_path != provisional:
            provisional.replace(final_path)
        job.payload['marketplace_workbook_qa'] = qa
        return final_path

    prep = job.payload['preparation']; validation = job.payload['validation']
    path = Path(write_validated_workbook(prep, validation, output_dir=job.directory))
    identity = job.payload.get('canonical_identity')
    if identity is None:
        return path
    specifications = job.payload.get('master_specifications') or []
    qa = finalize_product_workbook(path, identity, specifications, [])
    if not qa.ok:
        blocked = _artifact_status_path(path, completed=False)
        if blocked != path:
            path.replace(blocked)
        assert_product_workbook_qa(qa)
    completed = _artifact_status_path(path, completed=True)
    if completed != path:
        path.replace(completed)
    return completed


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
