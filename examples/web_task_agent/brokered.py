"""A brokered WebArena-style task agent for ShieldAgent runtime demonstrations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from agentshield.adapters.langgraph import ToolObservation
from agentshield.capabilities.client import BrokerClient
from agentshield.capabilities.models import CapabilityRequest, CapabilityResponse


WEB_ENVIRONMENTS = ("shopping", "cms", "reddit", "gitlab", "maps", "suitecrm")


class BrokeredCapabilityError(RuntimeError):
    def __init__(self, response: CapabilityResponse) -> None:
        super().__init__(f"Capability {response.status}: {response.decision} ({response.transaction_id})")
        self.response = response


class BrokeredWebRuntime:
    __slots__ = ("client", "trajectory_id", "tool_trace")

    def __init__(self, client: BrokerClient, trajectory_id: str) -> None:
        self.client = client
        self.trajectory_id = trajectory_id
        self.tool_trace: list[dict[str, Any]] = []

    def call_tool(self, tool: str, **arguments: Any) -> ToolObservation:
        capability = {
            "read_web_page": "web.page.read",
            "submit_web_action": "web.action.submit",
        }.get(tool)
        if capability is None:
            raise KeyError(f"No brokered capability mapping for tool: {tool}")
        object_id = arguments.pop("data_object_id", None)
        response = self.client.request(
            CapabilityRequest(
                request_id=str(uuid4()),
                trajectory_id=self.trajectory_id,
                capability_id=capability,
                arguments=arguments,
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


class WebTaskState(TypedDict, total=False):
    messages: list[Any]
    environment: str
    response: str
    tool_trace: list[dict[str, Any]]


@dataclass(slots=True)
class BrokeredWebTaskAgent:
    client: BrokerClient
    trajectory_id: str
    runtime: BrokeredWebRuntime = field(init=False)
    graph: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.runtime = BrokeredWebRuntime(self.client, self.trajectory_id)
        self.graph = _compile(self.runtime)

    def invoke(self, inputs: Any, config: Any = None, **kwargs: Any) -> dict[str, Any]:
        output = self.graph.invoke(inputs, config=config, **kwargs)
        release = self.client.request(
            CapabilityRequest(
                trajectory_id=self.trajectory_id,
                capability_id="response.release",
                arguments={"response": output["response"], "purpose": "web_task"},
            )
        )
        if release.status != "SUCCEEDED":
            raise BrokeredCapabilityError(release)
        return {
            **output,
            "response": release.value,
            "response_transaction_id": release.transaction_id,
        }


def build_brokered_web_task_agent(
    client: BrokerClient,
    *,
    trajectory_id: str | None = None,
) -> BrokeredWebTaskAgent:
    return BrokeredWebTaskAgent(client, trajectory_id or f"web-task-{uuid4().hex[:10]}")


def infer_environment(prompt: str) -> str:
    lowered = prompt.lower()
    keywords = {
        "shopping": ("shop", "buy", "cart", "order", "购物", "商品", "订单"),
        "cms": ("cms", "content", "publish", "页面", "发布", "内容管理"),
        "reddit": ("reddit", "forum", "community", "社区", "帖子"),
        "gitlab": ("gitlab", "merge request", "repository", "代码", "合并请求", "仓库"),
        "maps": ("map", "route", "location", "地图", "路线", "地点"),
        "suitecrm": ("crm", "customer", "客户", "联系人", "工单"),
    }
    for environment, terms in keywords.items():
        if any(term in lowered for term in terms):
            return environment
    return "suitecrm"


def _compile(runtime: BrokeredWebRuntime):
    def plan(state: WebTaskState) -> dict[str, Any]:
        requested = str(state.get("environment") or "")
        environment = requested if requested in WEB_ENVIRONMENTS else infer_environment(_message_text(state.get("messages", [])))
        return {"environment": environment}

    def act(state: WebTaskState) -> dict[str, Any]:
        environment = state["environment"]
        page = runtime.call_tool("read_web_page", environment=environment)
        runtime.call_tool(
            "submit_web_action",
            environment=environment,
            action="complete_user_requested_web_task",
            recipient="external-web.test",
            body=page.value,
            data_object_id=page.data_object_id,
            purpose="web_task",
        )
        return {
            "response": f"已在 {environment} Web 环境中完成受控任务动作。",
            "tool_trace": list(runtime.tool_trace),
        }

    builder = StateGraph(WebTaskState)
    builder.add_node("web_task_planner", plan)
    builder.add_node("web_task_actions", act)
    builder.add_edge(START, "web_task_planner")
    builder.add_edge("web_task_planner", "web_task_actions")
    builder.add_edge("web_task_actions", END)
    return builder.compile(name="agentshield-brokered-web-task-agent")


def _message_text(messages: list[Any]) -> str:
    if not messages:
        return ""
    message = messages[-1]
    if isinstance(message, dict):
        return str(message.get("content", ""))
    return str(getattr(message, "content", message))
