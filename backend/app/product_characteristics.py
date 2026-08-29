from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

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


@dataclass
class ProductIntelligenceResult:
    identity: CanonicalIdentity
    specifications: list[MasterSpecification] = field(default_factory=list)
    evidence_errors: list[str] = field(default_factory=list)
    critical_errors: list[str] = field(default_factory=list)
    qa_ready: bool = False


def resolve_characteristics_input(
    template_path: Path,
    manual_identifier: str | None = None,
) -> CharacteristicsInput:
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
