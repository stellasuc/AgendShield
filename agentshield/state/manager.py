"""Apply lifecycle events as incremental state transitions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, fields, replace
from typing import Any, TYPE_CHECKING
from time import perf_counter

from agentshield.lineage.models import TransformationType
from agentshield.lineage.tracker import DataLineageTracker
from agentshield.runtime.lifecycle import EventType, LifecycleEvent
from agentshield.state.diff import StateDiff
from agentshield.state.models import (
    ApprovalRecord,
    ComplianceState,
    ConsentRecord,
    DataClassification,
    DataObject,
)

if TYPE_CHECKING:
    from agentshield.detectors.base import Detector


class ComplianceStateManager:
    def __init__(self, state: ComplianceState, detector: "Detector | None" = None) -> None:
        self.state = state
        self.lineage = DataLineageTracker(state)
        self.detector = detector
        self.detector_calls = 0
        self.detector_latency_ms = 0.0

    def apply(self, event: LifecycleEvent) -> StateDiff:
        """Apply an event atomically, restoring state if normalization fails."""
        snapshot = deepcopy(self.state)
        try:
            return self._apply(event)
        except Exception:
            for state_field in fields(ComplianceState):
                setattr(self.state, state_field.name, getattr(snapshot, state_field.name))
            raise

    def _apply(self, event: LifecycleEvent) -> StateDiff:
        if event.trajectory_id != self.state.trajectory_id:
            raise ValueError("Event trajectory does not match compliance state")
        last_sequence = int(self.state.audit_metadata.get("last_sequence", -1))
        if event.sequence <= last_sequence:
            raise ValueError(
                f"Event sequence must increase monotonically (last={last_sequence}, got={event.sequence})"
            )
        changed: set[str] = set()
        changed_objects: dict[str, frozenset[str]] = {}

        if event.event_type == EventType.USER_REQUEST:
            for key, value in {"purpose": event.purpose, **event.metadata.get("task_context", {})}.items():
                if self.state.task_context.get(key) != value:
                    self.state.task_context[key] = value
                    changed.add(f"task_context.{key}")

        if event.event_type == EventType.POLICY_CONTEXT_UPDATE:
            for key, value in event.metadata.get("policy_context", {}).items():
                if self.state.policy_context.get(key) != value:
                    self.state.policy_context[key] = value
                    changed.add(f"policy_context.{key}")

        object_spec = event.metadata.get("data_object")
        if object_spec:
            obj = self._data_object(object_spec)
            self._detect_into(obj, self._event_content(event), event)
            if obj.object_id in self.state.data_objects:
                raise ValueError(f"Data object already exists: {obj.object_id}")
            self.state.data_objects[obj.object_id] = obj
            fields = frozenset(asdict(obj))
            changed_objects[obj.object_id] = fields
            changed.update(f"object.{field}" for field in fields)

        lineage_spec = event.metadata.get("lineage")
        if lineage_spec:
            target = self.lineage.transform(
                lineage_spec["source_object_id"],
                lineage_spec["target_object_id"],
                TransformationType(lineage_spec["transformation"]),
                event.event_id,
                preserves_personal_data=lineage_spec.get("preserves_personal_data"),
                confidence=float(lineage_spec.get("confidence", 1.0)),
                purpose=event.purpose,
            )
            self._detect_into(target, self._event_content(event), event)
            if self.detector is not None and self.state.lineage_edges:
                self.state.lineage_edges[-1] = replace(
                    self.state.lineage_edges[-1],
                    preserves_personal_data=target.contains_personal_data,
                )
            fields = frozenset(asdict(target))
            changed_objects[target.object_id] = fields
            changed.update(f"object.{field}" for field in fields)
            changed.add("lineage")

        if event.event_type == EventType.CONSENT_UPDATE:
            record = ConsentRecord(
                consent_id=event.metadata["consent_id"],
                data_object_ids=frozenset(event.data_object_ids),
                purpose=event.purpose or "",
                recipient=event.recipient,
                separate=bool(event.metadata.get("separate", False)),
                granted=bool(event.metadata.get("granted", True)),
                event_type=event.metadata.get("authorized_event_type"),
            )
            self.state.consents[record.consent_id] = record
            changed.add("authorization.consent")

        if event.event_type == EventType.HUMAN_APPROVAL:
            record = ApprovalRecord(
                approval_id=event.metadata["approval_id"],
                event_type=event.metadata["approved_event_type"],
                purpose=event.purpose,
                recipient=event.recipient,
                data_object_ids=frozenset(event.data_object_ids),
                approved=bool(event.metadata.get("approved", True)),
            )
            self.state.approvals[record.approval_id] = record
            changed.add("authorization.approval")

        # Event facts are ephemeral but must drive affected-rule lookup.
        for key in (
            "recipient_type",
            "is_minimized",
            "side_effectful",
            "trust_boundary",
            "has_lawful_basis",
            "purpose_compatible",
            "special_category_condition_confirmed",
            "retention_bounded",
            "recipient_disclosed",
            "recipient_notified",
            "specific_purpose",
            "strictly_necessary",
            "protective_measures_confirmed",
            "cross_border",
            "cross_border_mechanism_confirmed",
        ):
            if key in event.metadata:
                changed.add(f"event.{key}")
        if event.recipient is not None:
            changed.add("event.recipient")
        if event.purpose is not None:
            changed.add("event.purpose")

        self.state.audit_metadata["events_seen"] = int(self.state.audit_metadata.get("events_seen", 0)) + 1
        self.state.audit_metadata["last_sequence"] = event.sequence
        return StateDiff(
            changed_variables=frozenset(changed),
            changed_objects=changed_objects,
        )

    @staticmethod
    def _data_object(spec: dict[str, Any]) -> DataObject:
        payload = dict(spec)
        classification = payload.get("classification", "UNKNOWN")
        if isinstance(classification, str):
            payload["classification"] = DataClassification[classification.upper()]
        return DataObject(**payload)

    @staticmethod
    def _event_content(event: LifecycleEvent) -> Any:
        if "data_payload" in event.metadata:
            return event.metadata["data_payload"]
        if event.event_type in {EventType.TOOL_RESULT, EventType.RESPONSE_GENERATED}:
            return event.output
        return event.input

    def _detect_into(self, obj: DataObject, content: Any, event: LifecycleEvent) -> None:
        if self.detector is None or content is None:
            return
        from agentshield.detectors.sensitive_data import regulation_candidate_mappings

        detector_started = perf_counter()
        result = self.detector.detect(
            content,
            context={"event_type": event.event_type.value, "purpose": event.purpose},
        )
        self.detector_latency_ms += (perf_counter() - detector_started) * 1000
        self.detector_calls += 1
        obj.contains_personal_data = result.contains_personal_data
        obj.contains_sensitive_data = result.contains_sensitive_personal_data
        obj.classification = (
            DataClassification.SENSITIVE
            if result.contains_sensitive_personal_data
            else DataClassification.PERSONAL
            if result.contains_personal_data
            else DataClassification.NON_PERSONAL
        )
        obj.categories = list(result.categories)
        obj.sensitive_categories = list(result.sensitive_categories)
        obj.detection_confidence = result.confidence
        obj.detectors = list(result.detectors)
        obj.attributes.update(regulation_candidate_mappings(result))
        obj.attributes["detection_content_sha256"] = result.content_sha256
        obj.attributes["detection_evidence"] = [
            {
                "category": item.category,
                "path": item.path,
                "detector": item.detector,
                "confidence": item.confidence,
                "reason": item.reason,
            }
            for item in result.evidence
        ]
