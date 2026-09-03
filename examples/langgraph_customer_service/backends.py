"""Local-only demo backends. No external messages or persistent data are sent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MockCRM:
    customers: list[dict[str, Any]] = field(
        default_factory=lambda: [
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
            {
                "customer_id": "cust-003",
                "name": "Carol Example",
                "email": "carol@example.test",
                "phone": "+1 202 555 0103",
                "region": "US",
            },
        ]
    )
    search_calls: int = 0

    def search(self, region: str) -> list[dict[str, Any]]:
        self.search_calls += 1
        return [dict(customer) for customer in self.customers if customer["region"] == region]

    def get(self, customer_id: str) -> dict[str, Any] | None:
        return next(
            (dict(customer) for customer in self.customers if customer["customer_id"] == customer_id),
            None,
        )


@dataclass(slots=True)
class MockEmail:
    outbox: list[dict[str, Any]] = field(default_factory=list)
    calls: int = 0
    fail_next: bool = False

    def send(self, recipient: str, body: Any) -> dict[str, Any]:
        self.calls += 1
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("injected mock email failure")
        message = {"recipient": recipient, "body": body}
        self.outbox.append(message)
        return {"status": "sent", "message_id": f"mock-{self.calls:03d}"}


@dataclass(slots=True)
class MockMemoryStore:
    entries: list[Any] = field(default_factory=list)
    calls: int = 0

    def save(self, data: Any) -> dict[str, Any]:
        self.calls += 1
        self.entries.append(data)
        return {"status": "stored", "index": len(self.entries) - 1}

