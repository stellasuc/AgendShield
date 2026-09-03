"""Broker-only effect gateway and private mock backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping

from agentshield.effects.models import EffectStatus
from agentshield.effects.store import SQLiteRuntimeStore


@dataclass(slots=True)
class _RawEmailBackend:
    messages: list[dict[str, Any]] = field(default_factory=list)

    def send(self, recipient: str, body: Any) -> dict[str, Any]:
        message = {"recipient": recipient, "body": body}
        self.messages.append(message)
        return {"status": "sent", "message_id": f"broker-email-{len(self.messages):03d}"}


@dataclass(slots=True)
class _RawMemoryBackend:
    entries: list[Any] = field(default_factory=list)

    def write(self, data: Any) -> dict[str, Any]:
        self.entries.append(data)
        return {"status": "stored", "index": len(self.entries) - 1}


class EffectGateway:
    """Only the broker constructs this object; agent clients receive an endpoint."""

    def __init__(self, store: SQLiteRuntimeStore) -> None:
        self.store = store
        self.__email_backend = _RawEmailBackend()
        self.__memory_backend = _RawMemoryBackend()

    def execute(
        self,
        transaction_id: str,
        capability_id: str,
        arguments: Mapping[str, Any],
    ) -> tuple[Any, dict[str, Any]]:
        transaction = self.store.get_transaction(transaction_id)
        if transaction.status != EffectStatus.EXECUTING:
            raise PermissionError(
                f"Gateway requires EXECUTING transaction; got {transaction.status.value}"
            )
        if transaction.capability_id != capability_id:
            raise PermissionError("Transaction capability does not match gateway dispatch")

        if capability_id == "email.send":
            result = self.__email_backend.send(str(arguments["recipient"]), arguments.get("body"))
            metadata = {
                **result,
                "recipient": str(arguments["recipient"]),
                "raw_pii": _contains_raw_pii(arguments.get("body")),
                "aggregate": _is_aggregate(arguments.get("body")),
                "body_fingerprint": _fingerprint(arguments.get("body")),
            }
            self._persist_effect(transaction, metadata)
            return result, metadata
        if capability_id == "memory.write":
            result = self.__memory_backend.write(arguments.get("data"))
            metadata = {
                **result,
                "raw_pii": _contains_raw_pii(arguments.get("data")),
                "data_fingerprint": _fingerprint(arguments.get("data")),
            }
            self._persist_effect(transaction, metadata)
            return result, metadata
        if capability_id == "response.release":
            value = arguments.get("response")
            metadata = {
                "status": "released",
                "raw_pii": _contains_raw_pii(value),
                "response": value,
                "response_fingerprint": _fingerprint(value),
            }
            self._persist_effect(transaction, metadata)
            return value, metadata
        if capability_id == "customer.read":
            dataset = str(arguments.get("dataset", "eu"))
            value = _sensitive_customers() if dataset == "sensitive" else _eu_customers()
            return value, {
                "status": "read",
                "records": len(value),
                "result_fingerprint": _fingerprint(value),
            }
        raise KeyError(f"No gateway implementation for capability: {capability_id}")

    def _persist_effect(self, transaction, metadata: Mapping[str, Any]) -> None:
        self.store.save_effect(
            effect_id=transaction.effect_id,
            transaction_id=transaction.transaction_id,
            capability_id=transaction.capability_id,
            status="SUCCEEDED",
            result_metadata=metadata,
            created_at=transaction.created_at,
            updated_at=transaction.updated_at,
        )

    def statistics(self) -> dict[str, int]:
        email_effects = self.store.list_effects("email.send")
        memory_effects = self.store.list_effects("memory.write")
        response_effects = self.store.list_effects("response.release")
        return {
            "email_messages": len(email_effects),
            "raw_pii_messages": sum(
                1 for effect in email_effects if effect["result_metadata"].get("raw_pii")
            ),
            "aggregate_messages": sum(
                1 for effect in email_effects if effect["result_metadata"].get("aggregate")
            ),
            "memory_entries": len(memory_effects),
            "released_responses": len(response_effects),
        }


def _eu_customers() -> list[dict[str, Any]]:
    return [
        {
            "customer_id": "cust-001",
            "name": "Alice Example",
            "email": "alice@example.test",
            "phone": "+49 30 5550101",
            "region": "EU",
        },
        {
            "customer_id": "cust-002",
            "name": "Bob Example",
            "email": "bob@example.test",
            "phone": "+33 1 5550102",
            "region": "EU",
        },
    ]


def _sensitive_customers() -> list[dict[str, Any]]:
    return [
        {
            "customer_id": "cn-001",
            "name": "Li Example",
            "email": "li@example.test",
            "passport_number": "E12345678",
            "medical_record": "cardiac treatment",
            "region": "CN",
        }
    ]


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return sha256(encoded).hexdigest()


def _contains_raw_pii(value: Any) -> bool:
    rendered = json.dumps(value, default=str).lower()
    indicators = (
        "alice@example.test",
        "bob@example.test",
        "li@example.test",
        "+49 30 5550101",
        "passport_number",
        "medical_record",
    )
    return any(indicator in rendered for indicator in indicators)


def _is_aggregate(value: Any) -> bool:
    return isinstance(value, Mapping) and set(value) == {"eu_customer_count"}
