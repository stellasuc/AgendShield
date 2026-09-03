from __future__ import annotations

import json

from agentshield.audit.logger import AuditLogger
from agentshield.policy.engine import DeterministicPolicyEngine
from agentshield.policy.rules import Decision
from agentshield.runtime.harness import ComplianceHarness
from agentshield.runtime.lifecycle import EventType, LifecycleEvent
from agentshield.state.models import ComplianceState, DataObject


def _harness(tmp_path, policy_set, *, max_repairs=2, object_count=1):
    state = ComplianceState("run")
    for index in range(object_count):
        name = "raw" if index == 0 else f"raw-{index}"
        state.data_objects[name] = DataObject(name, contains_personal_data=True, source="db")
    return ComplianceHarness(
        DeterministicPolicyEngine(policy_set),
        state,
        AuditLogger(tmp_path),
        max_repair_attempts=max_repairs,
    )


def _event(object_ids=("raw",)):
    return LifecycleEvent(
        trajectory_id="run",
        sequence=1,
        event_type=EventType.EXTERNAL_TRANSFER,
        actor="agent",
        input={"email": "alice@example.com", "phone": "+1-555-0100"},
        data_object_ids=object_ids,
        recipient="partner",
        purpose="statistics",
        metadata={
            "recipient_type": "external",
            "is_minimized": False,
            "payload": "alice@example.com",
        },
    )


def test_repair_is_reverified_and_lineage_preserved(tmp_path, policy_set) -> None:
    harness = _harness(tmp_path, policy_set)
    result = harness.enforce(_event())
    assert result.outcome == Decision.ALLOW
    assert result.repair_attempts == 1
    assert [item.decision for item in result.decisions] == [Decision.REPAIR, Decision.ALLOW]
    assert result.final_event is not None
    assert result.final_event.replaces_event_id == result.original_event.event_id
    assert harness.state.violations[0]["rule_ids"] == ["TEST_MINIMIZATION"]
    derived_id = result.final_event.data_object_ids[0]
    assert harness.state.data_objects[derived_id].contains_personal_data is False
    assert harness.manager.lineage.trace_origins(derived_id) == ("raw",)


def test_invalid_aggregate_repair_fails_closed(tmp_path, policy_set) -> None:
    harness = _harness(tmp_path, policy_set, object_count=2)
    result = harness.enforce(_event(("raw", "raw-1")))
    assert result.outcome == Decision.BLOCK
    assert result.final_event is None


def test_repair_limit_is_enforced(tmp_path, policy_set) -> None:
    result = _harness(tmp_path, policy_set, max_repairs=0).enforce(_event())
    assert result.outcome == Decision.BLOCK
    assert result.repair_attempts == 0


def test_audit_redacts_payload_and_preserves_source(tmp_path, policy_set) -> None:
    harness = _harness(tmp_path, policy_set)
    harness.enforce(_event())
    raw_log = (tmp_path / "run.jsonl").read_text(encoding="utf-8")
    assert "alice@example.com" not in raw_log
    assert "+1-555-0100" not in raw_log
    assert "[REDACTED]" in raw_log
    assert '"recipient": "partner"' not in raw_log
    records = harness.audit.read("run")
    assert records[0]["regulation_sources"][0]["article"] == "T-1"
    assert all(AuditLogger.verify(record) for record in records)
    assert records[0]["event"]["input_fingerprint"]["sha256"]


def test_audit_detects_record_tampering(tmp_path, policy_set) -> None:
    harness = _harness(tmp_path, policy_set)
    harness.enforce(_event())
    record = dict(harness.audit.read("run")[0])
    record["decision"] = "ALLOW"
    assert not AuditLogger.verify(record)


def test_decision_is_reproducible_from_same_normalized_facts(policy_set) -> None:
    state = ComplianceState("run")
    state.data_objects["raw"] = DataObject("raw", contains_personal_data=True)
    engine = DeterministicPolicyEngine(policy_set)
    from agentshield.state.diff import StateDiff

    first = engine.decide(_event(), state, StateDiff())
    second = engine.decide(_event(), state, StateDiff())
    assert first.decision == second.decision
    assert first.violated_rules == second.violated_rules
    assert first.required_intervention == second.required_intervention
