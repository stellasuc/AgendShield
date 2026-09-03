from __future__ import annotations

import json

import pytest

from agentshield.capabilities.broker import CapabilityBroker
from agentshield.capabilities.client import BrokerClient
from agentshield.capabilities.models import CapabilityRequest
from agentshield.capabilities.service import BrokerServiceProcess
from agentshield.effects.models import EffectStatus
from agentshield.effects.store import SQLiteRuntimeStore
from agentshield.effects.transactions import TransactionManager
from examples.langgraph_customer_service.brokered import build_brokered_customer_service_agent


def _request(
    capability: str,
    arguments: dict,
    *,
    trajectory: str = "broker-security-test",
    refs: tuple[str, ...] = (),
    effect_id: str | None = None,
):
    return CapabilityRequest(
        trajectory_id=trajectory,
        capability_id=capability,
        arguments=arguments,
        referenced_data_objects=refs,
        effect_id=effect_id,
    )


def _read(broker: CapabilityBroker, *, trajectory="broker-security-test", sensitive=False):
    return broker.handle(
        _request(
            "customer.read",
            {"dataset": "sensitive" if sensitive else "eu"},
            trajectory=trajectory,
        )
    )


def _sensitive_waiting(database, *, trajectory="pipl-waiting"):
    broker = CapabilityBroker(database, regulations=("PIPL",))
    read = _read(broker, trajectory=trajectory, sensitive=True)
    waiting = broker.handle(
        _request(
            "email.send",
            {
                "recipient": "partner@example.test",
                "body": read.value,
                "purpose": "customer_service",
            },
            trajectory=trajectory,
            refs=(read.data_object_id,),
        )
    )
    return broker, read, waiting


def test_unregistered_capability_is_rejected_before_transaction(tmp_path):
    broker = CapabilityBroker(tmp_path / "runtime.db")
    with pytest.raises(KeyError, match="Unregistered capability"):
        broker.handle(_request("shell.exec", {"command": "id"}))
    assert broker.store.list_transactions() == ()


def test_gdpr_raw_transfer_is_repaired_and_raw_pii_never_reaches_gateway(tmp_path):
    broker = CapabilityBroker(tmp_path / "runtime.db")
    read = _read(broker)
    result = broker.handle(
        _request(
            "email.send",
            {
                "recipient": "partner@example.test",
                "body": read.value,
                "purpose": "customer_service",
            },
            refs=(read.data_object_id,),
        )
    )
    assert result.status == "SUCCEEDED"
    assert result.disposition == "REPAIRED_AND_EXECUTED"
    assert broker.statistics() == {
        "email_messages": 1,
        "raw_pii_messages": 0,
        "aggregate_messages": 1,
        "memory_entries": 0,
        "released_responses": 0,
        "web_actions": 0,
    }


def test_repaired_effect_has_parent_transaction_and_is_reverified(tmp_path):
    broker = CapabilityBroker(tmp_path / "runtime.db")
    read = _read(broker)
    broker.handle(
        _request(
            "email.send",
            {"recipient": "partner@example.test", "body": read.value},
            refs=(read.data_object_id,),
        )
    )
    transfers = [
        item for item in broker.store.list_transactions() if item.capability_id == "email.send"
    ]
    assert len(transfers) == 2
    parent = next(item for item in transfers if item.repair_parent is None)
    child = next(item for item in transfers if item.repair_parent is not None)
    assert parent.status == EffectStatus.BLOCKED
    assert parent.decision == "REPAIR"
    assert child.repair_parent == parent.transaction_id
    assert child.status == EffectStatus.SUCCEEDED
    assert child.decision == "ALLOW"
    assert child.execution_attempts == 1


def test_memory_block_occurs_before_persistence(tmp_path):
    broker = CapabilityBroker(tmp_path / "runtime.db")
    read = _read(broker)
    result = broker.handle(
        _request(
            "memory.write",
            {"data": read.value, "purpose": "customer_service"},
            refs=(read.data_object_id,),
        )
    )
    assert result.status == "BLOCKED"
    assert broker.statistics()["memory_entries"] == 0


