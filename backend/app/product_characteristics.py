from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from .marketplace_template import (
    MarketplaceTemplateProfile,
    ProductSlot,
    analyze_marketplace_template,
    choose_manual_slot,
    classify_identifier,
)
from .product_evidence import MasterSpecification, parse_master_specifications, validate_master_specifications
from .product_identity import (
    CanonicalIdentity,
    canonical_identity_from_raw,
    choose_research_identifier,
    enrich_identity_from_workbook_evidence,
    extract_identity_candidates,
)


@dataclass
class CharacteristicsInput:
    input_mode: str
    identifier: str
    identifier_type: str
    source_row: int | None = None
    marketplace: str = ''


@dataclass
class ProductIntelligenceResult:
    identity: CanonicalIdentity
    specifications: list[MasterSpecification] = field(default_factory=list)
    evidence_errors: list[str] = field(default_factory=list)
    critical_errors: list[str] = field(default_factory=list)
    qa_ready: bool = False


def _manual_slot(profile: MarketplaceTemplateProfile, identifier: str) -> ProductSlot:
    matched = choose_manual_slot(profile, identifier)
    if matched is not None:
        return matched
    if profile.products:
        raise ValueError('MANUAL_IDENTIFIER_ROW_NOT_FOUND')
    category = profile.category_options[0] if len(profile.category_options) == 1 else ''
    return ProductSlot(
        row=profile.data_start_row,
        identifier=str(identifier or '').strip(),
        identifier_type=classify_identifier(identifier),
        category=category,
        existing_values={},
        identity_source='manual',
    )


def resolve_characteristics_slots(
    template_path: Path,
    manual_identifier: str | None = None,
) -> tuple[MarketplaceTemplateProfile, list[ProductSlot]]:
    profile = analyze_marketplace_template(template_path)
    # Real Falabella marketplace templates contain instruction/requirement rows before
    # the mapped row. Compact historical test/legacy sheets keep the previous resolver.
    if profile.marketplace == 'falabella' and profile.header_rows[-1] < 4:
        raise ValueError('UNSUPPORTED_MARKETPLACE_TEMPLATE')
    manual = str(manual_identifier or '').strip()
    if manual:
        return profile, [_manual_slot(profile, manual)]
    if not profile.products:
        raise ValueError('IDENTITY_CANDIDATE_NOT_FOUND')
    return profile, list(profile.products)


def resolve_characteristics_input(
    template_path: Path,
    manual_identifier: str | None = None,
) -> CharacteristicsInput:
    try:
        profile, slots = resolve_characteristics_slots(template_path, manual_identifier)
        slot = slots[0]
        return CharacteristicsInput(
            'manual' if str(manual_identifier or '').strip() else 'auto',
            slot.identifier,
            slot.identifier_type,
            source_row=slot.row,
            marketplace=profile.marketplace,
        )
    except ValueError as exc:
        if str(exc) != 'UNSUPPORTED_MARKETPLACE_TEMPLATE':
            raise

    # Backward-compatible fallback for legacy/non-marketplace workbook families.
    candidates = extract_identity_candidates(template_path)
    input_mode, identifier, identifier_type = choose_research_identifier(manual_identifier, candidates)
    return CharacteristicsInput(input_mode, identifier, identifier_type)


def build_product_intelligence(
    raw: dict,
    template_path: Path,
    resolved_identifier: str,
    min_confidence: int = 80,
) -> ProductIntelligenceResult:
    identity = canonical_identity_from_raw(raw, fallback_identifier=resolved_identifier)
    # Prior workbook evidence may enrich an already resolved MPN, but it may never
    # introduce a different product when the current research did not resolve one.
    if identity.manufacturer_part_number:
        identity = enrich_identity_from_workbook_evidence(template_path, identity)
    parsed = parse_master_specifications(raw, identity)
    accepted, evidence_errors = validate_master_specifications(
        parsed,
        identity,
        min_confidence=min_confidence,
    )
    critical_errors: list[str] = []
    if not identity.brand:
        critical_errors.append('MISSING_IDENTITY:brand')
    if not identity.manufacturer_part_number:
        critical_errors.append('MISSING_IDENTITY:manufacturer_part_number')
    if not identity.commercial_model:
        critical_errors.append('MISSING_IDENTITY:commercial_model')
    return ProductIntelligenceResult(
        identity=identity,
        specifications=accepted,
        evidence_errors=evidence_errors,
        critical_errors=critical_errors,
        qa_ready=not critical_errors,
    )


def serialize_identity(identity: CanonicalIdentity) -> dict:
    return asdict(identity)
