"""Normalized events emitted by an agent runtime adapter."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any
from uuid import uuid4
import json
import re


class EventType(str, Enum):
    USER_REQUEST = "USER_REQUEST"
    PLAN_GENERATED = "PLAN_GENERATED"
    TOOL_CALL = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"
    EXTERNAL_TRANSFER = "EXTERNAL_TRANSFER"
    RESPONSE_GENERATED = "RESPONSE_GENERATED"
    MEMORY_WRITE = "MEMORY_WRITE"
    LOG_WRITE = "LOG_WRITE"
    CONSENT_UPDATE = "CONSENT_UPDATE"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    POLICY_CONTEXT_UPDATE = "POLICY_CONTEXT_UPDATE"
    AGENT_ERROR = "AGENT_ERROR"


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    trajectory_id: str
    sequence: int
    event_type: EventType
    actor: str
    event_id: str = field(default_factory=lambda: str(uuid4()))
    tool: str | None = None
    input: Any = None
    output: Any = None
    data_object_ids: tuple[str, ...] = ()
    recipient: str | None = None
    purpose: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    replaces_event_id: str | None = None
    parent_event_ids: tuple[str, ...] = ()
    correlation_id: str | None = None
    tool_call_id: str | None = None

    def repaired(self, **changes: Any) -> "LifecycleEvent":
        metadata = dict(changes.pop("metadata", self.metadata))
        metadata.setdefault("repair", {})
        metadata["repair"] = {
            **metadata["repair"],
            "original_event_id": self.event_id,
        }
        return replace(
            self,
            event_id=str(uuid4()),
            sequence=self.sequence + 1,
            occurred_at=datetime.now(timezone.utc),
            replaces_event_id=self.event_id,
            parent_event_ids=tuple(dict.fromkeys((*self.parent_event_ids, self.event_id))),
            metadata=metadata,
            **changes,
        )

    def audit_view(self) -> dict[str, Any]:
        """Return metadata-only payload evidence; raw inputs/outputs are never logged."""
        return {
            "event_id": self.event_id,
            "trajectory_id": self.trajectory_id,
            "sequence": self.sequence,
            "event_type": self.event_type.value,
            "actor": self.actor,
            "tool": self.tool,
            "input_fingerprint": _fingerprint(self.input),
            "output_fingerprint": _fingerprint(self.output),
            "data_object_ids": list(self.data_object_ids),
            "recipient_fingerprint": _fingerprint(self.recipient),
            "purpose": self.purpose,
            "metadata": _redact_metadata(self.metadata),
            "occurred_at": self.occurred_at.isoformat(),
            "replaces_event_id": self.replaces_event_id,
            "parent_event_ids": list(self.parent_event_ids),
            "correlation_id": self.correlation_id,
            "tool_call_id": self.tool_call_id,
        }


def _fingerprint(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    return {"sha256": sha256(encoded).hexdigest(), "bytes": len(encoded)}


def _redact_metadata(value: Any, key: str = "") -> Any:
    sensitive_fragments = ("payload", "content", "email", "phone", "address", "identifier", "secret", "token")
    if isinstance(value, dict):
        return {
            str(k): (
                "[REDACTED]"
                if any(fragment in str(k).lower() for fragment in sensitive_fragments)
                else _redact_metadata(v, str(k))
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_metadata(item, key) for item in value]
    if isinstance(value, tuple):
        return [_redact_metadata(item, key) for item in value]
    if isinstance(value, str) and (
        re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", value, re.IGNORECASE)
        or re.search(r"(?<!\w)\+?\d[\d().\s-]{6,}\d(?!\w)", value)
    ):
        return "[REDACTED]"
    return value
