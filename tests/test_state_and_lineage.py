from __future__ import annotations

from agentshield.lineage.models import TransformationType
from agentshield.lineage.tracker import DataLineageTracker
from agentshield.runtime.lifecycle import EventType, LifecycleEvent
from agentshield.state.manager import ComplianceStateManager
from agentshield.state.models import ComplianceState, DataClassification, DataObject
import pytest


def test_unknown_is_not_false() -> None:
    obj = DataObject("unknown")
    assert obj.contains_personal_data is None
    assert obj.contains_personal_data is not False
    assert obj.classification == DataClassification.UNKNOWN


def test_objects_do_not_contaminate_each_other() -> None:
    state = ComplianceState("run")
    state.data_objects["personal"] = DataObject("personal", contains_personal_data=True)
    state.data_objects["public"] = DataObject("public", classification=DataClassification.NON_PERSONAL)
    assert state.data_objects["personal"].contains_personal_data is True
    assert state.data_objects["public"].contains_personal_data is False


def test_sensitive_classification_implies_personal() -> None:
    obj = DataObject("sensitive", contains_sensitive_data=True)
    assert obj.classification == DataClassification.SENSITIVE
    assert obj.contains_personal_data is True


def test_aggregate_creates_new_object_and_preserves_source() -> None:
    state = ComplianceState("run")
    state.data_objects["raw"] = DataObject(
        "raw",
        contains_personal_data=True,
        contains_sensitive_data=True,
        source="db",
        provenance=["db"],
    )
    tracker = DataLineageTracker(state)
    derived = tracker.transform("raw", "count", TransformationType.AGGREGATE, "event-1")
    assert state.data_objects["raw"].contains_sensitive_data is True
    assert derived.contains_personal_data is False
    assert derived.contains_sensitive_data is False
    assert derived.object_id != "raw"
    assert tracker.trace_origins("count") == ("raw",)
    assert state.lineage_edges[0].preserves_personal_data is False


def test_state_diff_tracks_object_fields() -> None:
    state = ComplianceState("run")
    diff = ComplianceStateManager(state).apply(
        LifecycleEvent(
            trajectory_id="run",
            sequence=1,
            event_type=EventType.TOOL_RESULT,
            actor="tool",
            metadata={
                "data_object": {
                    "object_id": "result",
                    "contains_personal_data": True,
                    "source": "tool",
                }
            },
        )
    )
    assert "object.contains_personal_data" in diff.changed_variables
    assert "result" in diff.changed_objects


def test_failed_normalization_rolls_back_partial_state() -> None:
    state = ComplianceState("run")
    manager = ComplianceStateManager(state)
    with pytest.raises(KeyError, match="Unknown lineage source"):
        manager.apply(
            LifecycleEvent(
                trajectory_id="run",
                sequence=1,
                event_type=EventType.TOOL_RESULT,
                actor="tool",
                metadata={
                    "data_object": {"object_id": "partial", "contains_personal_data": True},
                    "lineage": {
                        "source_object_id": "missing",
                        "target_object_id": "derived",
                        "transformation": "COPY",
                    },
                },
            )
        )
    assert state.data_objects == {}
    assert state.audit_metadata == {"events_seen": 0}


def test_consent_is_scoped_to_object_purpose_and_recipient() -> None:
    state = ComplianceState("run")
    manager = ComplianceStateManager(state)
    manager.apply(
        LifecycleEvent(
            trajectory_id="run",
            sequence=1,
            event_type=EventType.CONSENT_UPDATE,
            actor="user",
            data_object_ids=("object-a",),
            purpose="billing",
            recipient="processor-a",
            metadata={"consent_id": "c1", "granted": True},
        )
    )
    assert state.matching_consent(("object-a",), "billing", "processor-a")
    assert not state.matching_consent(("object-b",), "billing", "processor-a")
    assert not state.matching_consent(("object-a",), "marketing", "processor-a")
    assert not state.matching_consent(("object-a", "object-b"), "billing", "processor-a")


def test_approval_is_scoped_to_operation() -> None:
    state = ComplianceState("run")
    manager = ComplianceStateManager(state)
    manager.apply(
        LifecycleEvent(
            trajectory_id="run",
            sequence=1,
            event_type=EventType.HUMAN_APPROVAL,
            actor="reviewer",
            data_object_ids=("object-a",),
            purpose="transfer",
            recipient="partner",
            metadata={"approval_id": "a1", "approved_event_type": "EXTERNAL_TRANSFER"},
        )
    )
    assert state.matching_approval("EXTERNAL_TRANSFER", ("object-a",), "transfer", "partner")
    assert not state.matching_approval("MEMORY_WRITE", ("object-a",), "transfer", "partner")
