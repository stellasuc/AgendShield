"""Deterministic PIPL sensitive-information and separate-consent demo."""

from __future__ import annotations

from pathlib import Path
import tempfile

from agentshield import AgentShield
from agentshield.runtime.lifecycle import EventType, LifecycleEvent


def _transfer(sequence: int) -> LifecycleEvent:
    return LifecycleEvent(
        trajectory_id="pipl-demo",
        sequence=sequence,
        event_type=EventType.EXTERNAL_TRANSFER,
        actor="benefits_agent",
        tool="send_to_benefits_processor",
        input={"record_reference": "health-records-001"},
        data_object_ids=("health-records-001",),
        recipient="benefits-processor",
        purpose="benefits-review",
        metadata={
            "recipient_type": "external_handler",
            "has_lawful_basis": True,
            "purpose_compatible": True,
            "is_minimized": True,
            "recipient_notified": True,
            "specific_purpose": True,
            "strictly_necessary": True,
            "protective_measures_confirmed": True,
            "cross_border": False,
        },
    )


def run_demo(audit_directory: Path):
    shield = AgentShield(regulations=["PIPL"])
    harness = shield.create_harness("pipl-demo", audit_directory)
    harness.enforce(
        LifecycleEvent(
            trajectory_id="pipl-demo",
            sequence=1,
            event_type=EventType.TOOL_RESULT,
            actor="health_records",
            output={
                "patient_name": "Li Mei",
                "diagnosis": "asthma",
                "national_id": "11010519491231002X",
            },
            purpose="benefits-review",
            metadata={
                "data_object": {
                    "object_id": "health-records-001",
                    "source": "health_records",
                    "purpose": "benefits-review",
                    "provenance": ["health_records"],
                }
            },
        )
    )
    missing = harness.enforce(_transfer(2))
    wrong_consent = harness.enforce(
        LifecycleEvent(
            trajectory_id="pipl-demo",
            sequence=3,
            event_type=EventType.CONSENT_UPDATE,
            actor="user",
            data_object_ids=("other-record",),
            recipient="benefits-processor",
            purpose="benefits-review",
            metadata={
                "consent_id": "wrong-object-consent",
                "separate": True,
                "granted": True,
                "authorized_event_type": "EXTERNAL_TRANSFER",
            },
        )
    )
    wrong_retry = harness.enforce(_transfer(4))
    matching_consent = harness.enforce(
        LifecycleEvent(
            trajectory_id="pipl-demo",
            sequence=5,
            event_type=EventType.CONSENT_UPDATE,
            actor="user",
            data_object_ids=("health-records-001",),
            recipient="benefits-processor",
            purpose="benefits-review",
            metadata={
                "consent_id": "matching-separate-consent",
                "separate": True,
                "granted": True,
                "authorized_event_type": "EXTERNAL_TRANSFER",
            },
        )
    )
    allowed = harness.enforce(_transfer(6))
    return shield, harness, missing, wrong_consent, wrong_retry, matching_consent, allowed


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="agentshield-pipl-") as directory:
        shield, harness, missing, _, wrong_retry, _, allowed = run_demo(Path(directory))
        obj = harness.state.data_objects["health-records-001"]
        source_articles = sorted({source.article for source in missing.decisions[0].regulation_sources})
        print("[AgentShield]")
        print(f"Regulation          : {shield.regulations[0]}")
        print("Lifecycle Stage     : EXTERNAL_TRANSFER")
        print("Data Object         : health-records-001")
        print(f"Sensitive Categories: {', '.join(obj.sensitive_categories)}")
        print(f"Source Articles     : {', '.join(source_articles)}")
        print(f"Initial Decision    : {missing.outcome.value}")
        print("Consent Requirement : Separate consent scoped to object, purpose, recipient, operation")
        print(f"Wrong-object Retry  : {wrong_retry.outcome.value}")
        print(f"Matched Consent     : {allowed.outcome.value}")
        print("Final Outcome       : External provision allowed after matching consent")
        print(f"Audit Records       : {len(harness.audit.read('pipl-demo'))}")


if __name__ == "__main__":
    main()

