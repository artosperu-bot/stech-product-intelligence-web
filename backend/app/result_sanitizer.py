from __future__ import annotations

import json
import re
from typing import Any

_MARKDOWN_LINK_RE = re.compile(r"^\s*\[([^\]]+)\]\((https?://[^)]+)\)\s*$", re.IGNORECASE)
_RAW_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def normalize_url_value(value: str) -> str:
    """Return a clean absolute URL when ChatGPT wrapped it as a Markdown link."""
    text = str(value or "").strip()
    match = _MARKDOWN_LINK_RE.match(text)
    if match:
        target = match.group(2).strip()
        return target if _RAW_URL_RE.match(target) else text
    return text


def sanitize_research_value(value: Any) -> Any:
    """Recursively normalize URL-like string values without changing the JSON contract."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(item, str) and ("url" in str(key).casefold() or "link" in str(key).casefold()):
                cleaned[str(key)] = normalize_url_value(item)
            else:
                cleaned[str(key)] = sanitize_research_value(item)
        return cleaned
    if isinstance(value, list):
        return [sanitize_research_value(item) for item in value]
    return value


def sanitize_research_result(result: Any) -> Any:
    """Normalize structured results and JSON-string results returned by ChatGPT."""
    if not isinstance(result, str):
        return sanitize_research_value(result)

    text = result.strip()
    try:
        parsed = json.loads(text)
    except Exception:
        return result

    cleaned = sanitize_research_value(parsed)
    return json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"))
