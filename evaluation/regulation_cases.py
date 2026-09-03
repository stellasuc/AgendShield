"""Run 12 deterministic privacy-control regression cases."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from statistics import mean
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Callable

from agentshield import AgentShield
from agentshield.policy.rules import Decision
from agentshield.runtime.harness import ComplianceHarness, EnforcementResult
from agentshield.runtime.lifecycle import EventType, LifecycleEvent


@dataclass(frozen=True, slots=True)
class CaseSpec:
    case_id: str
    regulation: str
    expected_outcome: Decision
    violation_expected: bool
    execute: Callable[[Path], tuple[ComplianceHarness, EnforcementResult]]


@dataclass(frozen=True, slots=True)
class CaseResult:
    case_id: str
    regulation: str
    expected_outcome: str
    actual_outcome: str
    passed: bool
    violation_expected: bool
    violation_detected: bool
    repairs_attempted: int
    repairs_successful: int
    rules_evaluated: int
    events_skipped: int
    verification_latency_ms: float


def _harness(regulation: str, case_id: str, audit_dir: Path) -> ComplianceHarness:
    return AgentShield([regulation]).create_harness(case_id, audit_dir)


def _seed(harness: ComplianceHarness, case_id: str, output: object, object_id: str, purpose: str) -> None:
    harness.enforce(
        LifecycleEvent(
            case_id, 1, EventType.TOOL_RESULT, "mock-database",
            output=output,
            purpose=purpose,
            metadata={"data_object": {"object_id": object_id, "source": "mock-database", "purpose": purpose}},
        )
    )


def _gdpr_transfer(case_id: str, sequence: int, object_id: str, **overrides: object) -> LifecycleEvent:
    metadata = {
        "recipient_type": "external",
        "has_lawful_basis": True,
        "purpose_compatible": True,
        "is_minimized": True,
        "recipient_disclosed": True,
    }
    metadata.update(overrides)
    return LifecycleEvent(
        case_id, sequence, EventType.EXTERNAL_TRANSFER, "agent",
        input={"object_reference": object_id}, data_object_ids=(object_id,),
        recipient="partner", purpose="statistics", metadata=metadata,
    )


def _pipl_transfer(case_id: str, sequence: int, object_id: str, **overrides: object) -> LifecycleEvent:
    metadata = {
        "recipient_type": "external_handler",
        "has_lawful_basis": True,
        "purpose_compatible": True,
        "is_minimized": True,
        "recipient_notified": True,
        "specific_purpose": True,
        "strictly_necessary": True,
        "protective_measures_confirmed": True,
        "cross_border": False,
    }
    metadata.update(overrides)
    return LifecycleEvent(
        case_id, sequence, EventType.EXTERNAL_TRANSFER, "agent",
        input={"object_reference": object_id}, data_object_ids=(object_id,),
        recipient="processor", purpose="benefits", metadata=metadata,
    )


def _consent(harness: ComplianceHarness, case_id: str, sequence: int, object_id: str, purpose: str) -> None:
    harness.enforce(
        LifecycleEvent(
            case_id, sequence, EventType.CONSENT_UPDATE, "user",
            data_object_ids=(object_id,), recipient="processor", purpose=purpose,
            metadata={
                "consent_id": f"consent-{case_id}", "separate": True,
                "authorized_event_type": "EXTERNAL_TRANSFER",
            },
        )
    )


def _gdpr_raw_repair(path: Path):
    case_id = "gdpr_raw_repair"
    harness = _harness("GDPR", case_id, path)
    _seed(harness, case_id, [{"name": "Alice", "email": "alice@example.test"}], "raw", "statistics")
    return harness, harness.enforce(_gdpr_transfer(case_id, 2, "raw", is_minimized=False))


def _gdpr_public(path: Path):
    case_id = "gdpr_public_aggregate"
    harness = _harness("GDPR", case_id, path)
    _seed(harness, case_id, {"customer_count": 42}, "count", "statistics")
    return harness, harness.enforce(_gdpr_transfer(case_id, 2, "count"))


def _gdpr_missing_basis(path: Path):
    case_id = "gdpr_missing_basis"
    harness = _harness("GDPR", case_id, path)
    _seed(harness, case_id, {"email": "alice@example.test"}, "personal", "statistics")
    return harness, harness.enforce(_gdpr_transfer(case_id, 2, "personal", has_lawful_basis=False))


def _gdpr_wrong_purpose(path: Path):
    case_id = "gdpr_incompatible_purpose"
    harness = _harness("GDPR", case_id, path)
    _seed(harness, case_id, {"email": "alice@example.test"}, "personal", "support")
    return harness, harness.enforce(_gdpr_transfer(case_id, 2, "personal", purpose_compatible=False))


def _gdpr_unbounded_memory(path: Path):
    case_id = "gdpr_unbounded_memory"
    harness = _harness("GDPR", case_id, path)
    _seed(harness, case_id, {"email": "alice@example.test"}, "personal", "support")
    event = LifecycleEvent(
        case_id, 2, EventType.MEMORY_WRITE, "agent", input={"object_reference": "personal"},
        data_object_ids=("personal",), purpose="support",
        metadata={"has_lawful_basis": True, "purpose_compatible": True, "retention_bounded": False},
    )
    return harness, harness.enforce(event)


def _gdpr_special_category(path: Path):
    case_id = "gdpr_special_category"
    harness = _harness("GDPR", case_id, path)
    _seed(harness, case_id, {"patient_name": "Alice", "diagnosis": "asthma"}, "health", "statistics")
    return harness, harness.enforce(_gdpr_transfer(case_id, 2, "health"))


def _pipl_missing_consent(path: Path):
    case_id = "pipl_missing_consent"
    harness = _harness("PIPL", case_id, path)
    _seed(harness, case_id, {"patient_name": "Li Mei", "diagnosis": "asthma"}, "health", "benefits")
    return harness, harness.enforce(_pipl_transfer(case_id, 2, "health"))


def _pipl_matching_consent(path: Path):
    case_id = "pipl_matching_consent"
    harness = _harness("PIPL", case_id, path)
    _seed(harness, case_id, {"patient_name": "Li Mei", "diagnosis": "asthma"}, "health", "benefits")
    _consent(harness, case_id, 2, "health", "benefits")
    return harness, harness.enforce(_pipl_transfer(case_id, 3, "health"))


def _pipl_wrong_object(path: Path):
    case_id = "pipl_wrong_object_consent"
    harness = _harness("PIPL", case_id, path)
    _seed(harness, case_id, {"patient_name": "Li Mei", "diagnosis": "asthma"}, "health", "benefits")
    _consent(harness, case_id, 2, "other", "benefits")
    return harness, harness.enforce(_pipl_transfer(case_id, 3, "health"))


def _pipl_wrong_purpose(path: Path):
    case_id = "pipl_wrong_purpose_consent"
    harness = _harness("PIPL", case_id, path)
    _seed(harness, case_id, {"patient_name": "Li Mei", "diagnosis": "asthma"}, "health", "benefits")
    _consent(harness, case_id, 2, "health", "marketing")
    return harness, harness.enforce(_pipl_transfer(case_id, 3, "health"))


def _pipl_unbounded_memory(path: Path):
    case_id = "pipl_unbounded_memory"
    harness = _harness("PIPL", case_id, path)
    _seed(harness, case_id, {"patient_name": "Li Mei", "diagnosis": "asthma"}, "health", "benefits")
    event = LifecycleEvent(
        case_id, 2, EventType.MEMORY_WRITE, "agent", input={"object_reference": "health"},
        data_object_ids=("health",), purpose="benefits",
        metadata={
            "has_lawful_basis": True, "purpose_compatible": True, "retention_bounded": False,
            "specific_purpose": True, "strictly_necessary": True, "protective_measures_confirmed": True,
        },
    )
    return harness, harness.enforce(event)


def _pipl_public(path: Path):
    case_id = "pipl_public_aggregate"
    harness = _harness("PIPL", case_id, path)
    _seed(harness, case_id, {"customer_count": 42}, "count", "benefits")
    return harness, harness.enforce(_pipl_transfer(case_id, 2, "count"))


CASES = (
    CaseSpec("gdpr_raw_repair", "GDPR", Decision.ALLOW, True, _gdpr_raw_repair),
    CaseSpec("gdpr_public_aggregate", "GDPR", Decision.ALLOW, False, _gdpr_public),
    CaseSpec("gdpr_missing_basis", "GDPR", Decision.REQUIRE_APPROVAL, True, _gdpr_missing_basis),
    CaseSpec("gdpr_incompatible_purpose", "GDPR", Decision.REPLAN, True, _gdpr_wrong_purpose),
    CaseSpec("gdpr_unbounded_memory", "GDPR", Decision.BLOCK, True, _gdpr_unbounded_memory),
    CaseSpec("gdpr_special_category", "GDPR", Decision.REQUIRE_APPROVAL, True, _gdpr_special_category),
    CaseSpec("pipl_missing_consent", "PIPL", Decision.REQUIRE_CONSENT, True, _pipl_missing_consent),
    CaseSpec("pipl_matching_consent", "PIPL", Decision.ALLOW, False, _pipl_matching_consent),
    CaseSpec("pipl_wrong_object_consent", "PIPL", Decision.REQUIRE_CONSENT, True, _pipl_wrong_object),
    CaseSpec("pipl_wrong_purpose_consent", "PIPL", Decision.REQUIRE_CONSENT, True, _pipl_wrong_purpose),
    CaseSpec("pipl_unbounded_memory", "PIPL", Decision.BLOCK, True, _pipl_unbounded_memory),
    CaseSpec("pipl_public_aggregate", "PIPL", Decision.ALLOW, False, _pipl_public),
)


def run_evaluation(output: Path | None = None) -> dict[str, object]:
    results: list[CaseResult] = []
    wall_started = perf_counter()
    with TemporaryDirectory(prefix="agentshield-regulation-eval-") as directory:
        audit_root = Path(directory)
        for spec in CASES:
            harness, enforcement = spec.execute(audit_root / spec.case_id)
            records = harness.audit.read(spec.case_id)
            violation_detected = any(decision.violated_rules for decision in enforcement.decisions)
            results.append(
                CaseResult(
                    case_id=spec.case_id,
                    regulation=spec.regulation,
                    expected_outcome=spec.expected_outcome.value,
                    actual_outcome=enforcement.outcome.value,
                    passed=enforcement.outcome == spec.expected_outcome,
                    violation_expected=spec.violation_expected,
                    violation_detected=violation_detected,
                    repairs_attempted=enforcement.repair_attempts,
                    repairs_successful=int(enforcement.repair_attempts > 0 and enforcement.outcome == Decision.ALLOW),
                    rules_evaluated=sum(int(record["rules_evaluated"]) for record in records),
                    events_skipped=sum(bool(record["verification_skipped"]) for record in records),
                    verification_latency_ms=round(
                        sum(float(record["latency_ms"]) for record in records), 4
                    ),
                )
            )
    safe_results = [item for item in results if not item.violation_expected]
    expected_violations = [item for item in results if item.violation_expected]
    summary = {
        "cases_total": len(results),
        "cases_passed": sum(item.passed for item in results),
        "violations_expected": len(expected_violations),
        "violations_detected": sum(item.violation_detected for item in expected_violations),
        "false_blocks": sum(item.actual_outcome != Decision.ALLOW.value for item in safe_results),
        "repairs_attempted": sum(item.repairs_attempted for item in results),
        "repairs_successful": sum(item.repairs_successful for item in results),
        "rules_evaluated": sum(item.rules_evaluated for item in results),
        "events_skipped": sum(item.events_skipped for item in results),
        "verification_latency_ms_total": round(sum(item.verification_latency_ms for item in results), 4),
        "verification_latency_ms_mean_per_case": round(mean(item.verification_latency_ms for item in results), 4),
        "evaluation_wall_time_ms": round((perf_counter() - wall_started) * 1000, 4),
    }
    payload = {"summary": summary, "cases": [asdict(item) for item in results]}
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = run_evaluation(args.output)
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
