from __future__ import annotations

import inspect
from typing import Any, Callable

_REMOTE_TYPE = "__stech_remote_type__"


def encode_remote_value(value: Any) -> Any:
    if callable(value):
        return {
            _REMOTE_TYPE: "callable",
            "name": getattr(value, "__name__", value.__class__.__name__),
            "async": bool(inspect.iscoroutinefunction(value)),
        }
    if isinstance(value, dict):
        return {str(key): encode_remote_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode_remote_value(item) for item in value]
    return value


def decode_remote_value(value: Any, callback_factory: Callable[[str, bool], Callable]) -> Any:
    if isinstance(value, dict):
        if value.get(_REMOTE_TYPE) == "callable":
            return callback_factory(str(value.get("name") or "callback"), bool(value.get("async")))
        return {key: decode_remote_value(item, callback_factory) for key, item in value.items()}
    if isinstance(value, list):
        return [decode_remote_value(item, callback_factory) for item in value]
    return value
