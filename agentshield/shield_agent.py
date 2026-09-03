"""Paper-inspired ShieldAgent runtime trace built on AgentShield enforcement.

This module implements the runtime shape described in ShieldAgent: retrieve
action-relevant rule circuits, assign truth values to atomic predicates, perform
formal rule verification, and create a shielding plan.  It deliberately does not
claim to reproduce the paper's learned probabilistic circuit weights; production
decisions remain deterministic and fail closed through AgentShield's policy engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentshield.policy.dependency_index import DependencyIndex
from agentshield.policy.rules import ComplianceRule, PolicyDecision, Predicate
from agentshield.runtime.lifecycle import LifecycleEvent
from agentshield.state.diff import StateDiff
from agentshield.state.models import ComplianceState
from agentshield.verifier.deterministic import DeterministicVerifier, UNKNOWN


@dataclass(frozen=True, slots=True)
class PredicateAssignment:
    symbol: str
    variable: str
    truth_value: str
    role: str


@dataclass(frozen=True, slots=True)
class ActionRuleCircuit:
    rule_id: str
    action_types: tuple[str, ...]
    formula: str
    source_articles: tuple[str, ...]
    assignments: tuple[PredicateAssignment, ...]
    verification: str


@dataclass(frozen=True, slots=True)
class ShieldingOperation:
    operation: str
    status: str
    detail: str


@dataclass(frozen=True, slots=True)
class ShieldingPlan:
    """Payload-safe trace for a single action verification attempt."""

    event_id: str
    action: str
    circuits: tuple[ActionRuleCircuit, ...]
    operations: tuple[ShieldingOperation, ...]
    decision: str
    intervention: str | None

    def audit_view(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "action": self.action,
            "circuits": [
                {
                    "rule_id": circuit.rule_id,
                    "action_types": list(circuit.action_types),
                    "formula": circuit.formula,
                    "source_articles": list(circuit.source_articles),
                    "assignments": [
                        {
                            "symbol": item.symbol,
                            "variable": item.variable,
                            "truth_value": item.truth_value,
                            "role": item.role,
                        }
                        for item in circuit.assignments
                    ],
                    "verification": circuit.verification,
                }
                for circuit in self.circuits
            ],
            "operations": [
                {
                    "operation": operation.operation,
                    "status": operation.status,
                    "detail": operation.detail,
                }
                for operation in self.operations
            ],
            "decision": self.decision,
            "intervention": self.intervention,
            "probabilistic_weights": "not_implemented_deterministic_fail_closed",
        }


class ShieldAgent:
    """Generate paper-style shielding plans from actual runtime policy evidence."""

    def __init__(self, policy_set, verifier: DeterministicVerifier) -> None:
        self.index = DependencyIndex(policy_set)
        self.verifier = verifier

    def shield(
        self,
        event: LifecycleEvent,
        state: ComplianceState,
        diff: StateDiff,
        decision: PolicyDecision,
    ) -> ShieldingPlan:
        rules = self.index.affected_rules(event, diff)
        circuits = tuple(self._circuit(rule, event, state) for rule in rules)
        action = event.tool or event.event_type.value
        operations = (
            ShieldingOperation(
                "Retrieve relevant action rule circuits",
                "COMPLETE",
                f"{len(circuits)} 个与 {action} 相关的规则电路",
            ),
            ShieldingOperation(
                "Assign atomic predicate truth values",
                "COMPLETE",
                f"已为 {sum(len(item.assignments) for item in circuits)} 个原子谓词赋值",
            ),
            ShieldingOperation(
                "Formal verify action circuits",
                "COMPLETE",
                "确定性 LTL 风格规则核验已完成；未知必要条件按 fail-closed 处理。",
            ),
            ShieldingOperation(
                "Generate shielding plan",
                "COMPLETE",
                _decision_detail(decision),
            ),
        )
        return ShieldingPlan(
            event_id=event.event_id,
            action=action,
            circuits=circuits,
            operations=operations,
            decision=decision.decision.value,
            intervention=(decision.required_intervention.value if decision.required_intervention else None),
        )

    def _circuit(
        self,
        rule: ComplianceRule,
        event: LifecycleEvent,
        state: ComplianceState,
    ) -> ActionRuleCircuit:
        applicability = tuple(
            self._assignment(predicate, "适用条件", event, state)
            for predicate in rule.applicability
        )
        requirements = tuple(
            self._assignment(predicate, "必须满足", event, state)
            for predicate in rule.requirements
        )
        evaluation = self.verifier.verify(rule, event, state)
        return ActionRuleCircuit(
            rule_id=rule.rule_id,
            action_types=tuple(sorted(stage.value for stage in rule.lifecycle_stages)),
            formula=_formula(rule),
            source_articles=tuple(source.article for source in rule.sources),
            assignments=applicability + requirements,
            verification=("PASS" if evaluation.passed else "VIOLATION") if evaluation.applicable else "NOT_APPLICABLE",
        )

    def _assignment(
        self,
        predicate: Predicate,
        role: str,
        event: LifecycleEvent,
        state: ComplianceState,
    ) -> PredicateAssignment:
        value, _ = self.verifier.evaluate_predicate(predicate, event, state)
        truth = "UNKNOWN" if value is UNKNOWN else "TRUE" if value else "FALSE"
        return PredicateAssignment(
            symbol=_symbol(predicate),
            variable=predicate.variable,
            truth_value=truth,
            role=role,
        )


def _formula(rule: ComplianceRule) -> str:
    action = "action_in_" + "_or_".join(
        stage.value.lower() for stage in sorted(rule.lifecycle_stages, key=lambda item: item.value)
    )
    antecedent = " AND ".join((action, *(_symbol(item) for item in rule.applicability)))
    consequent = " AND ".join(_symbol(item) for item in rule.requirements) or "TRUE"
    return f"ALWAYS(({antecedent}) IMPLIES ({consequent}))"


def _symbol(predicate: Predicate) -> str:
    base = predicate.variable.replace("object.", "").replace("event.", "").replace("authorization.", "").replace(".", "_")
    if predicate.value is True:
        return base
    if predicate.value is False:
        return f"NOT {base}"
    return f"{base}_{str(predicate.value).lower()}"


def _decision_detail(decision: PolicyDecision) -> str:
    intervention = decision.required_intervention.value if decision.required_intervention else "无额外干预"
    return f"运行时决策：{decision.decision.value}；干预：{intervention}。"
