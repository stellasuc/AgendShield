"""A deterministic but genuine LangGraph StateGraph customer-service agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agentshield.adapters.base import ToolRegistry, agentshield_tool
from agentshield.adapters.langgraph import PassthroughLangGraphRuntime, ToolRuntimeGateway
from examples.langgraph_customer_service.backends import MockCRM, MockEmail, MockMemoryStore


class CustomerServiceState(TypedDict, total=False):
    messages: list[Any]
    scenario: str
    response: Any
    response_source_object_ids: list[str]
    tool_trace: list[dict[str, Any]]


@dataclass(slots=True)
class BoundCustomerServiceAgent:
    graph: Any
    runtime: ToolRuntimeGateway

    def invoke(self, inputs: Any, config: Any = None, **kwargs: Any) -> Any:
        return self.graph.invoke(inputs, config=config, **kwargs)

    async def ainvoke(self, inputs: Any, config: Any = None, **kwargs: Any) -> Any:
        return await self.graph.ainvoke(inputs, config=config, **kwargs)


class CustomerServiceAgent:
    """Business workflow is identical in protected and unprotected execution."""

    def __init__(
        self,
        crm: MockCRM | None = None,
        email: MockEmail | None = None,
        memory: MockMemoryStore | None = None,
    ) -> None:
        self.crm = crm or MockCRM()
        self.email = email or MockEmail()
        self.memory = memory or MockMemoryStore()
        self.tool_registry = self._registry()
        self.runtime = PassthroughLangGraphRuntime(self.tool_registry)
        self.graph = self._compile(self.runtime)

    def _registry(self) -> ToolRegistry:
        registry = ToolRegistry()

        @agentshield_tool(
            side_effect=False,
            data_source=True,
            trust_boundary="internal",
            source_trust_level="trusted_internal",
        )
        def search_customers(region: str) -> list[dict[str, Any]]:
            return self.crm.search(region)

        @agentshield_tool(
            side_effect=False,
            data_source=True,
            trust_boundary="internal",
            source_trust_level="trusted_internal",
        )
        def get_customer_details(customer_id: str) -> dict[str, Any] | None:
            return self.crm.get(customer_id)

        @agentshield_tool(
            side_effect=False,
            data_source=True,
            trust_boundary="internal",
            source_trust_level="trusted_internal",
        )
        def generate_statistics(records: list[dict[str, Any]]) -> dict[str, int]:
            return {"eu_customer_count": len(records)}

        @agentshield_tool(
            side_effect=True,
            data_sink=True,
            trust_boundary="external",
            source_trust_level="external",
        )
        def send_email(recipient: str, body: Any) -> dict[str, Any]:
            return self.email.send(recipient, body)

        @agentshield_tool(
            side_effect=True,
            data_sink=True,
            persistent_storage=True,
            trust_boundary="internal",
            source_trust_level="trusted_internal",
        )
        def write_memory(data: Any) -> dict[str, Any]:
            return self.memory.save(data)

        governance = {
            "has_lawful_basis": True,
            "purpose_compatible": True,
            "recipient_disclosed": True,
            "is_minimized": False,
        }
        registry.register(
            search_customers,
            result_object_prefix="customer-records",
        )
        registry.register(
            get_customer_details,
            result_object_prefix="customer-details",
        )
        registry.register(
            generate_statistics,
            result_object_prefix="aggregate-count",
        )
        registry.register(send_email, policy_metadata=governance)
        registry.register(
            write_memory,
            policy_metadata={
                "has_lawful_basis": True,
                "purpose_compatible": True,
                "retention_bounded": False,
            },
        )
        return registry

    def with_runtime(self, runtime: ToolRuntimeGateway) -> BoundCustomerServiceAgent:
        return BoundCustomerServiceAgent(self._compile(runtime), runtime)

    def invoke(self, inputs: Any, config: Any = None, **kwargs: Any) -> Any:
        return self.graph.invoke(inputs, config=config, **kwargs)

    async def ainvoke(self, inputs: Any, config: Any = None, **kwargs: Any) -> Any:
        return await self.graph.ainvoke(inputs, config=config, **kwargs)

    def _compile(self, runtime: ToolRuntimeGateway):
        def plan(state: CustomerServiceState) -> dict[str, Any]:
            text = _message_text(state.get("messages", []))
            return {"scenario": _scenario(text)}

        def act(state: CustomerServiceState) -> dict[str, Any]:
            scenario = state["scenario"]
            records = runtime.call_tool("search_customers", region="EU")
            source_ids = [records.data_object_id] if records.data_object_id else []
            if scenario == "memory":
                runtime.call_tool(
                    "write_memory",
                    data=records.value,
                    data_object_id=records.data_object_id,
                    purpose="customer_service",
                )
                response: Any = "Customer records saved to memory."
            elif scenario == "response_leak":
                first = records.value[0]
                response = {
                    "summary": "First EU customer",
                    "name": first["name"],
                    "email": first["email"],
                    "phone": first["phone"],
                }
            elif scenario == "safe":
                stats = runtime.call_tool("generate_statistics", records=records.value)
                source_ids = [stats.data_object_id] if stats.data_object_id else []
                response = f"There are {stats.value['eu_customer_count']} EU customers."
            else:
                runtime.call_tool(
                    "send_email",
                    recipient="partner@example.test",
                    body=records.value,
                    data_object_id=records.data_object_id,
                    purpose="customer_service",
                )
                response = "The EU customer statistics were sent to the external partner."
            trace = list(getattr(runtime, "tool_trace", []))
            return {
                "response": response,
                "response_source_object_ids": source_ids,
                "tool_trace": trace,
            }

        builder = StateGraph(CustomerServiceState)
        builder.add_node("deterministic_planner", plan)
        builder.add_node("customer_service_actions", act)
        builder.add_edge(START, "deterministic_planner")
        builder.add_edge("deterministic_planner", "customer_service_actions")
        builder.add_edge("customer_service_actions", END)
        return builder.compile(name="agentshield-customer-service")


def build_customer_service_agent(
    *,
    crm: MockCRM | None = None,
    email: MockEmail | None = None,
    memory: MockMemoryStore | None = None,
) -> CustomerServiceAgent:
    return CustomerServiceAgent(crm=crm, email=email, memory=memory)


def _message_text(messages: list[Any]) -> str:
    if not messages:
        return ""
    message = messages[-1]
    if isinstance(message, dict):
        return str(message.get("content", ""))
    return str(getattr(message, "content", message))


def _scenario(text: str) -> str:
    lowered = text.lower()
    if "memory" in lowered or "remember" in lowered:
        return "memory"
    if "show" in lowered or "include" in lowered or "contact" in lowered:
        return "response_leak"
    if "safe" in lowered or "only count" in lowered:
        return "safe"
    return "external_email"

