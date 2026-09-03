"""Normalized executable policy models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any

from agentshield.runtime.lifecycle import EventType


class Severity(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class Intervention(str, Enum):
    AUDIT_ONLY = "AUDIT_ONLY"
    REPLAN = "REPLAN"
    REDACT = "REDACT"
    AGGREGATE = "AGGREGATE"
    REQUIRE_CONSENT = "REQUIRE_CONSENT"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    PREVENT_MEMORY_WRITE = "PREVENT_MEMORY_WRITE"
    BLOCK = "BLOCK"

    @property
    def restrictiveness(self) -> int:
        return {
            Intervention.AUDIT_ONLY: 0,
            Intervention.REPLAN: 1,
            Intervention.REDACT: 2,
            Intervention.AGGREGATE: 2,
            Intervention.REQUIRE_CONSENT: 3,
            Intervention.REQUIRE_APPROVAL: 4,
            Intervention.PREVENT_MEMORY_WRITE: 5,
            Intervention.BLOCK: 6,
        }[self]


class Decision(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REPAIR = "REPAIR"
    REQUIRE_CONSENT = "REQUIRE_CONSENT"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    REPLAN = "REPLAN"
    AUDIT_ONLY = "AUDIT_ONLY"


class Operator(str, Enum):
    EQ = "EQ"
    NE = "NE"
    IN = "IN"
    EXISTS = "EXISTS"
    TRUTHY = "TRUTHY"


@dataclass(frozen=True, slots=True)
class Predicate:
    variable: str
    operator: Operator
    value: Any = None

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "Predicate":
        return cls(
            variable=str(payload["variable"]),
            operator=Operator(str(payload.get("operator", "EQ")).upper()),
            value=payload.get("value"),
        )


@dataclass(frozen=True, slots=True)
class RuleSource:
    regulation: str
    article: str
    official_url: str
    legal_requirement: str
    engineering_interpretation: str
    official_source: str = ""
    requirement_id: str = ""

    def __post_init__(self) -> None:
        if not all(
            (
                self.regulation,
                self.article,
                self.official_url,
                self.legal_requirement,
                self.engineering_interpretation,
            )
        ):
            raise ValueError(
                "Rule source must preserve regulation, article, URL, legal requirement, and engineering interpretation"
            )
        if not self.official_url.startswith(("https://", "http://")):
            raise ValueError("Rule source official_url must be an HTTP(S) URL")


@dataclass(frozen=True, slots=True)
class ComplianceRule:
    rule_id: str
    normalized_concept: str
    description: str
    lifecycle_stages: frozenset[EventType]
    dependencies: frozenset[str]
    applicability: tuple[Predicate, ...]
    requirements: tuple[Predicate, ...]
    severity: Severity
    intervention: Intervention
    sources: tuple[RuleSource, ...]
    regulation_ids: frozenset[str] = frozenset()
    repair_strategy: str | None = None
    fail_closed_on_unknown: bool = True
    interventions: tuple[Intervention, ...] = ()
    predicate_handler: str | None = None

    def __post_init__(self) -> None:
        if not self.rule_id or not self.normalized_concept:
            raise ValueError("rule_id and normalized_concept are required")
        if not self.lifecycle_stages or not self.sources:
            raise ValueError("A rule needs lifecycle stages and at least one source")

    @classmethod
    def from_mapping(cls, payload: dict[str, Any], regulation_id: str) -> "ComplianceRule":
        sources = tuple(RuleSource(**source) for source in payload["sources"])
        intervention_values = payload.get("interventions") or [payload["intervention"]]
        interventions = tuple(Intervention(str(value).upper()) for value in intervention_values)
        return cls(
            rule_id=payload["rule_id"],
            normalized_concept=payload["normalized_concept"],
            description=payload["description"],
            lifecycle_stages=frozenset(EventType(stage) for stage in payload["lifecycle_stages"]),
            dependencies=frozenset(payload.get("dependencies", [])),
            applicability=tuple(Predicate.from_mapping(p) for p in payload.get("applicability", [])),
            requirements=tuple(Predicate.from_mapping(p) for p in payload.get("requirements", [])),
            severity=Severity[str(payload.get("severity", "MEDIUM")).upper()],
            intervention=interventions[0],
            sources=sources,
            regulation_ids=frozenset({regulation_id}),
            repair_strategy=payload.get("repair_strategy"),
            fail_closed_on_unknown=bool(payload.get("fail_closed_on_unknown", True)),
            interventions=interventions,
            predicate_handler=(payload.get("predicate") or {}).get("handler"),
        )

    def semantic_signature(self) -> tuple[object, ...]:
        return (
            self.normalized_concept,
            tuple(sorted(stage.value for stage in self.lifecycle_stages)),
            tuple(sorted(self.dependencies)),
            repr(self.applicability),
            repr(self.requirements),
            self.severity,
            self.intervention,
            self.repair_strategy,
            self.fail_closed_on_unknown,
            tuple(self.interventions),
            self.predicate_handler,
        )


@dataclass(frozen=True, slots=True)
class PolicyConflict:
    concept: str
    rule_ids: tuple[str, ...]
    selected_control: Intervention
    explanation: str


@dataclass(frozen=True, slots=True)
class EffectivePolicySet:
    rules: tuple[ComplianceRule, ...]
    regulations: tuple[str, ...]
    conflicts: tuple[PolicyConflict, ...] = ()


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    rule: ComplianceRule
    applicable: bool
    passed: bool
    unknown_variables: tuple[str, ...] = ()
    explanation: str = ""


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    decision: Decision
    event_id: str
    activated_rules: tuple[str, ...] = ()
    violated_rules: tuple[str, ...] = ()
    regulation_sources: tuple[RuleSource, ...] = ()
    risk_level: Severity | None = None
    explanation: str = ""
    required_intervention: Intervention | None = None
    verification_skipped: bool = False
    rules_evaluated: int = 0
