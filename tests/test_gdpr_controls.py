from __future__ import annotations

from agentshield import AgentShield
from agentshield.policy.rules import Decision
from agentshield.runtime.lifecycle import EventType, LifecycleEvent
from agentshield.state.models import DataClassification, DataObject
from examples.gdpr_demo import run_demo


def test_excessive_raw_personal_transfer_is_repaired_and_reverified(tmp_path) -> None:
    _, harness, _, result = run_demo(tmp_path)
    assert result.outcome == Decision.ALLOW
    assert [decision.decision for decision in result.decisions] == [Decision.REPAIR, Decision.ALLOW]
    assert result.repair_attempts == 1
    assert result.decisions[0].violated_rules == ("GDPR_DATA_MINIMIZATION_001",)
    assert result.decisions[0].regulation_sources[0].article == "Articles 5(1)(c) and 25(1)-(2)"
    assert harness.state.data_objects["customer-records-001"].contains_personal_data is True


def test_safe_public_aggregate_transfer_allowed_without_false_block(tmp_path) -> None:
    shield = AgentShield(["GDPR"])
    harness = shield.create_harness("public", tmp_path)
    harness.state.data_objects["count"] = DataObject(
        "count", classification=DataClassification.NON_PERSONAL, source="aggregate"
    )
    result = harness.enforce(
        LifecycleEvent(
            "public", 1, EventType.EXTERNAL_TRANSFER, "agent",
            input={"customer_count": 42},
            data_object_ids=("count",),
            recipient="partner",
            purpose="statistics",
            metadata={"recipient_type": "external"},
        )
    )
    assert result.outcome == Decision.ALLOW
    assert result.decisions[0].violated_rules == ()


def test_missing_lawful_basis_requires_approval(tmp_path) -> None:
    shield = AgentShield(["GDPR"])
    harness = shield.create_harness("basis", tmp_path)
    harness.state.data_objects["personal"] = DataObject("personal", contains_personal_data=True)
    result = harness.enforce(
        LifecycleEvent(
            "basis", 1, EventType.EXTERNAL_TRANSFER, "agent",
            data_object_ids=("personal",), recipient="partner", purpose="support",
            metadata={
                "recipient_type": "external", "purpose_compatible": True,
                "is_minimized": True, "recipient_disclosed": True,
            },
        )
    )
    assert result.outcome == Decision.REQUIRE_APPROVAL
    assert "GDPR_LAWFUL_BASIS_001" in result.decisions[0].violated_rules


def test_unbounded_personal_memory_write_is_blocked(tmp_path) -> None:
    shield = AgentShield(["GDPR"])
    harness = shield.create_harness("memory", tmp_path)
    harness.state.data_objects["personal"] = DataObject("personal", contains_personal_data=True)
    result = harness.enforce(
        LifecycleEvent(
            "memory", 1, EventType.MEMORY_WRITE, "agent",
            input={"record_reference": "personal"}, data_object_ids=("personal",), purpose="support",
            metadata={"has_lawful_basis": True, "purpose_compatible": True, "retention_bounded": False},
        )
    )
    assert result.outcome == Decision.BLOCK
    assert result.decisions[0].required_intervention.value == "PREVENT_MEMORY_WRITE"

