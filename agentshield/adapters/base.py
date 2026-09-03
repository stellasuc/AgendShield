"""Framework-neutral adapter contract used by runtime integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import inspect
from typing import Any, Callable, Mapping


@dataclass(frozen=True, slots=True)
class AdapterCapabilities:
    user_request: bool = True
    plan: bool = False
    tool_pre_check: bool = True
    tool_result_ingestion: bool = True
    memory_pre_write: bool = True
    response_pre_release: bool = True
    async_invoke: bool = True
    parallel_tool_calls: bool = False


@dataclass(frozen=True, slots=True)
class ToolRiskMetadata:
    """Explicit risk facts. ``None`` means unknown, never implicitly safe."""

    side_effect: bool | None = None
    data_source: bool = False
    data_sink: bool = False
    persistent_storage: bool = False
    trust_boundary: str = "unknown"
    source_trust_level: str = "unknown"

    @property
    def high_risk_unknown(self) -> bool:
        return self.side_effect is None and (
            self.data_sink
            or self.persistent_storage
            or self.trust_boundary in {"external", "unknown"}
        )


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    function: Callable[..., Any]
    risk: ToolRiskMetadata
    policy_metadata: Mapping[str, Any] = field(default_factory=dict)
    result_object_prefix: str | None = None


class ToolRegistry:
    """Explicit registry; tool names are never used to infer effect risk."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(
        self,
        function: Callable[..., Any],
        *,
        name: str | None = None,
        risk: ToolRiskMetadata | None = None,
        policy_metadata: Mapping[str, Any] | None = None,
        result_object_prefix: str | None = None,
    ) -> Callable[..., Any]:
        tool_name = name or function.__name__
        attached = getattr(function, "__agentshield_tool_risk__", None)
        resolved_risk = risk or attached or ToolRiskMetadata()
        if tool_name in self._tools:
            raise ValueError(f"Duplicate tool registration: {tool_name}")
        self._tools[tool_name] = ToolSpec(
            name=tool_name,
            function=function,
            risk=resolved_risk,
            policy_metadata=dict(policy_metadata or {}),
            result_object_prefix=result_object_prefix,
        )
        return function

    def spec(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unregistered tool: {name}") from exc

    def invoke(self, name: str, arguments: Mapping[str, Any]) -> Any:
        spec = self.spec(name)
        signature = inspect.signature(spec.function)
        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        call_arguments = (
            dict(arguments)
            if accepts_kwargs
            else {key: value for key, value in arguments.items() if key in signature.parameters}
        )
        return spec.function(**call_arguments)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)


def agentshield_tool(
    *,
    side_effect: bool | None,
    data_source: bool = False,
    data_sink: bool = False,
    persistent_storage: bool = False,
    trust_boundary: str = "unknown",
    source_trust_level: str = "unknown",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Attach immutable, inspectable risk metadata to a tool callable."""

    risk = ToolRiskMetadata(
        side_effect=side_effect,
        data_source=data_source,
        data_sink=data_sink,
        persistent_storage=persistent_storage,
        trust_boundary=trust_boundary,
        source_trust_level=source_trust_level,
    )

    def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
        setattr(function, "__agentshield_tool_risk__", risk)
        return function

    return decorate


class AgentRuntimeAdapter(ABC):
    """Lifecycle boundary implemented by concrete agent framework adapters."""

    capabilities = AdapterCapabilities()

    @abstractmethod
    def on_user_request(self, request: Any) -> Any: ...

    def on_plan(self, plan: Any) -> Any:
        return plan

    @abstractmethod
    def before_tool_call(self, tool: str, arguments: Mapping[str, Any]) -> Any: ...

    @abstractmethod
    def after_tool_result(self, call: Any, result: Any) -> Any: ...

    @abstractmethod
    def before_memory_write(self, tool: str, arguments: Mapping[str, Any]) -> Any: ...

    @abstractmethod
    def after_memory_write(self, call: Any, result: Any) -> Any: ...

    @abstractmethod
    def before_response_release(self, response: Any, source_object_ids: tuple[str, ...] = ()) -> Any: ...

    def after_response_release(self, response: Any) -> Any:
        return response

    @abstractmethod
    def on_agent_error(self, error: BaseException, *, parent_event_id: str | None = None) -> None: ...
