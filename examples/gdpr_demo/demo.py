"""Deterministic GDPR data-minimization demonstration."""

from __future__ import annotations

from pathlib import Path
import tempfile

from agentshield import AgentShield
from agentshield.runtime.lifecycle import EventType, LifecycleEvent


def run_demo(audit_directory: Path):
    shield = AgentShield(regulations=["GDPR"])
    harness = shield.create_harness("gdpr-demo", audit_directory)
    tool_result = harness.enforce(
        LifecycleEvent(
            trajectory_id="gdpr-demo",
            sequence=1,
            event_type=EventType.TOOL_RESULT,
            actor="customer_database",
            tool="customer_database",
            output=[
                {"name": "Alice Example", "email": "alice@example.test", "phone": "+49 30 123456", "country": "DE"},
                {"name": "Bob Example", "email": "bob@example.test", "phone": "+33 1 23456789", "country": "FR"},
            ],
            purpose="statistics",
            metadata={
                "data_object": {
                    "object_id": "customer-records-001",
                    "source": "customer_database",
                    "purpose": "statistics",
                    "provenance": ["customer_database"],
                }
            },
        )
    )
    transfer = harness.enforce(
        LifecycleEvent(
            trajectory_id="gdpr-demo",
            sequence=2,
            event_type=EventType.EXTERNAL_TRANSFER,
            actor="customer_service_agent",
            tool="send_to_partner",
            input={"file": "customer.csv"},
            data_object_ids=("customer-records-001",),
            recipient="external-statistics-partner",
            purpose="statistics",
            metadata={
                "recipient_type": "external",
                "has_lawful_basis": True,
                "purpose_compatible": True,
                "is_minimized": False,
                "recipient_disclosed": True,
            },
        )
    )
    return shield, harness, tool_result, transfer


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="agentshield-gdpr-") as directory:
        shield, harness, _, result = run_demo(Path(directory))
        raw = harness.state.data_objects["customer-records-001"]
        first, final = result.decisions
        derived_id = result.final_event.data_object_ids[0] if result.final_event else "<blocked>"
        article = ", ".join(source.article for source in first.regulation_sources)
        print("[AgentShield]")
        print(f"Regulation       : {shield.regulations[0]}")
        print("Lifecycle Stage  : EXTERNAL_TRANSFER")
        print("Data Object      : customer-records-001")
        print(f"Detected Data    : Personal Data ({', '.join(raw.categories)})")
        print("Purpose          : Statistics")
        print("Activated Rules  :")
        for rule_id in first.activated_rules:
            print(f"- {rule_id}")
        print(f"Source Article   : {article}")
        print(f"Decision         : {first.decision.value}")
        print(f"Intervention     : {first.required_intervention.value}")
        print(f"Derived Object   : {derived_id}")
        print(f"Re-verification  : {'PASS' if final.decision.value == 'ALLOW' else 'FAIL'}")
        print("Final Action     : Send aggregate statistics to external partner")
        print(f"Audit Records    : {len(harness.audit.read('gdpr-demo'))}")


if __name__ == "__main__":
    main()

