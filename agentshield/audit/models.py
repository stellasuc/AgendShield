from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AuditEntry:
    run_id: str
    event: dict[str, Any]
    state_diff: dict[str, Any]
    data_object_ids: tuple[str, ...]
    activated_rules: tuple[str, ...]
    regulation_sources: tuple[dict[str, str], ...]
    decision: str
    intervention: str | None
    repair: dict[str, Any] | None
    final_outcome: str
    execution_outcome: str
    latency_ms: float
    rules_evaluated: int
    verification_skipped: bool
    record_hash: str = ""
