"""Block, repair, consent, approval, and replan interventions."""

from __future__ import annotations

from dataclasses import dataclass

from agentshield.intervention.repair import derived_object_id, redact_payload
from agentshield.policy.rules import Decision, Intervention, PolicyDecision
from agentshield.runtime.lifecycle import LifecycleEvent


@dataclass(frozen=True, slots=True)
class InterventionResult:
    outcome: Decision
    event: LifecycleEvent | None
    explanation: str


class InterventionEngine:
    def intervene(self, event: LifecycleEvent, decision: PolicyDecision) -> InterventionResult:
        action = decision.required_intervention
        if decision.decision != Decision.REPAIR:
            return InterventionResult(decision.decision, None, decision.explanation)
        if action == Intervention.REDACT:
            metadata = dict(event.metadata)
            metadata["is_minimized"] = True
            metadata["repair"] = {"strategy": "REDACT", "violated_rules": list(decision.violated_rules)}
            content_field = "output" if event.output is not None else "input"
            repaired = event.repaired(
                metadata=metadata,
                **{content_field: redact_payload(getattr(event, content_field))},
            )
            return InterventionResult(Decision.REPAIR, repaired, "Sensitive fields redacted; re-verification required")
        if action == Intervention.AGGREGATE:
            if len(event.data_object_ids) != 1:
                return InterventionResult(Decision.BLOCK, None, "Aggregate repair requires exactly one source object")
            source = event.data_object_ids[0]
            target = derived_object_id(source, "aggregate", event.event_id)
            metadata = dict(event.metadata)
            metadata.update(
                {
                    "is_minimized": True,
                    "recipient_type": event.metadata.get("recipient_type"),
                    "lineage": {
                        "source_object_id": source,
                        "target_object_id": target,
                        "transformation": "AGGREGATE",
                        "preserves_personal_data": False,
                        "confidence": 1.0,
                    },
                    "repair": {"strategy": "AGGREGATE", "violated_rules": list(decision.violated_rules)},
                }
            )
            replacement = event.metadata.get("aggregate_replacement")
            repaired_input = (
                dict(replacement)
                if isinstance(replacement, dict)
                else {"aggregate": "count", "source_object_id": source}
            )
            if isinstance(repaired_input, dict):
                for key in ("data_object_id", "source_object_id"):
                    if key in repaired_input:
                        repaired_input[key] = target
                metadata["data_payload"] = repaired_input.get("body", repaired_input)
            repaired = event.repaired(
                input=repaired_input,
                data_object_ids=(target,),
                metadata=metadata,
            )
            return InterventionResult(Decision.REPAIR, repaired, "Raw object replaced with aggregate; re-verification required")
        return InterventionResult(Decision.BLOCK, None, f"Unsupported repair strategy: {action}")
