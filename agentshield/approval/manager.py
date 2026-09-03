"""Minimal scoped approval validation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from agentshield.effects.models import EffectTransaction
from agentshield.effects.store import SQLiteRuntimeStore


class ApprovalScopeError(ValueError):
    pass


class ApprovalManager:
    def __init__(self, store: SQLiteRuntimeStore) -> None:
        self.store = store

    @staticmethod
    def expected_scope(transaction: EffectTransaction) -> dict[str, Any]:
        arguments = transaction.original_arguments
        return {
            "data_objects": sorted(transaction.referenced_data_objects),
            "purpose": str(arguments.get("purpose", "customer_service")),
            "recipient": arguments.get("recipient"),
            "operation": transaction.capability_id,
        }

    def record(
        self,
        transaction: EffectTransaction,
        decision: str,
        scope: Mapping[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any], float]:
        expected = self.expected_scope(transaction)
        supplied = dict(scope or expected)
        supplied["data_objects"] = sorted(supplied.get("data_objects") or [])
        if supplied != expected:
            raise ApprovalScopeError(
                f"Approval scope mismatch; expected {expected!r}, received {supplied!r}"
            )
        approval_id = f"AP-{uuid4().hex[:12]}"
        elapsed = self.store.save_approval(
            approval_id,
            transaction.transaction_id,
            decision,
            supplied,
            datetime.now(timezone.utc).isoformat(),
        )
        return approval_id, supplied, elapsed
