"""Small transaction state helper; intentionally not a workflow engine."""

from __future__ import annotations

from uuid import uuid4

from agentshield.capabilities.models import CapabilityRequest
from agentshield.effects.idempotency import effect_id_for
from agentshield.effects.models import EffectStatus, EffectTransaction


class TransactionManager:
    def create(self, request: CapabilityRequest) -> EffectTransaction:
        effect_id = request.effect_id or effect_id_for(
            request.trajectory_id,
            request.capability_id,
            request.arguments,
            request.referenced_data_objects,
        )
        return EffectTransaction(
            transaction_id=f"TX-{uuid4().hex[:12]}",
            effect_id=effect_id,
            request_id=request.request_id,
            trajectory_id=request.trajectory_id,
            capability_id=request.capability_id,
            original_arguments=dict(request.arguments),
            effective_arguments=dict(request.arguments),
            referenced_data_objects=request.referenced_data_objects,
        )

    @staticmethod
    def transition(transaction: EffectTransaction, status: EffectStatus, **changes):
        return transaction.update(status=status, **changes)
