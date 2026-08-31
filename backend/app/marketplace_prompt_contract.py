from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Iterable

from .marketplace_template import (
    MarketplaceTemplateProfile,
    ProductSlot,
    TemplateField,
    is_placeholder_value,
)


@dataclass(frozen=True)
class TemplateValueValidation:
    ok: bool
    value: str
    reason: str = ''


def _text(value) -> str:
    return str(value or '').strip()


def _norm(value) -> str:
    text = unicodedata.normalize('NFKD', _text(value).casefold())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return ' '.join(text.replace('_', ' ').split())


def _compact(value) -> str:
    return re.sub(r'[^a-z0-9]+', '', _norm(value))


def _field_key(field: TemplateField) -> str:
    label = re.sub(r'\s*#\s*\d+\s*$', '', _text(field.label))
    return _compact(field.code or label)


def _name_key(value: str) -> str:
    return _compact(re.sub(r'\s*#\s*\d+\s*$', '', _text(value)))


def extract_character_limit(field: TemplateField) -> int | None:
    text = _norm(field.instruction)
    if not text:
        return None
    patterns = (
        r'\b(?:maximo|max\.?|maximum|hasta)\s*(?:de\s*)?(\d{1,5})\s*(?:caracteres|characters)\b',
        r'\b(?:con\s+un\s+)?(?:maximo|max\.?|maximum)\s+de\s+(\d{1,5})\s*(?:caracteres|characters)\b',
        r'\b(\d{1,5})\s*(?:caracteres|characters)\s*(?:maximo|max\.?|maximum)\b',
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = int(match.group(1))
            if value > 0:
                return value
    return None


def _canonical_allowed(field: TemplateField, value: str) -> str | None:
    allowed = tuple(_text(item) for item in field.valid_values if _text(item))
    if not allowed:
        return value

    by_norm = {_norm(item): item for item in allowed}
    whole = by_norm.get(_norm(value))
    if whole is not None:
        return whole

    if '|' not in value and ';' not in value:
        return None
    parts = [part.strip() for part in re.split(r'[|;]', value) if part.strip()]
    if not parts:
        return None
    canonical: list[str] = []
    seen: set[str] = set()
    for part in parts:
        match = by_norm.get(_norm(part))
        if match is None:
            return None
        key = _norm(match)
        if key in seen:
            continue
        seen.add(key)
        canonical.append(match)
    return '|'.join(canonical)


def validate_template_value(field: TemplateField, value) -> TemplateValueValidation:
    text = _text(value)
    if not text:
        return TemplateValueValidation(False, '', 'EMPTY_VALUE')

    limit = extract_character_limit(field)
    if limit is not None and len(text) > limit:
        return TemplateValueValidation(False, '', f'MAX_CHARS_EXCEEDED:{limit}:{len(text)}')

    canonical = _canonical_allowed(field, text)
    if canonical is None:
        return TemplateValueValidation(False, '', f'VALUE_NOT_ALLOWED:{text[:160]}')
    return TemplateValueValidation(True, canonical)


def _clean_instruction(field: TemplateField, max_chars: int = 1400) -> str:
    instruction = _text(field.instruction)
    if not instruction:
        return ''
    if field.example_value:
        example_norm = _norm(field.example_value)
        lines = []
        for line in instruction.splitlines():
            stripped = re.sub(r'^\s*[-•]?\s*(?:value|valor|ejemplo|example)\s*:\s*', '', line, flags=re.I).strip()
            if stripped and _norm(stripped) == example_norm:
                continue
            lines.append(line)
        instruction = '\n'.join(lines).strip()
    if len(instruction) > max_chars:
        instruction = instruction[: max_chars - 1].rstrip() + '…'
    return instruction


def _selected_fields(
    profile: MarketplaceTemplateProfile,
    research_field_names: Iterable[str] | None,
) -> list[TemplateField]:
    requested = {_name_key(name) for name in (research_field_names or ()) if _text(name)}
    always = {
        'nombre', 'descripcion', 'marca', 'modelo', 'skudelvendedor', 'codigodebarras',
        'categoriaprimaria', 'condiciondelproducto',
        'name', 'description', 'brand', 'model', 'ean', 'categoria', 'state',
    }

    selected: list[TemplateField] = []
    for field in profile.fields:
        keys = {_field_key(field), _name_key(field.label), _name_key(field.code)}
        if requested and not (keys & requested) and not (keys & always):
            continue
        if not requested and not (keys & always):
            continue
        selected.append(field)

    selected.sort(
        key=lambda field: (
            0 if field.requirement_for('').upper() in {'REQUIRED', 'MANDATORY'} else 1,
            field.column,
        )
    )
    return selected


def _allowed_values_line(field: TemplateField, max_values: int = 80, max_chars: int = 3600) -> str:
    values = [_text(value) for value in field.valid_values if _text(value)]
    if not values:
        return ''
    shown = values[:max_values]
    rendered = ' | '.join(shown)
    if len(rendered) > max_chars:
        rendered = rendered[: max_chars - 1].rstrip(' |') + '…'
    if len(values) > len(shown) or len(' | '.join(shown)) > max_chars:
        rendered += f' [LISTA TRUNCADA; {len(values)} valores totales. El writer valida contra la lista completa.]'
    return rendered


def build_marketplace_prompt_contract(
    profile: MarketplaceTemplateProfile,
    slot: ProductSlot,
    research_field_names: Iterable[str] | None = None,
    *,
    max_chars: int = 24000,
) -> str:
    """Build per-product prompt instructions from the uploaded marketplace workbook.

    Workbook instructions are treated as output-schema rules, never as product evidence.
    The block is intentionally bounded so large marketplace reference lists cannot make
    the research prompt unreasonably large.
    """
    header = [
        '============================================================',
        'STECH MARKETPLACE TEMPLATE CONTRACT — DINÁMICO POR PRODUCTO',
        '============================================================',
        f'Marketplace: {profile.marketplace}',
        f'Hoja destino: {profile.sheet_name}',
        f'Fila producto: {slot.row}',
        f'Categoría de la fila: {slot.category or "(sin categoría explícita)"}',
        f'Identificador de entrada: {slot.identifier_type}: {slot.identifier}',
        f'Fuente de identidad en plantilla: {slot.identity_source}',
        '',
        'REGLAS DE INTERPRETACIÓN DEL EXCEL',
        '- Las instrucciones de la plantilla definen formato y restricciones de salida; NO son evidencia técnica del producto.',
        '- Los ejemplos/Value/Example son ejemplos de formato. NUNCA los copies como datos reales del producto.',
        '- Conserva valores existentes que ya sean reales y no sean placeholders; investiga/completa solo lo faltante, dudoso o inválido.',
        '- REQUIRED/MANDATORY aumenta prioridad, pero NUNCA inventes un dato para llenar un obligatorio.',
        '- Si un campo tiene VALORES PERMITIDOS, devuelve únicamente valores de esa lista; para múltiples usa |.',
        '- Si la evidencia real no puede mapearse con seguridad a un valor permitido, deja el campo vacío/no encontrado y explica la razón.',
        '- La evidencia manda sobre cualquier ejemplo. Las reglas de la plantilla mandan sobre estilo/formato del campo.',
        '- Cualquier especificación verificada que no tenga columna adecuada debe conservarse como especificación adicional/evidencia, no perderse.',
        '',
        'CAMPOS RELEVANTES DE ESTA PLANTILLA',
    ]
    text = '\n'.join(header)

    fields = _selected_fields(profile, research_field_names)
    omitted = 0
    for field in fields:
        requirement = field.requirement_for(slot.category).upper() or 'OPTIONAL'
        existing = _text(slot.existing_values.get(field.code))
        existing_is_real = bool(existing) and not is_placeholder_value(field, existing)
        instruction = _clean_instruction(field)
        allowed = _allowed_values_line(field)
        limit = extract_character_limit(field)

        block = [
            '',
            f'CAMPO: {field.label or field.code}',
            f'Código interno: {field.code}',
            f'Obligatoriedad: {requirement}',
        ]
        if field.group:
            block.append(f'Grupo: {field.group}')
        if instruction:
            block.append('INSTRUCCIÓN REAL DE LA PLANTILLA:')
            block.append(instruction)
        if limit is not None:
            block.append(f'LÍMITE DETERMINÍSTICO: máximo {limit} caracteres.')
        if field.example_value:
            block.append(f'EJEMPLO DE FORMATO — NO COPIAR COMO DATO: {field.example_value}')
        if allowed:
            block.append(f'VALORES PERMITIDOS: {allowed}')
        if existing_is_real:
            block.append(f'VALOR EXISTENTE VALIDADO/PRESERVAR: {existing}')

        candidate = text + '\n' + '\n'.join(block)
        if len(candidate) > max(2000, int(max_chars)):
            omitted += 1
            continue
        text = candidate

    if omitted:
        text += f'\n\n{omitted} campo(s) adicionales omitidos del prompt por límite de tamaño; el writer mantiene validación determinística sobre el Excel completo.'
    return text.strip()
