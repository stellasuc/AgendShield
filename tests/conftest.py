from __future__ import annotations

import pytest

from agentshield.policy.rules import (
    ComplianceRule,
    EffectivePolicySet,
    Intervention,
    Operator,
    Predicate,
    RuleSource,
    Severity,
)
from agentshield.runtime.lifecycle import EventType


@pytest.fixture
def source() -> RuleSource:
    return RuleSource(
        regulation="TEST",
        article="T-1",
        official_url="https://example.invalid/test",
        legal_requirement="Synthetic test requirement.",
        engineering_interpretation="Minimize personal data at external boundaries.",
    )


@pytest.fixture
def minimization_rule(source: RuleSource) -> ComplianceRule:
    return ComplianceRule(
        rule_id="TEST_MINIMIZATION",
        normalized_concept="DATA_MINIMIZATION",
        description="Raw personal data must not cross an external boundary.",
        lifecycle_stages=frozenset({EventType.EXTERNAL_TRANSFER}),
        dependencies=frozenset(
            {"object.contains_personal_data", "event.recipient_type", "event.is_minimized"}
        ),
        applicability=(
            Predicate("object.contains_personal_data", Operator.EQ, True),
            Predicate("event.recipient_type", Operator.EQ, "external"),
        ),
        requirements=(Predicate("event.is_minimized", Operator.EQ, True),),
        severity=Severity.HIGH,
        intervention=Intervention.AGGREGATE,
        sources=(source,),
        regulation_ids=frozenset({"TEST"}),
        repair_strategy="AGGREGATE",
    )


@pytest.fixture
def policy_set(minimization_rule: ComplianceRule) -> EffectivePolicySet:
    return EffectivePolicySet((minimization_rule,), ("TEST",))

