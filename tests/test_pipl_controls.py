from __future__ import annotations

from agentshield import AgentShield
from agentshield.policy.rules import Decision
from agentshield.runtime.lifecycle import EventType, LifecycleEvent
from examples.pipl_demo import run_demo


def _seed_sensitive(harness, trajectory: str = "pipl") -> None:
    harness.enforce(
        LifecycleEvent(
            trajectory, 1, EventType.TOOL_RESULT, "health-db",
            output={"patient_name": "Li Mei", "diagnosis": "asthma"},
            purpose="benefits",
            metadata={"data_object": {"object_id": "health", "source": "health-db", "purpose": "benefits"}},
        )
    )


def _transfer(trajectory: str, sequence: int) -> LifecycleEvent:
    return LifecycleEvent(
        trajectory, sequence, EventType.EXTERNAL_TRANSFER, "agent",
        input={"record_reference": "health"}, data_object_ids=("health",),
        recipient="processor", purpose="benefits",
        metadata={
            "recipient_type": "external_handler", "has_lawful_basis": True,
            "purpose_compatible": True, "is_minimized": True, "recipient_notified": True,
            "specific_purpose": True, "strictly_necessary": True,
            "protective_measures_confirmed": True, "cross_border": False,
        },
    )


def test_sensitive_information_and_missing_consent_detected(tmp_path) -> None:
    shield = AgentShield(["PIPL"])
    harness = shield.create_harness("pipl", tmp_path)
    _seed_sensitive(harness)
    assert harness.state.data_objects["health"].attributes["pipl_sensitive_candidate"]
    result = harness.enforce(_transfer("pipl", 2))
    assert result.outcome == Decision.REQUIRE_CONSENT
    assert {"PIPL_THIRD_PARTY_PROVISION_001", "PIPL_SENSITIVE_SEPARATE_CONSENT_001"} <= set(result.decisions[0].violated_rules)


def test_matching_consent_accepted_and_wrong_object_rejected(tmp_path) -> None:
    _, _, missing, _, wrong_retry, _, allowed = run_demo(tmp_path)
    assert missing.outcome == Decision.REQUIRE_CONSENT
    assert wrong_retry.outcome == Decision.REQUIRE_CONSENT
    assert allowed.outcome == Decision.ALLOW


def test_wrong_purpose_consent_is_rejected(tmp_path) -> None:
    shield = AgentShield(["PIPL"])
    harness = shield.create_harness("pipl", tmp_path)
    _seed_sensitive(harness)
    harness.enforce(
        LifecycleEvent(
            "pipl", 2, EventType.CONSENT_UPDATE, "user",
            data_object_ids=("health",), recipient="processor", purpose="marketing",
            metadata={
                "consent_id": "wrong-purpose", "separate": True,
                "authorized_event_type": "EXTERNAL_TRANSFER",
            },
        )
    )
    assert harness.enforce(_transfer("pipl", 3)).outcome == Decision.REQUIRE_CONSENT


def test_wrong_operation_consent_is_rejected(tmp_path) -> None:
    shield = AgentShield(["PIPL"])
    harness = shield.create_harness("pipl", tmp_path)
    _seed_sensitive(harness)
    harness.enforce(
        LifecycleEvent(
            "pipl", 2, EventType.CONSENT_UPDATE, "user",
            data_object_ids=("health",), recipient="processor", purpose="benefits",
            metadata={
                "consent_id": "wrong-operation", "separate": True,
                "authorized_event_type": "MEMORY_WRITE",
            },
        )
    )
    assert harness.enforce(_transfer("pipl", 3)).outcome == Decision.REQUIRE_CONSENT


def test_unsafe_sensitive_persistent_storage_is_blocked(tmp_path) -> None:
    shield = AgentShield(["PIPL"])
    harness = shield.create_harness("pipl", tmp_path)
    _seed_sensitive(harness)
    result = harness.enforce(
        LifecycleEvent(
            "pipl", 2, EventType.MEMORY_WRITE, "agent",
            input={"record_reference": "health"}, data_object_ids=("health",), purpose="benefits",
            metadata={
                "has_lawful_basis": True, "purpose_compatible": True,
                "retention_bounded": False, "specific_purpose": True,
                "strictly_necessary": True, "protective_measures_confirmed": True,
            },
        )
    )
    assert result.outcome == Decision.BLOCK
    assert "PIPL_RETENTION_001" in result.decisions[0].violated_rules

