"""Capability broker: policy verification, durable transaction, then dispatch."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from time import perf_counter
from typing import Any, Mapping

from agentshield.adapters.base import ToolRegistry, agentshield_tool
from agentshield.adapters.langgraph import LangGraphAdapter, ToolCallBlocked, ToolCallContext
from agentshield.approval.manager import ApprovalManager
from agentshield.capabilities.models import CapabilityRequest, CapabilityResponse
from agentshield.capabilities.registry import CapabilityRegistry
from agentshield.effects.gateway import EffectGateway
from agentshield.effects.models import EffectStatus, EffectTransaction
from agentshield.effects.store import SQLiteRuntimeStore
from agentshield.effects.transactions import TransactionManager
from agentshield.policy.rules import Decision
from agentshield.shield import AgentShield


class CapabilityBroker:
    """Owns protected backends; agent-side code receives only a BrokerClient."""

    def __init__(
        self,
        database: str | Path,
        *,
        regulations: tuple[str, ...] = ("GDPR",),
    ) -> None:
        self.database = Path(database)
        self.regulations = tuple(item.upper() for item in regulations)
        self.store = SQLiteRuntimeStore(self.database)
        self.capabilities = CapabilityRegistry()
        self.gateway = EffectGateway(self.store)
        self.transactions = TransactionManager()
        self.approvals = ApprovalManager(self.store)
        self._sessions: dict[str, LangGraphAdapter] = {}
        self._lock = RLock()
        self._tool_registry = self._build_tool_registry()
        self.last_metrics: dict[str, float] = {}

    def handle(self, request: CapabilityRequest) -> CapabilityResponse:
        with self._lock:
            self.last_metrics = {
                "policy_verification_ms": 0.0,
                "sqlite_persistence_ms": 0.0,
                "idempotency_lookup_ms": 0.0,
                "audit_persistence_ms": 0.0,
            }
            capability = self.capabilities.get(request.capability_id)
            effect_id = request.effect_id or self.transactions.create(request).effect_id
            if capability.side_effect:
                lookup_started = perf_counter()
                existing = self.store.get_succeeded_effect(effect_id)
                self.last_metrics["idempotency_lookup_ms"] += (
                    perf_counter() - lookup_started
                ) * 1000
                if existing is not None:
                    transaction = self.store.get_transaction(existing["transaction_id"])
                    self._audit(
                        transaction,
                        "IDEMPOTENT_REPLAY",
                        {"effect_id": effect_id, "capability_id": request.capability_id},
                    )
                    return self._response_from_replay(transaction, existing["result_metadata"])

            transaction = self.transactions.create(
                CapabilityRequest(
                    request_id=request.request_id,
                    trajectory_id=request.trajectory_id,
                    capability_id=request.capability_id,
                    arguments=request.arguments,
                    referenced_data_objects=request.referenced_data_objects,
                    effect_id=effect_id,
                )
            )
            self._save(transaction)
            self._audit(transaction, "TRANSACTION_CREATED", {"arguments": request.arguments})
            transaction = transaction.update(status=EffectStatus.CHECKING)
            self._save(transaction)
            if request.capability_id == "response.release":
                return self._handle_response(transaction)
            return self._handle_tool(transaction)

    def approve(
        self,
        transaction_id: str,
        *,
        scope: Mapping[str, Any] | None = None,
    ) -> CapabilityResponse:
        with self._lock:
            self.last_metrics = {
                "policy_verification_ms": 0.0,
                "sqlite_persistence_ms": 0.0,
                "idempotency_lookup_ms": 0.0,
                "audit_persistence_ms": 0.0,
            }
            transaction = self.store.get_transaction(transaction_id)
            if transaction.status != EffectStatus.WAITING_APPROVAL:
                raise ValueError(
                    f"Transaction {transaction_id} is not waiting for approval: {transaction.status.value}"
                )
            approval_id, approved_scope, elapsed = self.approvals.record(
                transaction, "APPROVED", scope
            )
            self.last_metrics["sqlite_persistence_ms"] += elapsed
            session = self._session(transaction.trajectory_id)
            self._hydrate_referenced_objects(session, transaction)
            session.record_approval(
                approval_id,
                data_object_ids=transaction.referenced_data_objects,
                purpose=str(approved_scope["purpose"]),
                recipient=approved_scope.get("recipient"),
                approved=True,
                separate_consent_evidence="PIPL" in self.regulations,
            )
            transaction = transaction.update(
                status=EffectStatus.CHECKING,
                approval_required=False,
                result_metadata={
                    **dict(transaction.result_metadata),
                    "approval_id": approval_id,
                    "approval_scope": approved_scope,
                },
            )
            self._save(transaction)
            self._audit(transaction, "APPROVAL_RECORDED", approved_scope)
            return self._handle_tool(transaction, approved=True)

    def deny(
        self,
        transaction_id: str,
        *,
        scope: Mapping[str, Any] | None = None,
    ) -> CapabilityResponse:
        with self._lock:
            transaction = self.store.get_transaction(transaction_id)
            if transaction.status != EffectStatus.WAITING_APPROVAL:
                raise ValueError("Only WAITING_APPROVAL transactions can be denied")
            approval_id, denied_scope, _ = self.approvals.record(transaction, "DENIED", scope)
            transaction = transaction.update(
                status=EffectStatus.BLOCKED,
                decision="DENIED",
                approval_required=False,
                result_metadata={"approval_id": approval_id, "approval_scope": denied_scope},
            )
            self._save(transaction)
            self._audit(transaction, "APPROVAL_DENIED", denied_scope)
            return self._response(transaction, disposition="DENIED")

    def resume_authorized(self, transaction_id: str) -> CapabilityResponse:
        self.last_metrics = {
            "policy_verification_ms": 0.0,
            "sqlite_persistence_ms": 0.0,
            "idempotency_lookup_ms": 0.0,
            "audit_persistence_ms": 0.0,
        }
        transaction = self.store.get_transaction(transaction_id)
        if transaction.status != EffectStatus.AUTHORIZED:
            raise ValueError("Only AUTHORIZED transactions can be resumed")
        transaction = transaction.update(status=EffectStatus.CHECKING)
        self._save(transaction)
        return self._handle_tool(transaction, approved=True)

    def statistics(self) -> dict[str, int]:
        return self.gateway.statistics()

    def _handle_tool(
        self,
        transaction: EffectTransaction,
        *,
        approved: bool = False,
    ) -> CapabilityResponse:
        session = self._session(transaction.trajectory_id)
        self._hydrate_referenced_objects(session, transaction)
        arguments = dict(transaction.original_arguments)
        if transaction.referenced_data_objects and "data_object_id" not in arguments:
            arguments["data_object_id"] = transaction.referenced_data_objects[0]
        arguments["_transaction_id"] = transaction.transaction_id
        trusted_policy_metadata: dict[str, Any] = {}
        if transaction.capability_id == "web.action.submit":
            # The broker, rather than the agent, derives this fact from the
            # classified object it is about to release. This permits ordinary
            # non-personal Web tasks while still forcing a repair for CRM pages
            # that carry direct identifiers.
            trusted_policy_metadata["is_minimized"] = not any(
                session.state.data_objects.get(object_id, None) is not None
                and session.state.data_objects[object_id].contains_personal_data is True
                for object_id in transaction.referenced_data_objects
            )
        if approved:
            trusted_policy_metadata.update(
                {
                    "has_lawful_basis": True,
                    "specific_purpose": True,
                    "strictly_necessary": True,
                    "protective_measures_confirmed": True,
                }
            )
        policy_started = perf_counter()
        try:
            context = session.before_tool_call(
                transaction.capability_id,
                arguments,
                trusted_policy_metadata=trusted_policy_metadata or None,
            )
        except ToolCallBlocked as exc:
            self.last_metrics["policy_verification_ms"] += (
                perf_counter() - policy_started
            ) * 1000
            context = exc.context
            rules = _activated_rules(context)
            waiting = exc.outcome in {Decision.REQUIRE_APPROVAL, Decision.REQUIRE_CONSENT}
            transaction = transaction.update(
                effective_arguments=(
                    dict(context.execution_arguments) if context else dict(arguments)
                ),
                decision=exc.outcome.value,
                activated_rules=rules,
                status=(EffectStatus.WAITING_APPROVAL if waiting else EffectStatus.BLOCKED),
                approval_required=waiting,
                result_metadata={
                    **dict(transaction.result_metadata),
                    "regulations": list(self.regulations),
                    "approval_scope": self.approvals.expected_scope(transaction),
                },
            )
            self._save(transaction)
            self._audit(
                transaction,
                "POLICY_DECISION",
                {
                    "decision": exc.outcome.value,
                    "shielding_plan": _shielding_plan(context),
                },
            )
            return self._response(
                transaction,
                disposition="WAITING_APPROVAL" if waiting else "BLOCKED",
            )
        self.last_metrics["policy_verification_ms"] += (
            perf_counter() - policy_started
        ) * 1000
        return self._authorize_and_execute(transaction, context)

    def _authorize_and_execute(
        self,
        transaction: EffectTransaction,
        context: ToolCallContext,
    ) -> CapabilityResponse:
        rules = _activated_rules(context)
        execution_transaction = transaction
        if context.enforcement.repair_attempts:
            transaction = transaction.update(
                decision="REPAIR",
                activated_rules=rules,
                status=EffectStatus.BLOCKED,
            )
            self._save(transaction)
            repair_strategy = _repair_strategy(context)
            self._audit(
                transaction,
                "POLICY_DECISION",
                {
                    "decision": "REPAIR",
                    "intervention": repair_strategy,
                    "data_object_ids": list(transaction.referenced_data_objects),
                    "shielding_plan": _shielding_plan(context),
                },
            )
            execution_transaction = EffectTransaction(
                transaction_id=self.transactions.create(
                    CapabilityRequest(
                        request_id=transaction.request_id,
                        trajectory_id=transaction.trajectory_id,
                        capability_id=transaction.capability_id,
                        arguments=transaction.original_arguments,
                        referenced_data_objects=context.data_object_ids,
                        effect_id=transaction.effect_id,
                    )
                ).transaction_id,
                effect_id=transaction.effect_id,
                request_id=transaction.request_id,
                trajectory_id=transaction.trajectory_id,
                capability_id=transaction.capability_id,
                original_arguments=transaction.original_arguments,
                effective_arguments=dict(context.execution_arguments),
                referenced_data_objects=context.data_object_ids,
                decision="ALLOW",
                activated_rules=rules,
                status=EffectStatus.AUTHORIZED,
                repair_parent=transaction.transaction_id,
                result_metadata={"regulations": list(self.regulations)},
            )
            self._save(execution_transaction)
            self._audit(
                execution_transaction,
                "DERIVED_OBJECT",
                {
                    "data_object_id": (
                        context.data_object_ids[0] if context.data_object_ids else None
                    ),
                    "source_data_object_ids": list(transaction.referenced_data_objects),
                    "transformation": repair_strategy,
                },
            )
            context = replace(
                context,
                execution_arguments={
                    **dict(context.execution_arguments),
                    "_transaction_id": execution_transaction.transaction_id,
                },
            )
        else:
            execution_transaction = transaction.update(
                effective_arguments=dict(context.execution_arguments),
                referenced_data_objects=context.data_object_ids,
                decision="ALLOW",
                activated_rules=rules,
                status=EffectStatus.AUTHORIZED,
                result_metadata={
                    **dict(transaction.result_metadata),
                    "regulations": list(self.regulations),
                },
            )
            self._save(execution_transaction)
        self._audit(
            execution_transaction,
            "AUTHORIZED",
            {
                "decision": "ALLOW",
                "shielding_plan": _shielding_plan(context),
            },
        )
        execution_transaction = execution_transaction.update(
            status=EffectStatus.EXECUTING,
            execution_attempts=execution_transaction.execution_attempts + 1,
        )
        self._save(execution_transaction)
        try:
            observation = self._session(execution_transaction.trajectory_id).execute_tool(context)
            effect = self.store.get_succeeded_effect(execution_transaction.effect_id)
            result_metadata = (
                dict(effect["result_metadata"])
                if effect
                else _safe_read_metadata(observation.value)
            )
            if observation.data_object_id:
                result_metadata["data_object_id"] = observation.data_object_id
                object_summary = _data_object_summary(
                    self._session(execution_transaction.trajectory_id),
                    observation.data_object_id,
                )
                if object_summary:
                    self._audit(
                        execution_transaction,
                        "DATA_OBJECT_OBSERVED",
                        object_summary,
                    )
            execution_transaction = execution_transaction.update(
                status=EffectStatus.SUCCEEDED,
                result_metadata={
                    **dict(execution_transaction.result_metadata),
                    **result_metadata,
                },
            )
            self._save(execution_transaction)
            self._audit(execution_transaction, "EFFECT_SUCCEEDED", result_metadata)
            return self._response(
                execution_transaction,
                value=observation.value,
                data_object_id=observation.data_object_id,
                disposition=(
                    "REPAIRED_AND_EXECUTED"
                    if execution_transaction.repair_parent
                    else "EXECUTED"
                ),
            )
        except BaseException as exc:
            execution_transaction = execution_transaction.update(
                status=EffectStatus.FAILED,
                error=f"{type(exc).__name__}: {exc}",
            )
            self._save(execution_transaction)
            self._audit(execution_transaction, "EFFECT_FAILED", {"error": str(exc)})
            return self._response(execution_transaction, disposition="FAILED", error=str(exc))

    def _handle_response(self, transaction: EffectTransaction) -> CapabilityResponse:
        session = self._session(transaction.trajectory_id)
        self._hydrate_referenced_objects(session, transaction)
        policy_started = perf_counter()
        try:
            released = session.before_response_release(
                transaction.original_arguments.get("response"),
                transaction.referenced_data_objects,
            )
        except ToolCallBlocked as exc:
            self.last_metrics["policy_verification_ms"] += (
                perf_counter() - policy_started
            ) * 1000
            transaction = transaction.update(
                decision=exc.outcome.value,
                status=EffectStatus.WAITING_APPROVAL,
                approval_required=True,
                result_metadata={"regulations": list(self.regulations)},
            )
            self._save(transaction)
            return self._response(transaction, disposition="WAITING_APPROVAL")
        self.last_metrics["policy_verification_ms"] += (
            perf_counter() - policy_started
        ) * 1000
        transaction = transaction.update(
            effective_arguments={"response": released},
            decision="ALLOW",
            status=EffectStatus.AUTHORIZED,
            result_metadata={"regulations": list(self.regulations)},
        )
        self._save(transaction)
        transaction = transaction.update(
            status=EffectStatus.EXECUTING,
            execution_attempts=transaction.execution_attempts + 1,
        )
        self._save(transaction)
        try:
            value, _ = self.gateway.execute(
                transaction.transaction_id,
                transaction.capability_id,
                transaction.effective_arguments,
            )
            effect = self.store.get_succeeded_effect(transaction.effect_id)
            transaction = transaction.update(
                status=EffectStatus.SUCCEEDED,
                result_metadata={
                    **dict(transaction.result_metadata),
                    **dict(effect["result_metadata"] if effect else {}),
                },
            )
            self._save(transaction)
            self._audit(transaction, "EFFECT_SUCCEEDED", {"value": value})
            return self._response(transaction, value=value, disposition="EXECUTED")
        except BaseException as exc:
            transaction = transaction.update(status=EffectStatus.FAILED, error=str(exc))
            self._save(transaction)
            return self._response(transaction, disposition="FAILED", error=str(exc))

    def _session(self, trajectory_id: str) -> LangGraphAdapter:
        if trajectory_id not in self._sessions:
            shield = AgentShield(self.regulations)
            self._sessions[trajectory_id] = LangGraphAdapter(
                shield,
                self._tool_registry,
                trajectory_id=trajectory_id,
                audit_directory=self.database.parent / "audit",
            )
        return self._sessions[trajectory_id]

    def _hydrate_referenced_objects(
        self,
        session: LangGraphAdapter,
        transaction: EffectTransaction,
    ) -> None:
        payload = (
            transaction.original_arguments.get("body")
            if "body" in transaction.original_arguments
            else transaction.original_arguments.get("data")
            if "data" in transaction.original_arguments
            else transaction.original_arguments.get("response")
        )
        for object_id in transaction.referenced_data_objects:
            if object_id not in session.state.data_objects and payload is not None:
                session.ingest_data_object(object_id, payload)

    def _build_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()

        @agentshield_tool(
            side_effect=False,
            data_source=True,
            trust_boundary="internal",
            source_trust_level="broker_protected",
        )
        def customer_read(_transaction_id: str, dataset: str = "eu"):
            return self.gateway.execute(_transaction_id, "customer.read", {"dataset": dataset})[0]

        @agentshield_tool(
            side_effect=False,
            data_source=True,
            trust_boundary="external",
            source_trust_level="untrusted_web_environment",
        )
        def web_page_read(_transaction_id: str, environment: str):
            return self.gateway.execute(
                _transaction_id,
                "web.page.read",
                {"environment": environment},
            )[0]

        @agentshield_tool(
            side_effect=True,
            data_sink=True,
            trust_boundary="external",
            source_trust_level="external",
        )
        def web_action_submit(
            _transaction_id: str,
            environment: str,
            action: str,
            recipient: str,
            body: Any,
        ):
            return self.gateway.execute(
                _transaction_id,
                "web.action.submit",
                {
                    "environment": environment,
                    "action": action,
                    "recipient": recipient,
                    "body": body,
                },
            )[0]

        @agentshield_tool(
            side_effect=True,
            data_sink=True,
            trust_boundary="external",
            source_trust_level="external",
        )
        def email_send(_transaction_id: str, recipient: str, body: Any):
            return self.gateway.execute(
                _transaction_id, "email.send", {"recipient": recipient, "body": body}
            )[0]

        @agentshield_tool(
            side_effect=True,
            data_sink=True,
            persistent_storage=True,
            trust_boundary="internal",
            source_trust_level="broker_protected",
        )
        def memory_write(_transaction_id: str, data: Any):
            return self.gateway.execute(_transaction_id, "memory.write", {"data": data})[0]

        registry.register(customer_read, name="customer.read", result_object_prefix="customer-records")
        registry.register(
            web_page_read,
            name="web.page.read",
            result_object_prefix="web-page",
        )
        registry.register(
            web_action_submit,
            name="web.action.submit",
            policy_metadata={
                "has_lawful_basis": True,
                "purpose_compatible": True,
                "recipient_disclosed": True,
                "recipient_notified": True,
                "is_minimized": False,
                "cross_border": False,
            },
        )
        registry.register(
            email_send,
            name="email.send",
            policy_metadata={
                "has_lawful_basis": True,
                "purpose_compatible": True,
                "recipient_disclosed": True,
                "recipient_notified": True,
                "is_minimized": "PIPL" in self.regulations,
                "cross_border": False,
            },
        )
        registry.register(
            memory_write,
            name="memory.write",
            policy_metadata={
                "has_lawful_basis": True,
                "purpose_compatible": True,
                "retention_bounded": False,
            },
        )
        return registry

    def _save(self, transaction: EffectTransaction) -> None:
        self.last_metrics.setdefault("sqlite_persistence_ms", 0.0)
        self.last_metrics["sqlite_persistence_ms"] += self.store.save_transaction(transaction)

    def _audit(
        self,
        transaction: EffectTransaction,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> None:
        self.last_metrics.setdefault("audit_persistence_ms", 0.0)
        self.last_metrics["audit_persistence_ms"] += self.store.append_audit(
            transaction.trajectory_id,
            transaction.transaction_id,
            event_type,
            {
                **dict(payload),
                "effect_id": transaction.effect_id,
                "capability_id": transaction.capability_id,
                "status": transaction.status.value,
                "decision": transaction.decision,
                "activated_rules": list(transaction.activated_rules),
            },
            datetime.now(timezone.utc).isoformat(),
        )

    def _response(
        self,
        transaction: EffectTransaction,
        *,
        value: Any = None,
        data_object_id: str | None = None,
        disposition: str,
        error: str | None = None,
    ) -> CapabilityResponse:
        return CapabilityResponse(
            transaction_id=transaction.transaction_id,
            effect_id=transaction.effect_id,
            status=transaction.status.value,
            decision=transaction.decision,
            value=value,
            data_object_id=data_object_id,
            disposition=disposition,
            activated_rules=transaction.activated_rules,
            error=error or transaction.error,
        )

    def _response_from_replay(
        self,
        transaction: EffectTransaction,
        result_metadata: Mapping[str, Any],
    ) -> CapabilityResponse:
        if transaction.capability_id == "response.release":
            value = result_metadata.get("response")
        else:
            value = {
                key: value
                for key, value in result_metadata.items()
                if key in {"status", "message_id", "index"}
            }
        return CapabilityResponse(
            transaction_id=transaction.transaction_id,
            effect_id=transaction.effect_id,
            status=EffectStatus.SUCCEEDED.value,
            decision=transaction.decision,
            value=value,
            data_object_id=transaction.result_metadata.get("data_object_id"),
            replayed=True,
            disposition="IDEMPOTENT_REPLAY",
            activated_rules=transaction.activated_rules,
        )


def _activated_rules(context: ToolCallContext | None) -> tuple[str, ...]:
    if context is None:
        return ()
    return tuple(
        dict.fromkeys(
            rule
            for decision in context.enforcement.decisions
            for rule in (*decision.activated_rules, *decision.violated_rules)
        )
    )


def _shielding_plan(context: ToolCallContext | None) -> Mapping[str, object] | None:
    if context is None or not context.enforcement.shielding_plans:
        return None
    return context.enforcement.shielding_plans[-1].audit_view()


def _repair_strategy(context: ToolCallContext) -> str:
    for decision in context.enforcement.decisions:
        if decision.required_intervention is not None:
            return decision.required_intervention.value
    return "REPAIR"


def _data_object_summary(
    session: LangGraphAdapter,
    object_id: str,
) -> dict[str, Any]:
    data_object = session.state.data_objects.get(object_id)
    if data_object is None:
        return {}
    return {
        "data_object_id": data_object.object_id,
        "classification": data_object.classification.name,
        "contains_personal_data": data_object.contains_personal_data,
        "contains_sensitive_data": data_object.contains_sensitive_data,
        "categories": list(data_object.categories),
        "sensitive_categories": list(data_object.sensitive_categories),
        "source": data_object.source,
        "purpose": data_object.purpose,
        "transformations": list(data_object.transformations),
        "detectors": list(data_object.detectors),
    }


def _safe_read_metadata(value: Any) -> dict[str, Any]:
    return {"status": "read", "records": len(value) if isinstance(value, list) else 1}
