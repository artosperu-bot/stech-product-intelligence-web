from __future__ import annotations

import json
import re

_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def _canonical(value) -> str | None:
    if not isinstance(value, (dict, list)):
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def extract_json_payload(text: str) -> str | None:
    """Extract one complete JSON object/array from a rendered ChatGPT assistant message.

    Returns canonical JSON only when parsing is complete. Incomplete streaming JSON is
    deliberately rejected so the worker never cuts off a response mid-generation.
    """
    raw = str(text or "").strip()
    if not raw:
        return None

    candidates = [raw]
    candidates.extend(match.group(1).strip() for match in _FENCED_JSON_RE.finditer(raw))

    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            return _canonical(json.loads(candidate))
        except Exception:
            pass

        starts = [index for index in (candidate.find("{"), candidate.find("[")) if index >= 0]
        if not starts:
            continue
        start = min(starts)
        try:
            value, end = decoder.raw_decode(candidate[start:])
        except Exception:
            continue
        tail = candidate[start + end :].strip()
        if tail and not tail.startswith("```"):
            continue
        canonical = _canonical(value)
        if canonical is not None:
            return canonical

    return None
