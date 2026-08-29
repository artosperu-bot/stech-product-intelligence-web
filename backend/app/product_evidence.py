from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .product_identity import CanonicalIdentity

_SOURCE_RANK = {
    'OFFICIAL_PDF': 700,
    'OFFICIAL_PRODUCT': 650,
    'OFFICIAL_SUPPORT': 620,
    'AUTHORIZED_DISTRIBUTOR': 520,
    'RETAILER': 420,
    'MARKETPLACE': 320,
    'SECONDARY': 220,
    'CONTROL': 0,
}


@dataclass
class EvidenceRecord:
    source_url: str = ''
    source_type: str = ''
    source_title: str = ''
    pdf_page: int | None = None
    evidence: str = ''
    applies_to: str = ''


@dataclass
class MasterSpecification:
    key: str
    label: str
    value: str
    unit: str
    status: str
    confidence: int
    source_url: str
    source_type: str
    source_title: str
    pdf_page: int | None
    evidence: str
    applies_to: str


def _text(value: Any) -> str:
    return str(value or '').strip()


def _confidence(value: Any) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def _page(value: Any) -> int | None:
    if value in (None, ''):
        return None
    try:
        return int(value)
    except Exception:
        return None


def source_rank(source_type: str) -> int:
    return _SOURCE_RANK.get(_text(source_type).upper(), 100)


def _raw_spec_list(raw: dict) -> list[dict]:
    if not isinstance(raw, dict):
        return []
    candidates = [
        raw.get('specifications'),
        raw.get('especificaciones_completas'),
        raw.get('master_specifications'),
        (raw.get('ficha_maestra') or {}).get('specifications')
        if isinstance(raw.get('ficha_maestra'), dict)
        else None,
        (raw.get('master') or {}).get('specifications')
        if isinstance(raw.get('master'), dict)
        else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return []


def parse_master_specifications(
    raw: dict,
    identity: CanonicalIdentity,
) -> list[MasterSpecification]:
    result: list[MasterSpecification] = []
    for item in _raw_spec_list(raw):
        key = _text(item.get('key') or item.get('campo') or item.get('name') or item.get('label'))
        label = _text(item.get('label') or item.get('nombre') or item.get('campo') or key)
        value = _text(item.get('value') if 'value' in item else item.get('valor'))
        unit = _text(item.get('unit') if 'unit' in item else item.get('unidad'))
        status = _text(item.get('status') or item.get('estado') or 'CONFIRMED').upper()
        source_url = _text(item.get('source_url') or item.get('url') or item.get('fuente'))
        source_type = _text(item.get('source_type') or item.get('tipo_fuente') or 'SECONDARY').upper()
        source_title = _text(
            item.get('source_title') or item.get('titulo_fuente') or item.get('documento')
        )
        evidence = _text(item.get('evidence') or item.get('evidencia') or item.get('fragmento'))
        applies_to = _text(
            item.get('applies_to') or item.get('aplica_a') or identity.manufacturer_part_number
        )
        result.append(
            MasterSpecification(
                key=key,
                label=label,
                value=value,
                unit=unit,
                status=status,
                confidence=_confidence(item.get('confidence', item.get('confianza', 0))),
                source_url=source_url,
                source_type=source_type,
                source_title=source_title,
                pdf_page=_page(item.get('pdf_page', item.get('pagina_pdf'))),
                evidence=evidence,
                applies_to=applies_to,
            )
        )
    return result


def _group_key(spec: MasterSpecification) -> str:
    return ' '.join((spec.key or spec.label).casefold().split())


def _same_product(spec: MasterSpecification, identity: CanonicalIdentity) -> bool:
    target = _text(spec.applies_to)
    mpn = _text(identity.manufacturer_part_number)
    if not target or not mpn:
        return True
    return target.casefold() == mpn.casefold()


def validate_master_specifications(
    specs: list[MasterSpecification],
    identity: CanonicalIdentity,
    min_confidence: int = 80,
) -> tuple[list[MasterSpecification], list[str]]:
    errors: list[str] = []
    eligible_by_key: dict[str, list[MasterSpecification]] = {}

    for spec in specs:
        key = _group_key(spec)
        if spec.source_type.upper() == 'CONTROL' or key.startswith('__control__'):
            errors.append(f'CONTROL_SENTINEL:{spec.label or spec.key}')
            continue
        if spec.status.upper() != 'CONFIRMED':
            continue
        if spec.confidence < min_confidence:
            continue
        if not _text(spec.value):
            continue
        if not _same_product(spec, identity):
            errors.append(f'CROSS_PRODUCT:{spec.label or spec.key}:{spec.applies_to}')
            continue
        eligible_by_key.setdefault(key, []).append(spec)

    accepted: list[MasterSpecification] = []
    for key, group in eligible_by_key.items():
        ranked = sorted(
            group,
            key=lambda spec: (source_rank(spec.source_type), spec.confidence),
            reverse=True,
        )
        top_rank = source_rank(ranked[0].source_type)
        top = [spec for spec in ranked if source_rank(spec.source_type) == top_rank]
        distinct_values = {(spec.value.casefold(), spec.unit.casefold()) for spec in top}
        if len(distinct_values) > 1:
            errors.append(f'CONFLICT:{key}')
            continue
        accepted.append(ranked[0])

    return accepted, errors
