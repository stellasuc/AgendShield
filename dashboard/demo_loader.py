"""Run isolated portfolio demos and load their real runtime evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from agentshield.capabilities.service import BrokerServiceProcess
from agentshield.observability import SecuritySnapshot, SecurityTimeline
from agentshield.planning import AgentPlan, ModelConfig, plan_customer_data_task
from agentshield.policy.rules import Operator, Predicate
from agentshield.shield import AgentShield
from examples.portfolio.demo import (
    run_gdpr_broker,
    run_idempotency,
    run_pipl_approval,
)


@dataclass(frozen=True, slots=True)
class DemoDefinition:
    key: str
    title: str
    regulation: str
    run_id: str
    user_request: str
    description: str


DEMO_DEFINITIONS = {
    "gdpr": DemoDefinition(
        key="gdpr",
        title="GDPR — Personal Data Exfiltration Prevention",
        regulation="GDPR",
        run_id="gdpr-broker-demo",
        user_request=(
            "Count EU customers and send the statistics to our external partner."
        ),
        description=(
            "Raw customer records are detected, repaired to an aggregate, "
            "re-verified, and sent through the broker."
        ),
    ),
    "pipl": DemoDefinition(
        key="pipl",
        title="PIPL — Sensitive Information Approval",
        regulation="PIPL",
        run_id="pipl-approval-demo",
        user_request=(
            "Send sensitive customer information to the external partner "
            "for customer service."
        ),
        description=(
            "The effect pauses durably and can be approved or denied through "
            "the real broker API."
        ),
    ),
    "idempotency": DemoDefinition(
        key="idempotency",
        title="Agent Retry / Broker Restart Protection",
        regulation="GDPR",
        run_id="idempotency-demo",
        user_request="Send the approved aggregate statistics once.",
        description=(
            "The same logical effect is retried after broker restart and "
            "returns a durable replay instead of executing twice."
        ),
    ),
}


@dataclass(slots=True)
class DemoSession:
    definition: DemoDefinition
    database: Path
    result: dict[str, Any]
    snapshot: SecuritySnapshot
    _temporary_directory: TemporaryDirectory[str] = field(repr=False)
    task_prompt: str = ""
    regulations: tuple[str, ...] = ()
    model_plan: AgentPlan | None = None

    def refresh(self) -> SecuritySnapshot:
        self.snapshot = SecurityTimeline(self.database).snapshot(
            self.definition.run_id
        )
        return self.snapshot

    def close(self) -> None:
        self._temporary_directory.cleanup()


@dataclass(frozen=True, slots=True)
class PolicyPreparation:
    """A payload-free, read-only preview of the selected policy package."""

    regulations: tuple[str, ...]
    requirements: int
    executable_rules: int
    conflicts: int


@dataclass(frozen=True, slots=True)
class PolicyRequirementView:
    requirement_id: str
    article: str
    legal_requirement: str
    engineering_interpretation: str
    runtime_enforcement: str
    lifecycle_stages: tuple[str, ...]
    source_url: str


@dataclass(frozen=True, slots=True)
class PolicyRuleView:
    rule_id: str
    description: str
    intervention: str
    lifecycle_stages: tuple[str, ...]
    source_articles: tuple[str, ...]
    source_urls: tuple[str, ...]
    formal_logic: str
    predicates: tuple["PolicyPredicateView", ...]


@dataclass(frozen=True, slots=True)
class PolicyPredicateView:
    symbol: str
    source_variable: str
    expected_value: str
    role: str


@dataclass(frozen=True, slots=True)
class PolicyInspection:
    preparation: PolicyPreparation
    requirements: tuple[PolicyRequirementView, ...]
    rules: tuple[PolicyRuleView, ...]


def prepare_policy(regulations: tuple[str, ...]) -> PolicyPreparation:
    """Load, validate, and compile selected curated regulation packages.

    This intentionally uses the same public AgentShield construction path as the
    runtime. It performs no agent call, broker startup, or side effect.
    """
    return inspect_policy(regulations).preparation


def inspect_policy(regulations: tuple[str, ...]) -> PolicyInspection:
    """Return the source-linked requirements and executable rules for the UI."""
    shield = AgentShield(regulations)
    preparation = PolicyPreparation(
        regulations=shield.regulations,
        requirements=sum(len(package.requirements) for package in shield.packages),
        executable_rules=len(shield.policy_set.rules),
        conflicts=len(shield.policy_set.conflicts),
    )
    requirements = tuple(
        PolicyRequirementView(
            requirement_id=requirement.requirement_id,
            article=requirement.source.article,
            legal_requirement=requirement.legal_requirement_summary,
            engineering_interpretation=requirement.engineering_interpretation,
            runtime_enforcement=requirement.runtime_enforcement,
            lifecycle_stages=requirement.lifecycle_stages,
            source_url=requirement.source.official_url,
        )
        for package in shield.packages
        for requirement in package.requirements
    )
    rules = tuple(
        PolicyRuleView(
            rule_id=rule.rule_id,
            description=rule.description,
            intervention=rule.intervention.value,
            lifecycle_stages=tuple(sorted(stage.value for stage in rule.lifecycle_stages)),
            source_articles=tuple(source.article for source in rule.sources),
            source_urls=tuple(source.official_url for source in rule.sources),
            formal_logic=_formal_logic(rule.lifecycle_stages, rule.applicability, rule.requirements),
            predicates=tuple(
                _predicate_view(predicate, "适用条件")
                for predicate in rule.applicability
            )
            + tuple(
                _predicate_view(predicate, "必须满足")
                for predicate in rule.requirements
            ),
        )
        for rule in shield.policy_set.rules
    )
    return PolicyInspection(
        preparation=preparation,
        requirements=requirements,
        rules=rules,
    )


def _predicate_view(predicate: Predicate, role: str) -> PolicyPredicateView:
    symbol = _symbol(predicate)
    expected = _expected_value(predicate)
    return PolicyPredicateView(
        symbol=symbol,
        source_variable=predicate.variable,
        expected_value=expected,
        role=role,
    )


def _formal_logic(
    lifecycle_stages,
    applicability: tuple[Predicate, ...],
    requirements: tuple[Predicate, ...],
) -> str:
    action_symbol = "action_in_" + "_or_".join(stage.value.lower() for stage in sorted(lifecycle_stages, key=lambda item: item.value))
    antecedent = " AND ".join((action_symbol, *(_symbol(item) for item in applicability)))
    consequent = " AND ".join(_symbol(item) for item in requirements) or "TRUE"
    return f"ALWAYS(({antecedent}) IMPLIES ({consequent}))"


def _symbol(predicate: Predicate) -> str:
    base = predicate.variable.replace("object.", "").replace("event.", "").replace("authorization.", "").replace("attributes.", "").replace(".", "_")
    if predicate.operator == Operator.EQ and predicate.value is True:
        return base
    if predicate.operator == Operator.EQ and predicate.value is False:
        return f"NOT {base}"
    if predicate.operator == Operator.EQ:
        return f"{base}_is_{str(predicate.value).lower()}"
    if predicate.operator == Operator.NE:
        return f"{base}_is_not_{str(predicate.value).lower()}"
    return base


def _expected_value(predicate: Predicate) -> str:
    if predicate.operator == Operator.EQ and predicate.value is True:
        return "TRUE"
    if predicate.operator == Operator.EQ and predicate.value is False:
        return "FALSE"
    return f"{predicate.operator.value} {predicate.value!r}"


def run_demo(
    key: str,
    *,
    task_prompt: str | None = None,
    regulations: tuple[str, ...] | None = None,
    model_config: ModelConfig | None = None,
) -> DemoSession:
    if key not in DEMO_DEFINITIONS:
        raise ValueError(f"Unknown dashboard demo: {key}")
    definition = DEMO_DEFINITIONS[key]
    effective_regulations = regulations or (definition.regulation,)
    effective_prompt = (task_prompt or definition.user_request).strip()
    model_plan = plan_customer_data_task(effective_prompt, model_config) if model_config else None
    agent_prompt = (
        "Please use only count statistics; safe aggregate output required."
        if model_plan and model_plan.route == "safe_aggregate"
        else effective_prompt
    )
    temporary = TemporaryDirectory(prefix=f"agentshield-{key}-dashboard-")
    database = Path(temporary.name) / "runtime.db"
    try:
        if key == "gdpr":
            result = run_gdpr_broker(
                database,
                prompt=agent_prompt,
                regulations=effective_regulations,
            )
        elif key == "pipl":
            result = run_pipl_approval(database, pause_only=True)
        else:
            result = run_idempotency(database)
        snapshot = SecurityTimeline(database).snapshot(definition.run_id)
        return DemoSession(
            definition=definition,
            database=database,
            result=result,
            snapshot=snapshot,
            task_prompt=effective_prompt,
            regulations=effective_regulations,
            model_plan=model_plan,
            _temporary_directory=temporary,
        )
    except BaseException:
        temporary.cleanup()
        raise


def resolve_pipl_approval(
    session: DemoSession,
    decision: str,
) -> SecuritySnapshot:
    if session.definition.key != "pipl":
        raise ValueError("Approval controls are available only for the PIPL demo")
    transaction_id = str(session.result["transaction_id"])
    service = BrokerServiceProcess(session.database, regulations=("PIPL",))
    with service as client:
        if decision == "approve":
            response = client.approve(transaction_id)
        elif decision == "deny":
            response = client.deny(transaction_id)
        else:
            raise ValueError("Decision must be approve or deny")
        stats = client.statistics()
    session.result.update(
        {
            "operator_decision": decision.upper(),
            "approval_result": response.status,
            "approval_disposition": response.disposition,
            "email_messages_after_decision": stats["email_messages"],
        }
    )
    return session.refresh()
