"""Persistent side-effect transaction model."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class EffectStatus(str, Enum):
    CREATED = "CREATED"
    CHECKING = "CHECKING"
    BLOCKED = "BLOCKED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    AUTHORIZED = "AUTHORIZED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REQUIRE_HUMAN_REVIEW = "REQUIRE_HUMAN_REVIEW"


@dataclass(frozen=True, slots=True)
class EffectTransaction:
    transaction_id: str
    effect_id: str
    request_id: str
    trajectory_id: str
    capability_id: str
    original_arguments: Mapping[str, Any]
    effective_arguments: Mapping[str, Any]
    referenced_data_objects: tuple[str, ...]
    decision: str = "PENDING"
    activated_rules: tuple[str, ...] = ()
    status: EffectStatus = EffectStatus.CREATED
    created_at: str = field(default_factory=lambda: _now())
    updated_at: str = field(default_factory=lambda: _now())
    repair_parent: str | None = None
    approval_required: bool = False
    execution_attempts: int = 0
    result_metadata: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None

    def update(self, **changes: Any) -> "EffectTransaction":
        return replace(self, updated_at=_now(), **changes)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
