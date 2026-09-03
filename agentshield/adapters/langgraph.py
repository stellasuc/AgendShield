"""LangGraph runtime gateway with pre-effect compliance enforcement."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Protocol, TYPE_CHECKING
from uuid import uuid4

from agentshield.adapters.base import (
    AdapterCapabilities,
    AgentRuntimeAdapter,
    ToolRegistry,
    ToolRiskMetadata,
)
from agentshield.audit.models import AuditEntry
from agentshield.intervention.repair import derived_object_id, redact_payload
from agentshield.policy.rules import Decision
from agentshield.runtime.harness import EnforcementResult
from agentshield.runtime.lifecycle import EventType, LifecycleEvent

if TYPE_CHECKING:
    from agentshield.shield import AgentShield


class LangGraphRuntimeBindable(Protocol):
    """An agent that can rebuild the same graph around a runtime gateway."""

    tool_registry: ToolRegistry

    def with_runtime(self, runtime: "ToolRuntimeGateway") -> Any: ...


@dataclass(frozen=True, slots=True)
class ToolObservation:
    value: Any
    data_object_id: str | None = None
    tool_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class ToolCallContext:
    tool: str
    original_arguments: Mapping[str, Any]
    execution_arguments: Mapping[str, Any]
    risk: ToolRiskMetadata
    event_id: str
    tool_call_id: str
    correlation_id: str
    data_object_ids: tuple[str, ...]
    enforcement: EnforcementResult


class ToolCallBlocked(RuntimeError):
    def __init__(
        self,
        tool: str,
        outcome: Decision,
        explanation: str,
        *,
        context: ToolCallContext | None = None,
    ) -> None:
        super().__init__(f"Tool {tool!r} was not executed: {outcome.value}: {explanation}")
        self.tool = tool
        self.outcome = outcome
        self.context = context


class AdapterContractError(TypeError):
    pass


class ToolRuntimeGateway(Protocol):
    def call_tool(self, tool: str, **arguments: Any) -> ToolObservation: ...


class PassthroughLangGraphRuntime:
    """Unprotected execution of the same graph and registered mock tools."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry
        self._objects: defaultdict[str, int] = defaultdict(int)
        self.tool_trace: list[dict[str, Any]] = []

    def call_tool(self, tool: str, **arguments: Any) -> ToolObservation:
        result = self.registry.invoke(tool, arguments)
        spec = self.registry.spec(tool)
        object_id = None
        if spec.risk.data_source:
            prefix = spec.result_object_prefix or f"{tool}-result"
            self._objects[prefix] += 1
            object_id = f"{prefix}-{self._objects[prefix]:03d}"
        self.tool_trace.append(
            {"tool": tool, "arguments": dict(arguments), "result_object_id": object_id}
        )
        return ToolObservation(result, object_id, str(uuid4()))


