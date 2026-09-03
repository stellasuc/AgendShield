"""Brokered LangGraph agent whose normal API contains only a BrokerClient."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from agentshield.adapters.langgraph import ToolObservation
from agentshield.capabilities.client import BrokerClient
from agentshield.capabilities.models import CapabilityRequest, CapabilityResponse


class BrokeredCapabilityError(RuntimeError):
    def __init__(self, response: CapabilityResponse) -> None:
        super().__init__(
            f"Capability {response.status}: {response.decision} ({response.transaction_id})"
        )
        self.response = response


class BrokeredRuntime:
    __slots__ = ("client", "trajectory_id", "tool_trace")

    def __init__(self, client: BrokerClient, trajectory_id: str) -> None:
        self.client = client
        self.trajectory_id = trajectory_id
        self.tool_trace: list[dict[str, Any]] = []

    def call_tool(self, tool: str, **arguments: Any) -> ToolObservation:
        if tool == "generate_statistics":
            value = {"eu_customer_count": len(arguments["records"])}
            self.tool_trace.append({"tool": tool, "disposition": "LOCAL_READ_ONLY"})
            return ToolObservation(value)
        capability = {
            "search_customers": "customer.read",
            "get_customer_details": "customer.read",
            "send_email": "email.send",
            "write_memory": "memory.write",
        }.get(tool)
        if capability is None:
            raise KeyError(f"No brokered capability mapping for tool: {tool}")
        object_id = arguments.get("data_object_id")
        request_arguments = dict(arguments)
        request_arguments.pop("data_object_id", None)
        if capability == "customer.read":
            request_arguments = {"dataset": "eu"}
        response = self.client.request(
            CapabilityRequest(
                request_id=str(uuid4()),
                trajectory_id=self.trajectory_id,
                capability_id=capability,
                arguments=request_arguments,
                referenced_data_objects=((str(object_id),) if object_id else ()),
            )
        )
        self.tool_trace.append(
            {
                "tool": tool,
                "capability": capability,
                "transaction_id": response.transaction_id,
                "status": response.status,
                "decision": response.decision,
                "disposition": response.disposition,
            }
        )
        if response.status != "SUCCEEDED":
            raise BrokeredCapabilityError(response)
        return ToolObservation(response.value, response.data_object_id, response.transaction_id)


class BrokeredCustomerState(TypedDict, total=False):
    messages: list[Any]
    scenario: str
    response: Any
    response_source_object_ids: list[str]
    tool_trace: list[dict[str, Any]]


@dataclass(slots=True)
class BrokeredCustomerServiceAgent:
    client: BrokerClient
    trajectory_id: str
    runtime: BrokeredRuntime = field(init=False)
    graph: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.runtime = BrokeredRuntime(self.client, self.trajectory_id)
        self.graph = _compile(self.runtime)

    def invoke(self, inputs: Any, config: Any = None, **kwargs: Any) -> Any:
        output = self.graph.invoke(inputs, config=config, **kwargs)
        release = self.client.request(
            CapabilityRequest(
                trajectory_id=self.trajectory_id,
                capability_id="response.release",
                arguments={"response": output["response"], "purpose": "customer_service"},
                referenced_data_objects=tuple(output.get("response_source_object_ids") or ()),
            )
        )
        if release.status != "SUCCEEDED":
            raise BrokeredCapabilityError(release)
        return {
            **output,
            "response": release.value,
            "response_transaction_id": release.transaction_id,
        }


def build_brokered_customer_service_agent(
    client: BrokerClient,
    *,
    trajectory_id: str | None = None,
) -> BrokeredCustomerServiceAgent:
    return BrokeredCustomerServiceAgent(client, trajectory_id or f"broker-run-{uuid4().hex[:10]}")


def _compile(runtime: BrokeredRuntime):
    def plan(state: BrokeredCustomerState) -> dict[str, Any]:
        return {"scenario": _scenario(_message_text(state.get("messages", [])))}

    def act(state: BrokeredCustomerState) -> dict[str, Any]:
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
            source_ids = []
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
        return {
            "response": response,
            "response_source_object_ids": source_ids,
            "tool_trace": list(runtime.tool_trace),
        }

    builder = StateGraph(BrokeredCustomerState)
    builder.add_node("deterministic_planner", plan)
    builder.add_node("brokered_customer_service_actions", act)
    builder.add_edge(START, "deterministic_planner")
    builder.add_edge("deterministic_planner", "brokered_customer_service_actions")
    builder.add_edge("brokered_customer_service_actions", END)
    return builder.compile(name="agentshield-brokered-customer-service")


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
