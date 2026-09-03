from __future__ import annotations

from agentshield.policy.engine import DeterministicPolicyEngine
from agentshield.runtime.lifecycle import EventType, LifecycleEvent
from agentshield.shield import AgentShield
from agentshield.shield_agent import ShieldAgent
from agentshield.state.diff import StateDiff
from agentshield.state.models import ComplianceState, DataObject


def test_shield_agent_creates_action_circuits_and_fail_closed_plan():
    shield = AgentShield(("GDPR",))
    state = ComplianceState("shield-agent-trace")
    state.data_objects["customer-record"] = DataObject(
        object_id="customer-record",
        contains_personal_data=True,
        attributes={"is_minimized": False},
    )
    event = LifecycleEvent(
        trajectory_id="shield-agent-trace",
        sequence=1,
        event_type=EventType.EXTERNAL_TRANSFER,
        actor="web_task_agent",
        tool="suitecrm.send_email",
        data_object_ids=("customer-record",),
        recipient="partner@example.test",
        purpose="customer_service",
        metadata={
            "recipient_type": "external",
            "is_minimized": False,
            "side_effectful": True,
        },
    )
    diff = StateDiff(frozenset({"event.recipient", "event.is_minimized", "object.contains_personal_data"}))
    engine = DeterministicPolicyEngine(shield.policy_set)
    decision = engine.decide(event, state, diff)

    plan = ShieldAgent(shield.policy_set, engine.verifier).shield(event, state, diff, decision)

    assert plan.action == "suitecrm.send_email"
    assert plan.circuits
    assert all(circuit.formula.startswith("ALWAYS(") for circuit in plan.circuits)
    assert any(item.truth_value == "FALSE" for circuit in plan.circuits for item in circuit.assignments)
    assert plan.operations[-1].operation == "Generate shielding plan"
    assert plan.audit_view()["probabilistic_weights"] == "not_implemented_deterministic_fail_closed"
