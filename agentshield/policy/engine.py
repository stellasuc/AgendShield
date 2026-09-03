"""Event-driven policy evaluation and structured decisions."""

from __future__ import annotations

from agentshield.policy.dependency_index import DependencyIndex
from agentshield.policy.rules import (
    Decision,
    EffectivePolicySet,
    Intervention,
    PolicyDecision,
)
from agentshield.runtime.lifecycle import LifecycleEvent
from agentshield.state.diff import StateDiff
from agentshield.state.models import ComplianceState
from agentshield.verifier.deterministic import DeterministicVerifier
from dataclasses import replace


class DeterministicPolicyEngine:
    def __init__(
        self,
        policy_set: EffectivePolicySet,
        verifier: DeterministicVerifier | None = None,
        *,
        verify_every_event: bool = False,
    ) -> None:
        self.policy_set = policy_set
        self.index = DependencyIndex(policy_set)
        self.verifier = verifier or DeterministicVerifier()
        self.verify_every_event = verify_every_event

    def decide(self, event: LifecycleEvent, state: ComplianceState, diff: StateDiff) -> PolicyDecision:
        rules = self.index.affected_rules(event, diff)
        if not rules:
            decision = PolicyDecision(
                decision=Decision.ALLOW,
                event_id=event.event_id,
                explanation="No compliance-relevant rule affected; verification skipped",
                verification_skipped=True,
            )
            return self._with_counterfactual_work(decision, event, state, rules)

        evaluations = tuple(self.verifier.verify(rule, event, state) for rule in rules)
        activated = tuple(result for result in evaluations if result.applicable)
        violated = tuple(result for result in activated if not result.passed)
        if not violated:
            decision = PolicyDecision(
                decision=Decision.ALLOW,
                event_id=event.event_id,
                activated_rules=tuple(item.rule.rule_id for item in activated),
                regulation_sources=tuple(
                    dict.fromkeys(source for item in activated for source in item.rule.sources)
                ),
                explanation="Applicable rules passed deterministic verification",
                rules_evaluated=len(evaluations),
            )
            return self._with_counterfactual_work(decision, event, state, rules)

        controlling = max(
            (item.rule for item in violated),
            key=lambda rule: (rule.intervention.restrictiveness, int(rule.severity)),
        )
        decision = _decision_for(controlling.intervention)
        sources = tuple(dict.fromkeys(source for item in violated for source in item.rule.sources))
        decision = PolicyDecision(
            decision=decision,
            event_id=event.event_id,
            activated_rules=tuple(item.rule.rule_id for item in activated),
            violated_rules=tuple(item.rule.rule_id for item in violated),
            regulation_sources=sources,
            risk_level=max(item.rule.severity for item in violated),
            explanation="; ".join(f"{item.rule.rule_id}: {item.explanation}" for item in violated),
            required_intervention=controlling.intervention,
            rules_evaluated=len(evaluations),
        )
        return self._with_counterfactual_work(decision, event, state, rules)

    def _with_counterfactual_work(
        self,
        decision: PolicyDecision,
        event: LifecycleEvent,
        state: ComplianceState,
        selected_rules: tuple,
    ) -> PolicyDecision:
        if not self.verify_every_event:
            return decision
        selected_ids = {rule.rule_id for rule in selected_rules}
        # Deliberately evaluate irrelevant rules but discard their outcomes. This
        # preserves behavior while measuring the cost of a naive every-event gate.
        for rule in self.policy_set.rules:
            if rule.rule_id not in selected_ids:
                self.verifier.verify(rule, event, state)
        return replace(
            decision,
            verification_skipped=False,
            rules_evaluated=len(self.policy_set.rules),
        )


def _decision_for(intervention: Intervention) -> Decision:
    if intervention in {Intervention.REDACT, Intervention.AGGREGATE}:
        return Decision.REPAIR
    if intervention == Intervention.REQUIRE_CONSENT:
        return Decision.REQUIRE_CONSENT
    if intervention == Intervention.REQUIRE_APPROVAL:
        return Decision.REQUIRE_APPROVAL
    if intervention == Intervention.REPLAN:
        return Decision.REPLAN
    if intervention == Intervention.AUDIT_ONLY:
        return Decision.AUDIT_ONLY
    return Decision.BLOCK
