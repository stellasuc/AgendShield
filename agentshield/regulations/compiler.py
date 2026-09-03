"""Compile one or more regulation packages into an effective policy set."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from agentshield.policy.rules import ComplianceRule, EffectivePolicySet, PolicyConflict
from agentshield.regulations.models import RegulationPackage


class RegulationCompiler:
    """Normalizes rules, merges exact duplicates, and reports control conflicts.

    Conflict handling is an engineering policy, never a legal conclusion. Exact
    semantic duplicates are merged while retaining every source citation. Different
    controls under the same concept remain active; the restrictive action is noted.
    """

    def compile(self, packages: list[RegulationPackage]) -> EffectivePolicySet:
        if not packages:
            raise ValueError("At least one regulation package is required")

        merged: dict[tuple[object, ...], ComplianceRule] = {}
        concept_rules: dict[str, list[ComplianceRule]] = defaultdict(list)
        for package in packages:
            for rule in package.rules:
                normalized = replace(
                    rule,
                    normalized_concept=rule.normalized_concept.strip().upper(),
                    dependencies=frozenset(rule.dependencies),
                )
                signature = normalized.semantic_signature()
                if signature in merged:
                    prior = merged[signature]
                    merged[signature] = replace(
                        prior,
                        sources=tuple(dict.fromkeys((*prior.sources, *normalized.sources))),
                        regulation_ids=frozenset((*prior.regulation_ids, *normalized.regulation_ids)),
                    )
                else:
                    merged[signature] = normalized

        for rule in merged.values():
            concept_rules[rule.normalized_concept].append(rule)

        conflicts: list[PolicyConflict] = []
        for concept, rules in concept_rules.items():
            interventions = {r.intervention for r in rules}
            if len(interventions) > 1:
                chosen = max(interventions, key=lambda action: action.restrictiveness)
                conflicts.append(
                    PolicyConflict(
                        concept=concept,
                        rule_ids=tuple(r.rule_id for r in rules),
                        selected_control=chosen,
                        explanation=(
                            "Engineering conflict resolution selected the more restrictive "
                            "technical control; human review is recommended."
                        ),
                    )
                )

        return EffectivePolicySet(
            rules=tuple(sorted(merged.values(), key=lambda r: r.rule_id)),
            regulations=tuple(p.metadata.regulation_id for p in packages),
            conflicts=tuple(conflicts),
        )