class LangGraphAdapter(AgentRuntimeAdapter):
    """Per-invocation state, sequencing, enforcement, and tool dispatch."""

    capabilities = AdapterCapabilities(plan=False, parallel_tool_calls=False)

    def __init__(
        self,
        shield: "AgentShield",
        registry: ToolRegistry,
        *,
        trajectory_id: str,
        audit_directory: str | Path,
        enforcement_mode: str = "enforce",
    ) -> None:
        if enforcement_mode not in {"audit", "enforce"}:
            raise ValueError("enforcement_mode must be 'audit' or 'enforce'")
        self.shield = shield
        self.registry = registry
        self.trajectory_id = trajectory_id
        self.enforcement_mode = enforcement_mode
        self.harness = shield.create_harness(trajectory_id, audit_directory)
        self._sequence = -1
        self._lock = RLock()
        self._objects: defaultdict[str, int] = defaultdict(int)
        self._payloads: dict[str, Any] = {}
        self._uncertain_objects: set[str] = set()
        self._allowed_calls: dict[str, ToolCallContext] = {}
        self._last_event_id: str | None = None
        self.tool_trace: list[dict[str, Any]] = []

    @property
    def state(self):
        return self.harness.state

    @property
    def audit_path(self) -> Path:
        return self.harness.audit.directory / f"{self.trajectory_id}.jsonl"

    def _next_sequence(self) -> int:
        last = int(self.state.audit_metadata.get("last_sequence", -1))
        self._sequence = max(self._sequence, last) + 1
        return self._sequence

    def _event(
        self,
        event_type: EventType,
        *,
        actor: str,
        parent_event_ids: tuple[str, ...] = (),
        correlation_id: str | None = None,
        tool_call_id: str | None = None,
        **values: Any,
    ) -> LifecycleEvent:
        return LifecycleEvent(
            trajectory_id=self.trajectory_id,
            sequence=self._next_sequence(),
            event_type=event_type,
            actor=actor,
            parent_event_ids=parent_event_ids,
            correlation_id=correlation_id,
            tool_call_id=tool_call_id,
            **values,
        )

    def _enforce(self, event: LifecycleEvent) -> EnforcementResult:
        result = self.harness.enforce(event)
        self._sequence = max(
            self._sequence,
            int(self.state.audit_metadata.get("last_sequence", self._sequence)),
        )
        if result.final_event is not None:
            self._last_event_id = result.final_event.event_id
        else:
            self._last_event_id = event.event_id
        return result

    def on_user_request(self, request: Any) -> EnforcementResult:
        event = self._event(
            EventType.USER_REQUEST,
            actor="user",
            input=request,
            purpose=_request_purpose(request),
            metadata={"task_context": {"adapter": "langgraph", "run_id": self.trajectory_id}},
        )
        return self._enforce(event)

    def before_tool_call(
        self,
        tool: str,
        arguments: Mapping[str, Any],
        *,
        trusted_policy_metadata: Mapping[str, Any] | None = None,
    ) -> ToolCallContext:
        with self._lock:
            spec = self.registry.spec(tool)
            if spec.risk.persistent_storage:
                return self.before_memory_write(
                    tool,
                    arguments,
                    trusted_policy_metadata=trusted_policy_metadata,
                )
            return self._precheck(
                tool,
                arguments,
                spec.risk,
                trusted_policy_metadata=trusted_policy_metadata,
            )

    def _precheck(
        self,
        tool: str,
        arguments: Mapping[str, Any],
        risk: ToolRiskMetadata,
        *,
        force_event_type: EventType | None = None,
        trusted_policy_metadata: Mapping[str, Any] | None = None,
    ) -> ToolCallContext:
        spec = self.registry.spec(tool)
        tool_call_id = str(uuid4())
        correlation_id = str(uuid4())
        object_ids = self._resolve_object_ids(arguments)
        event_type = force_event_type or (
            EventType.EXTERNAL_TRANSFER
            if risk.data_sink and risk.trust_boundary == "external"
            else EventType.TOOL_CALL
        )
        metadata = {
            "runtime_phase": "TOOL_CALL_PROPOSED",
            "side_effectful": risk.side_effect is not False,
            "data_sink": risk.data_sink,
            "trust_boundary": risk.trust_boundary,
            "recipient_type": "external" if risk.trust_boundary == "external" else "internal",
            **dict(spec.policy_metadata),
            **dict(trusted_policy_metadata or {}),
        }
        if object_ids and event_type == EventType.EXTERNAL_TRANSFER:
            replacement = self._aggregate_replacement(arguments, object_ids)
            if replacement is not None:
                metadata["aggregate_replacement"] = replacement
        event = self._event(
            event_type,
            actor="agent",
            tool=tool,
            input=dict(arguments),
            data_object_ids=object_ids,
            recipient=_argument(arguments, "recipient"),
            purpose=_argument(arguments, "purpose") or "customer_service",
            metadata=metadata,
            parent_event_ids=((self._last_event_id,) if self._last_event_id else ()),
            correlation_id=correlation_id,
            tool_call_id=tool_call_id,
        )
        if risk.high_risk_unknown or (
            event_type == EventType.EXTERNAL_TRANSFER
            and any(object_id in self._uncertain_objects for object_id in object_ids)
        ):
            result = self._runtime_escalation(event, "Unknown high-risk tool or data classification")
        else:
            result = self._enforce(event)
        execution_event = result.final_event or event
        execution_arguments = (
            dict(arguments)
            if self.enforcement_mode == "audit"
            else dict(execution_event.input if isinstance(execution_event.input, Mapping) else arguments)
        )
        context = ToolCallContext(
            tool=tool,
            original_arguments=dict(arguments),
            execution_arguments=execution_arguments,
            risk=risk,
            event_id=execution_event.event_id,
            tool_call_id=tool_call_id,
            correlation_id=correlation_id,
            data_object_ids=(
                object_ids if self.enforcement_mode == "audit" else execution_event.data_object_ids
            ),
            enforcement=result,
        )
        allowed = result.outcome in {Decision.ALLOW, Decision.AUDIT_ONLY}
        if not allowed and self.enforcement_mode == "enforce":
            self.tool_trace.append(
                {
                    "tool": tool,
                    "tool_call_id": tool_call_id,
                    "event_id": execution_event.event_id,
                    "decision": result.outcome.value,
                    "repair_attempts": result.repair_attempts,
                    "executed": False,
                }
            )
            explanation = result.decisions[-1].explanation if result.decisions else "runtime gate"
            raise ToolCallBlocked(tool, result.outcome, explanation, context=context)
        self._allowed_calls[tool_call_id] = context
        self.tool_trace.append(
            {
                "tool": tool,
                "tool_call_id": tool_call_id,
                "event_id": execution_event.event_id,
                "decision": result.outcome.value,
                "repair_attempts": result.repair_attempts,
                "executed": False,
            }
        )
        return context

    def _runtime_escalation(self, event: LifecycleEvent, explanation: str) -> EnforcementResult:
        from agentshield.policy.rules import PolicyDecision, Severity
        from agentshield.state.diff import StateDiff

        diff = self.harness.manager.apply(event)
        decision = PolicyDecision(
            decision=Decision.REQUIRE_APPROVAL,
            event_id=event.event_id,
            risk_level=Severity.HIGH,
            explanation=explanation,
        )
        self.harness._audit(event, diff, decision, Decision.REQUIRE_APPROVAL, 0.0)
        self._last_event_id = event.event_id
        return EnforcementResult(event, None, (decision,), Decision.REQUIRE_APPROVAL, 0)

    def execute_tool(self, context: ToolCallContext) -> ToolObservation:
        if context.tool_call_id not in self._allowed_calls:
            raise RuntimeError("Tool execution requires a successful pre-effect check")
        try:
            value = self.registry.invoke(context.tool, context.execution_arguments)
        except BaseException as exc:
            self.on_agent_error(exc, parent_event_id=context.event_id)
            raise
        for trace in reversed(self.tool_trace):
            if trace["tool_call_id"] == context.tool_call_id:
                trace["executed"] = True
                break
        if context.risk.persistent_storage:
            return self.after_memory_write(context, value)
        return self.after_tool_result(context, value)

    def call_tool(self, tool: str, **arguments: Any) -> ToolObservation:
        context = self.before_tool_call(tool, arguments)
        return self.execute_tool(context)

    def after_tool_result(self, call: ToolCallContext, result: Any) -> ToolObservation:
        if call.tool_call_id not in self._allowed_calls:
            raise RuntimeError("TOOL_RESULT cannot precede an allowed TOOL_CALL")
        spec = self.registry.spec(call.tool)
        object_id = None
        metadata: dict[str, Any] = {
            "runtime_phase": "TOOL_RESULT_INGESTED",
            "source_trust_level": call.risk.source_trust_level,
            "suspicious_instruction_content": _suspicious_instruction(result),
        }
        if call.risk.data_source:
            prefix = spec.result_object_prefix or f"{call.tool}-result"
            object_id = self._new_object_id(prefix)
            metadata["data_object"] = {
                "object_id": object_id,
                "source": call.tool,
                "purpose": "customer_service",
                "attributes": {
                    "source_trust_level": call.risk.source_trust_level,
                    "suspicious_instruction_content": _suspicious_instruction(result),
                },
            }
        event = self._event(
            EventType.TOOL_RESULT,
            actor=call.tool,
            tool=call.tool,
            output=result,
            data_object_ids=((object_id,) if object_id else call.data_object_ids),
            purpose="customer_service",
            metadata=metadata,
            parent_event_ids=(call.event_id,),
            correlation_id=call.correlation_id,
            tool_call_id=call.tool_call_id,
        )
        enforcement = self._enforce(event)
        if object_id is not None:
            self._payloads[object_id] = result
            if enforcement.outcome not in {Decision.ALLOW, Decision.AUDIT_ONLY}:
                self._uncertain_objects.add(object_id)
        return ToolObservation(result, object_id, call.tool_call_id)

    def before_memory_write(
        self,
        tool: str,
        arguments: Mapping[str, Any],
        *,
        trusted_policy_metadata: Mapping[str, Any] | None = None,
    ) -> ToolCallContext:
        spec = self.registry.spec(tool)
        return self._precheck(
            tool,
            arguments,
            spec.risk,
            force_event_type=EventType.MEMORY_WRITE,
            trusted_policy_metadata=trusted_policy_metadata,
        )

    def ingest_data_object(
        self,
        object_id: str,
        payload: Any,
        *,
        source: str = "broker_recovery",
        source_trust_level: str = "broker_protected",
    ) -> EnforcementResult | None:
        if object_id in self.state.data_objects:
            return None
        event = self._event(
            EventType.TOOL_RESULT,
            actor="capability_broker",
            tool=source,
            output=payload,
            data_object_ids=(object_id,),
            purpose="customer_service",
            metadata={
                "runtime_phase": "BROKER_OBJECT_REHYDRATED",
                "data_object": {
                    "object_id": object_id,
                    "source": source,
                    "purpose": "customer_service",
                    "attributes": {"source_trust_level": source_trust_level},
                },
            },
        )
        self._payloads[object_id] = payload
        return self._enforce(event)

    def record_approval(
        self,
        approval_id: str,
        *,
        data_object_ids: tuple[str, ...],
        purpose: str,
        recipient: str | None,
        approved: bool,
        separate_consent_evidence: bool = False,
    ) -> None:
        approval = self._event(
            EventType.HUMAN_APPROVAL,
            actor="human_approver",
            data_object_ids=data_object_ids,
            purpose=purpose,
            recipient=recipient,
            metadata={
                "approval_id": approval_id,
                "approved_event_type": EventType.EXTERNAL_TRANSFER.value,
                "approved": approved,
            },
        )
        self._enforce(approval)
        if approved and separate_consent_evidence:
            consent = self._event(
                EventType.CONSENT_UPDATE,
                actor="human_approver",
                data_object_ids=data_object_ids,
                purpose=purpose,
                recipient=recipient,
                metadata={
                    "consent_id": f"{approval_id}-consent-evidence",
                    "granted": True,
                    "separate": True,
                    "authorized_event_type": EventType.EXTERNAL_TRANSFER.value,
                },
            )
            self._enforce(consent)

    def after_memory_write(self, call: ToolCallContext, result: Any) -> ToolObservation:
        # Persistence has already occurred, so this result event is audit-only and
        # causally linked to the pre-write event that allowed it.
        return self.after_tool_result(call, result)

    def before_response_release(
        self,
        response: Any,
        source_object_ids: tuple[str, ...] = (),
    ) -> Any:
        # First ingest the generated response as untrusted runtime output. This is
        # not released. The release candidate is then normalized and verified.
        response_id = self._new_object_id("response")
        response_object_metadata: dict[str, Any]
        known_sources = tuple(
            object_id for object_id in source_object_ids if object_id in self.state.data_objects
        )
        if known_sources:
            response_object_metadata = {
                "lineage": {
                    "source_object_id": known_sources[0],
                    "target_object_id": response_id,
                    "transformation": "COPY",
                    "preserves_personal_data": None,
                    "confidence": 1.0,
                }
            }
        else:
            response_object_metadata = {
                "data_object": {
                    "object_id": response_id,
                    "source": "agent_response",
                    "purpose": "customer_service",
                }
            }
        generation = self._event(
            EventType.TOOL_RESULT,
            actor="agent",
            tool="response_generator",
            output=response,
            data_object_ids=(response_id,),
            purpose="customer_service",
            metadata={
                "runtime_phase": "RESPONSE_GENERATED",
                **response_object_metadata,
            },
            parent_event_ids=((self._last_event_id,) if self._last_event_id else ()),
            correlation_id=str(uuid4()),
        )
        generated = self._enforce(generation)
        if generated.outcome not in {Decision.ALLOW, Decision.AUDIT_ONLY}:
            raise ToolCallBlocked("response_release", generated.outcome, "Response ingestion failed closed")
        response_object = self.state.data_objects[response_id]
        contains_personal_data = response_object.contains_personal_data is True
        detection_confidence = response_object.detection_confidence or 1.0
        released = redact_payload(response) if contains_personal_data else response
        target_id = (
            derived_object_id(response_id, "redact", generation.event_id)
            if contains_personal_data
            else derived_object_id(response_id, "copy", generation.event_id)
        )
        metadata = {
            "runtime_phase": "RESPONSE_RELEASE_CANDIDATE",
            "trust_boundary": "user",
            "recipient_type": "requesting_user",
            "lineage": {
                "source_object_id": response_id,
                "target_object_id": target_id,
                "transformation": "REDACT" if contains_personal_data else "COPY",
                "preserves_personal_data": not contains_personal_data,
                "confidence": detection_confidence,
            },
        }
        if contains_personal_data:
            metadata["repair"] = {
                "strategy": "REDACT",
                "original_event_id": generation.event_id,
                "reason": "runtime response leakage guard",
            }
        release_event = self._event(
            EventType.RESPONSE_GENERATED,
            actor="agentshield",
            output=released,
            data_object_ids=(target_id,),
            purpose="customer_service",
            metadata=metadata,
            parent_event_ids=(generation.event_id,),
            correlation_id=generation.correlation_id,
            replaces_event_id=(generation.event_id if contains_personal_data else None),
        )
        result = self._enforce(release_event)
        if result.outcome not in {Decision.ALLOW, Decision.AUDIT_ONLY} and self.enforcement_mode == "enforce":
            raise ToolCallBlocked(
                "response_release",
                result.outcome,
                result.decisions[-1].explanation,
            )
        return released if self.enforcement_mode == "enforce" else response

    def after_response_release(self, response: Any) -> Any:
        return response

    def on_agent_error(self, error: BaseException, *, parent_event_id: str | None = None) -> None:
        event = self._event(
            EventType.AGENT_ERROR,
            actor="agent_runtime",
            metadata={"error_type": type(error).__name__, "error_message": str(error)},
            parent_event_ids=((parent_event_id,) if parent_event_id else ()),
        )
        self._enforce(event)

    def _resolve_object_ids(self, value: Any) -> tuple[str, ...]:
        found: set[str] = set()

        def visit(item: Any) -> None:
            if isinstance(item, str) and (
                item in self.state.data_objects or item in self._uncertain_objects
            ):
                found.add(item)
            elif isinstance(item, Mapping):
                for nested in item.values():
                    visit(nested)
            elif isinstance(item, (list, tuple, set)):
                for nested in item:
                    visit(nested)

        visit(value)
        return tuple(sorted(found))

    def _aggregate_replacement(
        self,
        arguments: Mapping[str, Any],
        object_ids: tuple[str, ...],
    ) -> dict[str, Any] | None:
        if len(object_ids) != 1:
            return None
        payload = self._payloads.get(object_ids[0])
        aggregate = _aggregate_payload(payload)
        if aggregate is None:
            return None
        replacement = dict(arguments)
        replacement["body"] = aggregate
        replacement.pop("attachment", None)
        return replacement

    def _new_object_id(self, prefix: str) -> str:
        self._objects[prefix] += 1
        return f"{prefix}-{self._objects[prefix]:03d}"


