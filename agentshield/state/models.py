"""Persistent, object-scoped compliance state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any


class DataClassification(IntEnum):
    UNKNOWN = 0
    NON_PERSONAL = 1
    PERSONAL = 2
    SENSITIVE = 3


@dataclass(slots=True)
class DataObject:
    object_id: str
    classification: DataClassification = DataClassification.UNKNOWN
    contains_personal_data: bool | None = None
    contains_sensitive_data: bool | None = None
    source: str | None = None
    purpose: str | None = None
    transformations: list[str] = field(default_factory=list)
    recipients: list[str] = field(default_factory=list)
    retention: str | None = None
    provenance: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    sensitive_categories: list[str] = field(default_factory=list)
    detection_confidence: float | None = None
    detectors: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.contains_sensitive_data is True:
            self.contains_personal_data = True
            self.classification = DataClassification.SENSITIVE
        elif self.contains_personal_data is True and self.classification < DataClassification.PERSONAL:
            self.classification = DataClassification.PERSONAL
        if self.classification == DataClassification.NON_PERSONAL:
            self.contains_personal_data = False
            self.contains_sensitive_data = False


@dataclass(frozen=True, slots=True)
class ConsentRecord:
    consent_id: str
    data_object_ids: frozenset[str]
    purpose: str
    recipient: str | None = None
    separate: bool = False
    granted: bool = True
    event_type: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def matches(
        self,
        object_ids: tuple[str, ...],
        purpose: str | None,
        recipient: str | None,
        separate: bool,
        event_type: str | None,
    ) -> bool:
        return (
            self.granted
            and bool(object_ids)
            and set(object_ids).issubset(self.data_object_ids)
            and self.purpose == purpose
            and self.recipient == recipient
            and (not separate or self.separate)
            and (event_type is None or self.event_type == event_type)
        )


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    approval_id: str
    event_type: str
    purpose: str | None
    recipient: str | None
    data_object_ids: frozenset[str]
    approved: bool = True


@dataclass(slots=True)
class ComplianceState:
    trajectory_id: str
    task_context: dict[str, Any] = field(default_factory=dict)
    policy_context: dict[str, Any] = field(default_factory=dict)
    data_objects: dict[str, DataObject] = field(default_factory=dict)
    lineage_edges: list[Any] = field(default_factory=list)
    consents: dict[str, ConsentRecord] = field(default_factory=dict)
    approvals: dict[str, ApprovalRecord] = field(default_factory=dict)
    active_obligations: dict[str, dict[str, Any]] = field(default_factory=dict)
    violations: list[dict[str, Any]] = field(default_factory=list)
    audit_metadata: dict[str, Any] = field(default_factory=lambda: {"events_seen": 0})

    def matching_consent(
        self,
        object_ids: tuple[str, ...],
        purpose: str | None,
        recipient: str | None,
        *,
        separate: bool = False,
        event_type: str | None = None,
    ) -> bool:
        return any(
            c.matches(object_ids, purpose, recipient, separate, event_type)
            for c in self.consents.values()
        )

    def matching_approval(self, event_type: str, object_ids: tuple[str, ...], purpose: str | None, recipient: str | None) -> bool:
        return any(
            a.approved
            and a.event_type == event_type
            and a.purpose == purpose
            and a.recipient == recipient
            and bool(object_ids)
            and set(object_ids).issubset(a.data_object_ids)
            for a in self.approvals.values()
        )