def test_blocked_memory_retry_remains_blocked(tmp_path):
    broker = CapabilityBroker(tmp_path / "runtime.db")
    read = _read(broker)
    request = _request(
        "memory.write",
        {"data": read.value, "purpose": "customer_service"},
        refs=(read.data_object_id,),
    )
    assert broker.handle(request).status == "BLOCKED"
    assert broker.handle(request).status == "BLOCKED"
    assert broker.statistics()["memory_entries"] == 0


def test_response_release_redacts_before_gateway(tmp_path):
    broker = CapabilityBroker(tmp_path / "runtime.db")
    result = broker.handle(
        _request(
            "response.release",
            {"response": {"email": "alice@example.test", "summary": "ok"}},
        )
    )
    assert result.value == {"email": "[REDACTED]", "summary": "ok"}
    effect = broker.store.list_effects("response.release")[0]
    assert effect["result_metadata"]["raw_pii"] is False


def test_gateway_rejects_unauthorized_transaction(tmp_path):
    broker = CapabilityBroker(tmp_path / "runtime.db")
    transaction = TransactionManager().create(
        _request("email.send", {"recipient": "x@example.test", "body": {"count": 1}})
    )
    broker.store.save_transaction(transaction)
    with pytest.raises(PermissionError, match="requires EXECUTING"):
        broker.gateway.execute(
            transaction.transaction_id,
            "email.send",
            transaction.original_arguments,
        )


def test_successful_effect_is_idempotent_in_same_broker(tmp_path):
    broker = CapabilityBroker(tmp_path / "runtime.db")
    request = _request(
        "email.send",
        {"recipient": "partner@example.test", "body": {"eu_customer_count": 2}},
        effect_id="EF-SAME-BROKER",
    )
    first = broker.handle(request)
    replay = broker.handle(request)
    assert first.disposition == "EXECUTED"
    assert replay.disposition == "IDEMPOTENT_REPLAY"
    assert replay.replayed is True
    assert broker.statistics()["email_messages"] == 1


def test_idempotency_survives_broker_restart(tmp_path):
    database = tmp_path / "runtime.db"
    request = _request(
        "email.send",
        {"recipient": "partner@example.test", "body": {"eu_customer_count": 2}},
        effect_id="EF-RESTART",
    )
    assert CapabilityBroker(database).handle(request).status == "SUCCEEDED"
    restarted = CapabilityBroker(database)
    replay = restarted.handle(request)
    assert replay.disposition == "IDEMPOTENT_REPLAY"
    assert restarted.statistics()["email_messages"] == 1


def test_waiting_approval_survives_restart(tmp_path):
    database = tmp_path / "runtime.db"
    _, _, waiting = _sensitive_waiting(database)
    assert waiting.status == "WAITING_APPROVAL"
    restarted = CapabilityBroker(database, regulations=("PIPL",))
    transaction = restarted.store.get_transaction(waiting.transaction_id)
    assert transaction.status == EffectStatus.WAITING_APPROVAL
    assert restarted.statistics()["email_messages"] == 0


def test_wrong_approval_scope_is_rejected(tmp_path):
    broker, _, waiting = _sensitive_waiting(tmp_path / "runtime.db")
    with pytest.raises(ValueError, match="scope mismatch"):
        broker.approve(
            waiting.transaction_id,
            scope={
                "data_objects": ["wrong-object"],
                "purpose": "customer_service",
                "recipient": "partner@example.test",
                "operation": "email.send",
            },
        )
    assert broker.statistics()["email_messages"] == 0


def test_approved_transaction_is_reverified_then_executes(tmp_path):
    database = tmp_path / "runtime.db"
    _, _, waiting = _sensitive_waiting(database)
    restarted = CapabilityBroker(database, regulations=("PIPL",))
    approved = restarted.approve(waiting.transaction_id)
    transaction = restarted.store.get_transaction(waiting.transaction_id)
    assert approved.status == "SUCCEEDED"
    assert transaction.execution_attempts == 1
    assert "PIPL_SENSITIVE_PROCESSING_001" in transaction.activated_rules
    event_types = [
        item["event_type"]
        for item in restarted.store.read_audit("pipl-waiting")
        if item["transaction_id"] == waiting.transaction_id
    ]
    assert event_types.index("APPROVAL_RECORDED") < event_types.index("AUTHORIZED")
    assert restarted.statistics()["email_messages"] == 1


