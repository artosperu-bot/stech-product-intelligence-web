from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import json

@dataclass
class ProgressEvent:
    percent: int
    step: str
    message: str
    category: str = 'PROCESO'
    detail: str = ''

    def to_dict(self) -> dict:
        return {
            'type': 'progress',
            'percent': max(0, min(100, int(self.percent))),
            'step': self.step,
            'message': self.message,
            'category': self.category,
            'detail': self.detail,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }


def encode_ndjson(payload: dict) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
