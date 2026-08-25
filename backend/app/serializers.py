from __future__ import annotations
from dataclasses import asdict
from typing import Any

from .v30_bridge import CORE_DIR  # ensures legacy modules are importable


def serialize_preview_row(row) -> dict:
    return {
        'field': row.field,
        'value': row.value,
        'status': row.status,
        'cell': f'{row.column_letter}{row.row}',
        'confidence': row.confidence,
        'reason': row.reason,
    }


def serialize_price_offer(offer, index: int) -> dict:
    return {
        'index': int(index),
        'store': getattr(offer, 'store', ''),
        'price': getattr(offer, 'current_price', None),
        'previous_price': getattr(offer, 'previous_price', None),
        'currency': getattr(offer, 'currency', ''),
        'availability': getattr(offer, 'availability', ''),
        'seller': getattr(offer, 'seller', ''),
        'url': getattr(offer, 'url', ''),
        'match_type': getattr(offer, 'match_type', ''),
        'price_verified': bool(getattr(offer, 'price_verified', False)),
        'url_type': getattr(offer, 'url_type', ''),
        'verification_status': getattr(offer, 'verification_status', ''),
        'price_source': getattr(offer, 'price_source', ''),
        'price_anomaly': bool(getattr(offer, 'price_anomaly', False)),
        'verified_at': getattr(offer, 'verified_at', ''),
    }


def serialize_image_record(record, index: int) -> dict:
    data = asdict(record)
    data.pop('payload', None)
    data['index'] = int(index)
    data['score'] = float(getattr(record, 'score', 0) or 0)
    return data


def serialize_video_record(record, index: int) -> dict:
    data = asdict(record)
    data['index'] = int(index)
    return data
