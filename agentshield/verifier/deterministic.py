"""Deterministic predicate verification for the core runtime."""

from __future__ import annotations

from typing import Any

from agentshield.policy.rules import ComplianceRule, Operator, Predicate, RuleEvaluation
from agentshield.runtime.lifecycle import LifecycleEvent
from agentshield.state.models import ComplianceState


UNKNOWN = object()


class DeterministicVerifier:
    def verify(self, rule: ComplianceRule, event: LifecycleEvent, state: ComplianceState) -> RuleEvaluation:
        applicability = [self._evaluate(p, event, state) for p in rule.applicability]
        if any(value is False for value, _ in applicability):
            return RuleEvaluation(rule=rule, applicable=False, passed=True, explanation="Rule not applicable")
        applicability_unknown = [name for value, name in applicability if value is UNKNOWN]
        if applicability_unknown:
            # Unknown applicability does not prove that a rule applies. The event can
            # still be caught by a broader fail-closed rule if policy authors require it.
            return RuleEvaluation(
                rule=rule,
                applicable=False,
                passed=True,
                unknown_variables=tuple(applicability_unknown),
                explanation="Applicability is unknown",
            )

        requirements = [self._evaluate(p, event, state) for p in rule.requirements]
        unknown = [name for value, name in requirements if value is UNKNOWN]
        failed = [name for value, name in requirements if value is False]
        passed = not failed and (not unknown or not rule.fail_closed_on_unknown)
        if passed:
            explanation = "All required predicates are satisfied"
        elif failed:
            explanation = f"Failed predicates: {', '.join(failed)}"
        else:
            explanation = f"Unknown required predicates (fail closed): {', '.join(unknown)}"
        return RuleEvaluation(
            rule=rule,
            applicable=True,
            passed=passed,
            unknown_variables=tuple(unknown),
            explanation=explanation,
        )

    def _evaluate(self, predicate: Predicate, event: LifecycleEvent, state: ComplianceState) -> tuple[bool | object, str]:
        actual = self._resolve(predicate.variable, event, state)
        if actual is UNKNOWN:
            return UNKNOWN, predicate.variable
        if predicate.operator == Operator.EQ:
            return actual == predicate.value, predicate.variable
        if predicate.operator == Operator.NE:
            return actual != predicate.value, predicate.variable
        if predicate.operator == Operator.IN:
            return actual in predicate.value, predicate.variable
        if predicate.operator == Operator.EXISTS:
            return actual is not None, predicate.variable
        if predicate.operator == Operator.TRUTHY:
            return bool(actual), predicate.variable
        raise AssertionError(f"Unhandled operator: {predicate.operator}")

    def _resolve(self, variable: str, event: LifecycleEvent, state: ComplianceState) -> Any:
        if variable == "event.event_type":
            return event.event_type.value
        if variable == "event.purpose":
            return event.purpose if event.purpose is not None else UNKNOWN
        if variable == "event.recipient":
            return event.recipient if event.recipient is not None else UNKNOWN
        if variable.startswith("event."):
            return event.metadata.get(variable.removeprefix("event."), UNKNOWN)
        if variable.startswith("task_context."):
            return state.task_context.get(variable.removeprefix("task_context."), UNKNOWN)
        if variable.startswith("policy_context."):
            return state.policy_context.get(variable.removeprefix("policy_context."), UNKNOWN)
        if variable == "authorization.consent":
            return state.matching_consent(
                event.data_object_ids,
                event.purpose,
                event.recipient,
                event_type=event.event_type.value,
            )
        if variable == "authorization.separate_consent":
            return state.matching_consent(
                event.data_object_ids,
                event.purpose,
                event.recipient,
                separate=True,
                event_type=event.event_type.value,
            )
        if variable == "authorization.approval":
            return state.matching_approval(
                event.event_type.value,
                event.data_object_ids,
                event.purpose,
                event.recipient,
            )
        if variable.startswith("object."):
            field_path = variable.removeprefix("object.").split(".")
            values = [
                self._resolve_path(state.data_objects[object_id], field_path)
                for object_id in event.data_object_ids
                if object_id in state.data_objects
            ]
            if not values:
                return UNKNOWN
            known = [value for value in values if value is not None and value is not UNKNOWN]
            if not known:
                return UNKNOWN
            if all(isinstance(value, bool) for value in known):
                return any(known)
            return known[0] if all(value == known[0] for value in known) else tuple(known)
        return UNKNOWN

    @staticmethod
    def _resolve_path(value: Any, path: list[str]) -> Any:
        current = value
        for component in path:
            if isinstance(current, dict):
                current = current.get(component, UNKNOWN)
            else:
                current = getattr(current, component, UNKNOWN)
            if current is UNKNOWN:
                return UNKNOWN
        return current
