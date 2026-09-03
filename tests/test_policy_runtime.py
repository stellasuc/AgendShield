from __future__ import annotations

from dataclasses import replace

from agentshield.policy.dependency_index import DependencyIndex
from agentshield.policy.engine import DeterministicPolicyEngine
from agentshield.policy.rules import Decision, EffectivePolicySet, Intervention, Operator, Predicate
from agentshield.runtime.lifecycle import EventType, LifecycleEvent
from agentshield.state.diff import StateDiff
from agentshield.state.models import ComplianceState, DataObject


def _event(event_type=EventType.EXTERNAL_TRANSFER, **metadata) -> LifecycleEvent:
    return LifecycleEvent(
        trajectory_id="run",
        sequence=1,
        event_type=event_type,
        actor="agent",
        data_object_ids=("raw",),
        recipient="partner",
        purpose="statistics",
        metadata=metadata,
    )


def _state() -> ComplianceState:
    state = ComplianceState("run")
    state.data_objects["raw"] = DataObject("raw", contains_personal_data=True)
    return state


def test_unrelated_event_is_skipped(policy_set) -> None:
    event = LifecycleEvent("run", 1, EventType.PLAN_GENERATED, "agent")
    decision = DeterministicPolicyEngine(policy_set).decide(event, _state(), StateDiff())
    assert decision.decision == Decision.ALLOW
    assert decision.verification_skipped
    assert decision.rules_evaluated == 0


def test_external_transfer_is_always_checked(policy_set) -> None:
    rules = DependencyIndex(policy_set).affected_rules(_event(recipient_type="external", is_minimized=False), StateDiff())
    assert [rule.rule_id for rule in rules] == ["TEST_MINIMIZATION"]


def test_unsafe_transfer_requests_repair(policy_set) -> None:
    event = _event(recipient_type="external", is_minimized=False)
    decision = DeterministicPolicyEngine(policy_set).decide(event, _state(), StateDiff())
    assert decision.decision == Decision.REPAIR
    assert decision.required_intervention == Intervention.AGGREGATE
    assert decision.violated_rules == ("TEST_MINIMIZATION",)


def test_safe_minimized_transfer_is_allowed(policy_set) -> None:
    decision = DeterministicPolicyEngine(policy_set).decide(
        _event(recipient_type="external", is_minimized=True), _state(), StateDiff()
    )
    assert decision.decision == Decision.ALLOW
    assert decision.activated_rules == ("TEST_MINIMIZATION",)


def test_unknown_requirement_fails_closed(policy_set) -> None:
    decision = DeterministicPolicyEngine(policy_set).decide(
        _event(recipient_type="external"), _state(), StateDiff()
    )
    assert decision.decision == Decision.REPAIR
    assert "Unknown required predicates" in decision.explanation


def test_unknown_personal_data_does_not_equal_false(policy_set) -> None:
    state = ComplianceState("run")
    state.data_objects["raw"] = DataObject("raw")
    decision = DeterministicPolicyEngine(policy_set).decide(
        _event(recipient_type="external", is_minimized=False), state, StateDiff()
    )
    assert decision.decision == Decision.ALLOW
    assert decision.activated_rules == ()


def test_side_effect_tool_call_and_trust_response_force_stage_lookup(minimization_rule) -> None:
    tool_rule = replace(minimization_rule, rule_id="TOOL", lifecycle_stages=frozenset({EventType.TOOL_CALL}))
    response_rule = replace(
        minimization_rule, rule_id="RESPONSE", lifecycle_stages=frozenset({EventType.RESPONSE_GENERATED})
    )
    index = DependencyIndex(EffectivePolicySet((tool_rule, response_rule), ("TEST",)))
    tool = _event(EventType.TOOL_CALL, side_effectful=True)
    response = _event(EventType.RESPONSE_GENERATED, trust_boundary=True)
    assert [rule.rule_id for rule in index.affected_rules(tool, StateDiff())] == ["TOOL"]
    assert [rule.rule_id for rule in index.affected_rules(response, StateDiff())] == ["RESPONSE"]


def test_memory_and_log_writes_force_stage_lookup(minimization_rule) -> None:
    memory = replace(minimization_rule, rule_id="MEM", lifecycle_stages=frozenset({EventType.MEMORY_WRITE}))
    log = replace(minimization_rule, rule_id="LOG", lifecycle_stages=frozenset({EventType.LOG_WRITE}))
    index = DependencyIndex(EffectivePolicySet((memory, log), ("TEST",)))
    assert [rule.rule_id for rule in index.affected_rules(_event(EventType.MEMORY_WRITE), StateDiff())] == ["MEM"]
    assert [rule.rule_id for rule in index.affected_rules(_event(EventType.LOG_WRITE), StateDiff())] == ["LOG"]


def test_dependency_index_accepts_list_valued_predicate(minimization_rule) -> None:
    rule = replace(
        minimization_rule,
        requirements=(Predicate("event.recipient_type", Operator.IN, ["internal", "external"]),),
    )
    index = DependencyIndex(EffectivePolicySet((rule,), ("TEST",)))
    assert index.affected_rules(_event(recipient_type="external"), StateDiff())[0].rule_id == "TEST_MINIMIZATION"


def test_matching_consent_allows_and_unrelated_consent_does_not(minimization_rule) -> None:
    consent_rule = replace(
        minimization_rule,
        rule_id="CONSENT",
        requirements=(Predicate("authorization.consent", Operator.EQ, True),),
        intervention=Intervention.REQUIRE_CONSENT,
    )
    engine = DeterministicPolicyEngine(EffectivePolicySet((consent_rule,), ("TEST",)))
    state = _state()
    from agentshield.state.manager import ComplianceStateManager

    ComplianceStateManager(state).apply(
        LifecycleEvent(
            "run",
            1,
            EventType.CONSENT_UPDATE,
            "user",
            data_object_ids=("raw",),
            recipient="other-partner",
            purpose="statistics",
            metadata={"consent_id": "c1", "authorized_event_type": "EXTERNAL_TRANSFER"},
        )
    )
    event = _event(recipient_type="external", is_minimized=False)
    assert engine.decide(event, state, StateDiff()).decision == Decision.REQUIRE_CONSENT
    ComplianceStateManager(state).apply(
        LifecycleEvent(
            "run",
            2,
            EventType.CONSENT_UPDATE,
            "user",
            data_object_ids=("raw",),
            recipient="partner",
            purpose="statistics",
            metadata={"consent_id": "c2", "authorized_event_type": "EXTERNAL_TRANSFER"},
        )
    )
    assert engine.decide(event, state, StateDiff()).decision == Decision.ALLOW
