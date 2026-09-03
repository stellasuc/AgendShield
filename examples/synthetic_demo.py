"""Regulation-neutral end-to-end demo of aggregate repair and re-verification."""

from __future__ import annotations

from pathlib import Path
import tempfile

from agentshield.audit.logger import AuditLogger
from agentshield.policy.engine import DeterministicPolicyEngine
from agentshield.policy.rules import (
    ComplianceRule,
    EffectivePolicySet,
    Intervention,
    Operator,
    Predicate,
    RuleSource,
    Severity,
)
from agentshield.runtime.harness import ComplianceHarness
from agentshield.runtime.lifecycle import EventType, LifecycleEvent
from agentshield.state.manager import ComplianceStateManager
from agentshield.state.models import ComplianceState


def synthetic_policy() -> EffectivePolicySet:
    rule = ComplianceRule(
        rule_id="SYNTHETIC_DATA_MINIMIZATION",
        normalized_concept="DATA_MINIMIZATION",
        description="Do not externally transfer raw personal data when an aggregate satisfies the purpose.",
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
        sources=(
            RuleSource(
                regulation="SYNTHETIC",
                article="DEMO-1",
                official_url="https://example.invalid/synthetic-policy",
                legal_requirement="Synthetic demonstration requirement; not law.",
                engineering_interpretation="Use aggregate output when raw rows are unnecessary.",
            ),
        ),
        regulation_ids=frozenset({"SYNTHETIC"}),
        repair_strategy="AGGREGATE",
    )
    return EffectivePolicySet(rules=(rule,), regulations=("SYNTHETIC",))


def run_demo(audit_dir: Path) -> tuple[ComplianceHarness, object]:
    trajectory_id = "synthetic-demo"
    state = ComplianceState(trajectory_id=trajectory_id)
    manager = ComplianceStateManager(state)
    manager.apply(
        LifecycleEvent(
            trajectory_id=trajectory_id,
            sequence=1,
            event_type=EventType.TOOL_RESULT,
            actor="customer_database",
            output={"rows": "omitted from state and audit"},
            purpose="statistics",
            metadata={
                "data_object": {
                    "object_id": "customer-db-result",
                    "classification": "PERSONAL",
                    "contains_personal_data": True,
                    "contains_sensitive_data": False,
                    "source": "customer_database",
                    "purpose": "statistics",
                    "provenance": ["customer_database"],
                }
            },
        )
    )
    harness = ComplianceHarness(
        DeterministicPolicyEngine(synthetic_policy()),
        state,
        AuditLogger(audit_dir),
    )
    result = harness.enforce(
        LifecycleEvent(
            trajectory_id=trajectory_id,
            sequence=2,
            event_type=EventType.EXTERNAL_TRANSFER,
            actor="agent",
            tool="send_to_partner",
            input={"file": "customer.csv"},
            data_object_ids=("customer-db-result",),
            recipient="external-partner",
            purpose="statistics",
            metadata={"recipient_type": "external", "is_minimized": False},
        )
    )
    return harness, result


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="agentshield-demo-") as directory:
        harness, result = run_demo(Path(directory))
        print("[AgentShield] Synthetic lifecycle compliance demo")
        print(f"Original event: {result.original_event.event_type.value} ({result.original_event.event_id})")
        first, final = result.decisions
        print(f"Activated rule: {first.violated_rules[0]}")
        print(f"Decision: {first.decision.value}")
        print(f"Intervention: {first.required_intervention.value}")
        print(f"Repaired event: {result.final_event.event_id}")
        print(f"Re-verification: {'PASS' if final.decision.value == 'ALLOW' else 'FAIL'}")
        print(f"Final outcome: {result.outcome.value}")
        print(f"Final data object: {result.final_event.data_object_ids[0]}")
        origins = harness.manager.lineage.trace_origins(result.final_event.data_object_ids[0])
        print(f"Lineage origin: {', '.join(origins)}")
        print(f"Audit records: {len(harness.audit.read('synthetic-demo'))}")


if __name__ == "__main__":
    main()

