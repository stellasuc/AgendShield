"""Deterministic repair strategies."""

from __future__ import annotations

from hashlib import sha256
from typing import Any
import re


def redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sensitive = {"email", "phone", "address", "identifier", "name"}
        return {
            key: ("[REDACTED]" if key.lower() in sensitive else redact_payload(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, str):
        value = re.sub(
            r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
            "[REDACTED]",
            value,
            flags=re.IGNORECASE,
        )
        return re.sub(r"(?<!\w)\+?\d[\d().\s-]{6,}\d(?!\w)", "[REDACTED]", value)
    return value


def derived_object_id(source_id: str, transformation: str, event_id: str) -> str:
    suffix = sha256(f"{source_id}:{transformation}:{event_id}".encode()).hexdigest()[:10]
    return f"{source_id}-{transformation.lower()}-{suffix}"
