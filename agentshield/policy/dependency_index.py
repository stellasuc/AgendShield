"""Reverse index from changed compliance variables to executable rules."""

from __future__ import annotations

from collections import defaultdict

from agentshield.policy.rules import ComplianceRule, EffectivePolicySet
from agentshield.runtime.lifecycle import EventType, LifecycleEvent
from agentshield.state.diff import StateDiff


MANDATORY_PRE_EFFECT_STAGES = {
    EventType.EXTERNAL_TRANSFER,
    EventType.MEMORY_WRITE,
    EventType.LOG_WRITE,
}


class DependencyIndex:
    def __init__(self, policy_set: EffectivePolicySet) -> None:
        # Dictionaries avoid relying on ComplianceRule hashability. Predicate
        # values may legitimately be YAML lists (for example an IN condition).
        self._by_variable: dict[str, dict[str, ComplianceRule]] = defaultdict(dict)
        self._by_stage: dict[EventType, dict[str, ComplianceRule]] = defaultdict(dict)
        for rule in policy_set.rules:
            variables = set(rule.dependencies)
            variables.update(p.variable for p in (*rule.applicability, *rule.requirements))
            for variable in variables:
                self._by_variable[variable][rule.rule_id] = rule
            for stage in rule.lifecycle_stages:
                self._by_stage[stage][rule.rule_id] = rule

    def affected_rules(self, event: LifecycleEvent, diff: StateDiff) -> tuple[ComplianceRule, ...]:
        stage_rules = self._by_stage.get(event.event_type, {})
        force = (
            event.event_type in MANDATORY_PRE_EFFECT_STAGES
            or (event.event_type == EventType.TOOL_CALL and bool(event.metadata.get("side_effectful")))
            or (
                event.event_type == EventType.RESPONSE_GENERATED
                and bool(event.metadata.get("trust_boundary"))
            )
        )
        if force:
            return tuple(sorted(stage_rules.values(), key=lambda rule: rule.rule_id))
        affected: dict[str, ComplianceRule] = {}
        for variable in diff.changed_variables:
            affected.update(self._by_variable.get(variable, {}))
        selected = (stage_rules[rule_id] for rule_id in stage_rules.keys() & affected.keys())
        return tuple(sorted(selected, key=lambda rule: rule.rule_id))
