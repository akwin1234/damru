"""Redaction helpers for UI logs and JSON responses."""
from __future__ import annotations

import re

_AUTH_URL_RE = re.compile(r"(?P<scheme>\b(?:socks5h?|https?|http)://)(?P<auth>[^\s/@:]+(?::[^\s/@]*)?@)", re.I)
_PASSWORD_ASSIGN_RE = re.compile(r"(?i)\b(password|passwd|token|secret|api[_-]?key)\s*=\s*([^\s]+)")


def redact(value: object) -> str:
    """Return a display-safe string with credentials removed."""
    text = str(value)
    text = _AUTH_URL_RE.sub(lambda m: f"{m.group('scheme')}***:***@", text)
    text = _PASSWORD_ASSIGN_RE.sub(lambda m: f"{m.group(1)}=***", text)
    return text


def redact_dict(data: dict[str, object]) -> dict[str, object]:
    safe: dict[str, object] = {}
    for key, value in data.items():
        if isinstance(value, str):
            safe[key] = redact(value)
        elif isinstance(value, dict):
            safe[key] = redact_dict(value)  # type: ignore[arg-type]
        elif isinstance(value, list):
            safe[key] = [redact(item) if isinstance(item, str) else item for item in value]
        else:
            safe[key] = value
    return safe