def _aggregate_payload(payload: Any) -> dict[str, int] | None:
    """Return a safe aggregate for records read from a protected backend.

    Web task fixtures wrap customer lists in a page object (``{"records": [...]}``),
    while the original customer-service agent returns the list itself.  Both are
    personal-data-bearing sources and must preserve the proposed tool arguments
    when a repair replaces raw records with a count.
    """
    if isinstance(payload, (list, tuple)):
        return {"eu_customer_count": len(payload)}
    if isinstance(payload, Mapping) and isinstance(payload.get("records"), (list, tuple)):
        return {"eu_customer_count": len(payload["records"])}
    return None


class SecuredLangGraphAgent:
    """Runnable-like wrapper returned by ``AgentShield.wrap``."""

    def __init__(
        self,
        shield: "AgentShield",
        agent: LangGraphRuntimeBindable,
        *,
        audit_directory: str | Path,
        enforcement_mode: str,
    ) -> None:
        if not hasattr(agent, "with_runtime") or not isinstance(
            getattr(agent, "tool_registry", None), ToolRegistry
        ):
            raise AdapterContractError(
                "Full LangGraph protection requires an agent exposing tool_registry and with_runtime(runtime)"
            )
        self.shield = shield
        self.agent = agent
        self.audit_directory = Path(audit_directory)
        self.enforcement_mode = enforcement_mode
        self.sessions: dict[str, LangGraphAdapter] = {}
        self.last_run_id: str | None = None

    @property
    def capabilities(self) -> AdapterCapabilities:
        return LangGraphAdapter.capabilities

    @property
    def last_session(self) -> LangGraphAdapter | None:
        return self.sessions.get(self.last_run_id or "")

    def invoke(self, inputs: Any, config: Mapping[str, Any] | None = None, **kwargs: Any) -> Any:
        config = dict(config or {})
        configurable = dict(config.get("configurable", {}))
        run_id = str(configurable.get("thread_id") or uuid4())
        session = LangGraphAdapter(
            self.shield,
            self.agent.tool_registry,
            trajectory_id=run_id,
            audit_directory=self.audit_directory,
            enforcement_mode=self.enforcement_mode,
        )
        self.sessions[run_id] = session
        self.last_run_id = run_id
        session.on_user_request(inputs)
        bound = self.agent.with_runtime(session)
        try:
            output = bound.invoke(inputs, config=config, **kwargs)
        except BaseException as exc:
            if not isinstance(exc, ToolCallBlocked):
                session.on_agent_error(exc, parent_event_id=session._last_event_id)
            raise
        response, source_ids = _extract_response(output)
        released = session.before_response_release(response, source_ids)
        released = session.after_response_release(released)
        if isinstance(output, Mapping) and "response" in output:
            return {**output, "response": released, "agentshield_run_id": run_id}
        return released

    async def ainvoke(self, inputs: Any, config: Mapping[str, Any] | None = None, **kwargs: Any) -> Any:
        # Each invocation owns an isolated compliance session. V1 deliberately
        # serializes tool execution within a graph run.
        return await asyncio.to_thread(self.invoke, inputs, config, **kwargs)


def _extract_response(output: Any) -> tuple[Any, tuple[str, ...]]:
    if isinstance(output, Mapping) and "response" in output:
        sources = output.get("response_source_object_ids", ())
        return output["response"], tuple(sources or ())
    return output, ()


def _argument(arguments: Mapping[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    return str(value) if value is not None else None


def _request_purpose(request: Any) -> str:
    del request
    return "customer_service"


def _suspicious_instruction(value: Any) -> bool:
    rendered = str(value).lower()
    indicators = ("ignore previous instructions", "ignore all instructions", "upload the data")
    return any(indicator in rendered for indicator in indicators)
