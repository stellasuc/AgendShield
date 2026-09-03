"""Framework-agnostic enforcement loop with repair re-verification."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter
from collections import defaultdict

from agentshield.audit.logger import AuditLogger
from agentshield.audit.models import AuditEntry
from agentshield.intervention.engine import InterventionEngine
from agentshield.policy.engine import DeterministicPolicyEngine
from agentshield.policy.rules import Decision, PolicyDecision
from agentshield.runtime.lifecycle import LifecycleEvent
from agentshield.shield_agent import ShieldAgent, ShieldingPlan
from agentshield.state.manager import ComplianceStateManager
from agentshield.state.models import ComplianceState
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentshield.detectors.base import Detector


@dataclass(frozen=True, slots=True)
class EnforcementResult:
    original_event: LifecycleEvent
    final_event: LifecycleEvent | None
    decisions: tuple[PolicyDecision, ...]
    outcome: Decision
    repair_attempts: int
    shielding_plans: tuple[ShieldingPlan, ...] = ()


class ComplianceHarness:
    def __init__(
        self,
        engine: DeterministicPolicyEngine,
        state: ComplianceState,
        audit_logger: AuditLogger,
        *,
        max_repair_attempts: int = 2,
        detector: "Detector | None" = None,
        audit_failure_mode: str = "fail_closed",
    ) -> None:
        if max_repair_attempts < 0:
            raise ValueError("max_repair_attempts cannot be negative")
        self.engine = engine
        self.state = state
        self.manager = ComplianceStateManager(state, detector=detector)
        self.interventions = InterventionEngine()
        self.shield_agent = ShieldAgent(engine.policy_set, engine.verifier)
        self.audit = audit_logger
        self.max_repair_attempts = max_repair_attempts
        if audit_failure_mode not in {"fail_open", "fail_closed"}:
            raise ValueError("audit_failure_mode must be fail_open or fail_closed")
        self.audit_failure_mode = audit_failure_mode
        self.metrics: dict[str, float] = defaultdict(float)

    def enforce(self, event: LifecycleEvent) -> EnforcementResult:
        original = event
        current = event
        decisions: list[PolicyDecision] = []
        shielding_plans: list[ShieldingPlan] = []
        repairs = 0

        while True:
            started = perf_counter()
            try:
                state_started = perf_counter()
                diff = self.manager.apply(current)
                self.metrics["state_update_latency_ms"] += (perf_counter() - state_started) * 1000
                rule_started = perf_counter()
                decision = self.engine.decide(current, self.state, diff)
                self.metrics["rule_evaluation_latency_ms"] += (perf_counter() - rule_started) * 1000
            except (KeyError, TypeError, ValueError) as exc:
                decision = PolicyDecision(
                    decision=Decision.BLOCK,
                    event_id=current.event_id,
                    explanation=f"Event normalization or verification failed closed: {exc}",
                )
                from agentshield.state.diff import StateDiff

                diff = StateDiff()
            decisions.append(decision)
            shielding_plans.append(
                self.shield_agent.shield(current, self.state, diff, decision)
            )
            self.metrics["verification_triggers"] += 0 if decision.verification_skipped else 1
            self.metrics["events_skipped"] += 1 if decision.verification_skipped else 0
            self.metrics["rules_evaluated"] += decision.rules_evaluated
            self.metrics["events"] += 1
            self._record_decision(current, decision)
            elapsed_ms = (perf_counter() - started) * 1000

            if decision.decision == Decision.REPAIR:
                if repairs >= self.max_repair_attempts:
                    final_outcome = Decision.BLOCK
                    self._audit(current, diff, decision, final_outcome, elapsed_ms)
                    break
                intervention = self.interventions.intervene(current, decision)
                if intervention.event is None:
                    final_outcome = Decision.BLOCK
                    self._audit(current, diff, decision, final_outcome, elapsed_ms)
                    break
                self._audit(current, diff, decision, Decision.REPAIR, elapsed_ms)
                current = intervention.event
                repairs += 1
                self.metrics["repair_attempts"] += 1
                continue

            final_outcome = decision.decision
            self._audit(current, diff, decision, final_outcome, elapsed_ms)
            break

        return EnforcementResult(
            original_event=original,
            final_event=current if final_outcome in {Decision.ALLOW, Decision.AUDIT_ONLY} else None,
            decisions=tuple(decisions),
            outcome=final_outcome,
            repair_attempts=repairs,
            shielding_plans=tuple(shielding_plans),
        )

    def _record_decision(self, event: LifecycleEvent, decision: PolicyDecision) -> None:
        if decision.violated_rules:
            self.state.violations.append(
                {
                    "event_id": event.event_id,
                    "rule_ids": list(decision.violated_rules),
                    "decision": decision.decision.value,
                }
            )
        if decision.decision in {Decision.REQUIRE_CONSENT, Decision.REQUIRE_APPROVAL}:
            self.state.active_obligations[event.event_id] = {
                "type": decision.decision.value,
                "rule_ids": list(decision.violated_rules),
                "data_object_ids": list(event.data_object_ids),
                "purpose": event.purpose,
                "recipient_fingerprint": event.audit_view()["recipient_fingerprint"],
            }

    def _audit(self, event: LifecycleEvent, diff: object, decision: PolicyDecision, outcome: Decision, latency_ms: float) -> None:
        sources = tuple(asdict(source) for source in decision.regulation_sources)
        repair = event.metadata.get("repair")
        entry = AuditEntry(
                run_id=event.trajectory_id,
                event=event.audit_view(),
                state_diff=diff.audit_view(),
                data_object_ids=event.data_object_ids,
                activated_rules=decision.activated_rules,
                regulation_sources=sources,
                decision=decision.decision.value,
                intervention=(decision.required_intervention.value if decision.required_intervention else None),
                repair=repair,
                final_outcome=outcome.value,
                execution_outcome=_execution_outcome(event, outcome),
                latency_ms=round(latency_ms, 4),
                rules_evaluated=decision.rules_evaluated,
                verification_skipped=decision.verification_skipped,
            )
        audit_started = perf_counter()
        try:
            self.audit.append(entry)
        except Exception:
            self.metrics["audit_failures"] += 1
            if self.audit_failure_mode == "fail_closed":
                raise
        finally:
            self.metrics["audit_latency_ms"] += (perf_counter() - audit_started) * 1000
        self.metrics["detector_calls"] = self.manager.detector_calls
        self.metrics["detector_latency_ms"] = self.manager.detector_latency_ms


def _execution_outcome(event: LifecycleEvent, outcome: Decision) -> str:
    phase = event.metadata.get("runtime_phase")
    if event.event_type.value == "AGENT_ERROR":
        return "FAILED"
    if phase == "TOOL_RESULT_INGESTED":
        return "SUCCEEDED"
    if phase == "RESPONSE_RELEASE_CANDIDATE" and outcome in {Decision.ALLOW, Decision.AUDIT_ONLY}:
        return "APPROVED_FOR_RELEASE"
    if outcome == Decision.REPAIR:
        return "REPAIR_PROPOSED_NOT_EXECUTED"
    if outcome in {
        Decision.BLOCK,
        Decision.REQUIRE_CONSENT,
        Decision.REQUIRE_APPROVAL,
        Decision.REPLAN,
    }:
        return "PREVENTED"
    if phase == "TOOL_CALL_PROPOSED":
        return "APPROVED_FOR_EXECUTION"
    return "PROCESSED"
