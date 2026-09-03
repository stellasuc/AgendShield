from __future__ import annotations

from agentshield.detectors import CompositePrivacyDetector
from agentshield.lineage.models import TransformationType
from agentshield.runtime.lifecycle import EventType, LifecycleEvent
from agentshield.state.manager import ComplianceStateManager
from agentshield.state.models import ComplianceState, DataClassification, DataObject
from examples.gdpr_demo import run_demo


def test_detector_result_creates_object_scoped_state() -> None:
    state = ComplianceState("run")
    manager = ComplianceStateManager(state, CompositePrivacyDetector())
    manager.apply(
        LifecycleEvent(
            "run",
            1,
            EventType.TOOL_RESULT,
            "database",
            output={"name": "Alice", "email": "alice@example.test"},
            metadata={"data_object": {"object_id": "customer", "source": "database"}},
        )
    )
    obj = state.data_objects["customer"]
    assert obj.classification == DataClassification.PERSONAL
    assert {"name", "email"} <= set(obj.categories)
    assert obj.detectors


def test_detector_objects_do_not_contaminate_each_other() -> None:
    state = ComplianceState("run")
    manager = ComplianceStateManager(state, CompositePrivacyDetector())
    manager.apply(
        LifecycleEvent(
            "run", 1, EventType.TOOL_RESULT, "db",
            output={"email": "alice@example.test"},
            metadata={"data_object": {"object_id": "personal"}},
        )
    )
    manager.apply(
        LifecycleEvent(
            "run", 2, EventType.TOOL_RESULT, "report",
            output={"customer_count": 1},
            metadata={"data_object": {"object_id": "public"}},
        )
    )
    assert state.data_objects["personal"].contains_personal_data is True
    assert state.data_objects["public"].contains_personal_data is False


def test_copy_propagates_personal_classification_without_new_content() -> None:
    state = ComplianceState("run")
    state.data_objects["source"] = DataObject(
        "source", contains_personal_data=True, categories=["email"], source="db"
    )
    manager = ComplianceStateManager(state, CompositePrivacyDetector())
    manager.apply(
        LifecycleEvent(
            "run", 1, EventType.TOOL_RESULT, "copy-tool",
            output=None,
            metadata={
                "lineage": {
                    "source_object_id": "source",
                    "target_object_id": "copy",
                    "transformation": TransformationType.COPY.value,
                }
            },
        )
    )
    assert state.data_objects["copy"].contains_personal_data is True
    assert state.data_objects["copy"].categories == ["email"]


def test_redacted_content_is_independently_reclassified() -> None:
    state = ComplianceState("run")
    state.data_objects["source"] = DataObject("source", contains_personal_data=True, categories=["email"])
    manager = ComplianceStateManager(state, CompositePrivacyDetector())
    manager.apply(
        LifecycleEvent(
            "run", 1, EventType.TOOL_RESULT, "redactor",
            output={"email": "[REDACTED]"},
            metadata={
                "lineage": {
                    "source_object_id": "source",
                    "target_object_id": "redacted",
                    "transformation": "REDACT",
                    "preserves_personal_data": False,
                }
            },
        )
    )
    assert state.data_objects["redacted"].classification == DataClassification.NON_PERSONAL
    assert state.data_objects["source"].classification == DataClassification.PERSONAL


def test_aggregate_is_new_object_reclassified_and_lineage_preserved(tmp_path) -> None:
    _, harness, _, result = run_demo(tmp_path)
    assert result.final_event is not None
    derived = result.final_event.data_object_ids[0]
    assert derived != "customer-records-001"
    assert harness.state.data_objects[derived].classification == DataClassification.NON_PERSONAL
    assert harness.state.data_objects[derived].detectors
    assert harness.manager.lineage.trace_origins(derived) == ("customer-records-001",)
    assert harness.state.lineage_edges[-1].preserves_personal_data is False


def test_detector_corrects_lineage_when_labeled_aggregate_still_contains_personal_data() -> None:
    state = ComplianceState("run")
    state.data_objects["source"] = DataObject("source", contains_personal_data=True)
    manager = ComplianceStateManager(state, CompositePrivacyDetector())
    manager.apply(
        LifecycleEvent(
            "run", 1, EventType.TOOL_RESULT, "bad-aggregator",
            output={"customer_count": 1, "email": "alice@example.test"},
            metadata={
                "lineage": {
                    "source_object_id": "source", "target_object_id": "unsafe-aggregate",
                    "transformation": "AGGREGATE", "preserves_personal_data": False,
                }
            },
        )
    )
    assert state.data_objects["unsafe-aggregate"].contains_personal_data is True
    assert state.lineage_edges[-1].preserves_personal_data is True