def test_denied_transaction_never_executes(tmp_path):
    broker, _, waiting = _sensitive_waiting(tmp_path / "runtime.db")
    denied = broker.deny(waiting.transaction_id)
    assert denied.status == "BLOCKED"
    assert denied.decision == "DENIED"
    assert broker.statistics()["email_messages"] == 0


def test_sqlite_audit_never_stores_raw_sensitive_payload(tmp_path):
    broker = CapabilityBroker(tmp_path / "runtime.db")
    read = _read(broker)
    broker.handle(
        _request(
            "email.send",
            {"recipient": "partner@example.test", "body": read.value},
            refs=(read.data_object_id,),
        )
    )
    rendered = json.dumps(broker.store.read_audit("broker-security-test"), default=str)
    assert "alice@example.test" not in rendered
    assert "+49 30 5550101" not in rendered
    assert "arguments_fingerprint" in rendered


def test_executing_transaction_recovers_to_human_review(tmp_path):
    database = tmp_path / "runtime.db"
    store = SQLiteRuntimeStore(database)
    transaction = TransactionManager().create(
        _request("email.send", {"recipient": "x@example.test", "body": {"count": 1}})
    ).update(status=EffectStatus.EXECUTING)
    store.save_transaction(transaction)
    restarted = SQLiteRuntimeStore(database)
    recovered = restarted.get_transaction(transaction.transaction_id)
    assert recovered.status == EffectStatus.REQUIRE_HUMAN_REVIEW
    assert "outcome is unknown" in recovered.error


def test_authorized_transaction_can_be_reverified_and_resumed(tmp_path):
    database = tmp_path / "runtime.db"
    broker = CapabilityBroker(database)
    transaction = TransactionManager().create(
        _request(
            "email.send",
            {"recipient": "partner@example.test", "body": {"eu_customer_count": 2}},
        )
    ).update(status=EffectStatus.AUTHORIZED, decision="ALLOW")
    broker.store.save_transaction(transaction)
    result = CapabilityBroker(database).resume_authorized(transaction.transaction_id)
    assert result.status == "SUCCEEDED"
    assert result.disposition == "EXECUTED"


def test_customer_read_creates_data_object_for_later_provenance(tmp_path):
    broker = CapabilityBroker(tmp_path / "runtime.db")
    result = _read(broker)
    assert result.status == "SUCCEEDED"
    assert result.data_object_id == "customer-records-001"
    assert len(result.value) == 2


def test_normal_brokered_agent_api_exposes_no_raw_backend_handle():
    client = BrokerClient("http://127.0.0.1:1")
    agent = build_brokered_customer_service_agent(client, trajectory_id="surface-test")
    forbidden = ("email", "memory", "gateway", "tool_registry", "raw_email_backend")
    assert not any(hasattr(agent, name) for name in forbidden)
    assert not any(hasattr(agent.runtime, name) for name in forbidden)
    assert set(BrokerClient.__slots__) == {"endpoint", "timeout"}


def test_loopback_service_runs_in_separate_process(tmp_path):
    service = BrokerServiceProcess(tmp_path / "runtime.db")
    with service as client:
        health = client.health()
        assert health["status"] == "ok"
        import os

        assert health["pid"] != os.getpid()


def test_cli_safe_transaction_view_fingerprints_arguments(tmp_path, capsys):
    from agentshield.cli import _transaction_view, main

    database = tmp_path / "runtime.db"
    broker = CapabilityBroker(database)
    read = _read(broker)
    transaction = broker.store.list_transactions()[0].update(
        result_metadata={
            "status": "read",
            "value": {"email": "alice@example.test"},
        }
    )
    view = _transaction_view(transaction)
    rendered = json.dumps(view)
    assert "alice@example.test" not in rendered
    assert view["original_arguments"]["sha256"]
    assert view["result_metadata"]["value"]["sha256"]
    assert main(["audit", "broker-security-test", "--db", str(database)]) == 0
    output = capsys.readouterr().out
    assert "TRANSACTION_CREATED" in output
    assert "EFFECT_SUCCEEDED" in output
    assert "SUCCEEDED ALLOW" in output
