"""A brokered WebArena-style task agent for ShieldAgent runtime demonstrations."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Callable, Mapping, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from agentshield.adapters.langgraph import ToolObservation
from agentshield.capabilities.client import BrokerClient
from agentshield.capabilities.models import CapabilityRequest, CapabilityResponse
from examples.web_task_agent.shopping import choose_product


WEB_ENVIRONMENTS = ("shopping", "cms", "reddit", "gitlab", "maps", "suitecrm")
ProgressCallback = Callable[[str, Mapping[str, Any]], None]


class BrokeredCapabilityError(RuntimeError):
    def __init__(self, response: CapabilityResponse) -> None:
        super().__init__(f"Capability {response.status}: {response.decision} ({response.transaction_id})")
        self.response = response


class BrokeredWebRuntime:
    __slots__ = ("client", "trajectory_id", "tool_trace", "progress_callback")

    def __init__(
        self,
        client: BrokerClient,
        trajectory_id: str,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.client = client
        self.trajectory_id = trajectory_id
        self.tool_trace: list[dict[str, Any]] = []
        self.progress_callback = progress_callback

    def notify(self, event: str, payload: Mapping[str, Any]) -> None:
        if self.progress_callback is not None:
            self.progress_callback(event, payload)

    def call_tool(self, tool: str, **arguments: Any) -> ToolObservation:
        capability = {
            "read_web_page": "web.page.read",
            "submit_web_action": "web.action.submit",
        }.get(tool)
        if capability is None:
            raise KeyError(f"No brokered capability mapping for tool: {tool}")
        object_id = arguments.pop("data_object_id", None)
        safe_arguments = _safe_trace_arguments(arguments)
        self.notify(
            "action_requested",
            {"tool": tool, "capability": capability, "arguments": safe_arguments},
        )
        response = self.client.request(
            CapabilityRequest(
                request_id=str(uuid4()),
                trajectory_id=self.trajectory_id,
                capability_id=capability,
                arguments=arguments,
                referenced_data_objects=((str(object_id),) if object_id else ()),
            )
        )
        trace = {
            "tool": tool,
            "capability": capability,
            "transaction_id": response.transaction_id,
            "status": response.status,
            "decision": response.decision,
            "disposition": response.disposition,
            "arguments": safe_arguments,
        }
        self.tool_trace.append(trace)
        self.notify("shield_decided", trace)
        if response.status != "SUCCEEDED":
            raise BrokeredCapabilityError(response)
        return ToolObservation(response.value, response.data_object_id, response.transaction_id)


class WebTaskState(TypedDict, total=False):
    messages: list[Any]
    environment: str
    response: str
    tool_trace: list[dict[str, Any]]
    task_action: str
    query: str
    max_price: float | None
    quantity: int
    environment_state: dict[str, Any]
    scope_guard: str | None


@dataclass(slots=True)
class BrokeredWebTaskAgent:
    client: BrokerClient
    trajectory_id: str
    progress_callback: ProgressCallback | None = None
    runtime: BrokeredWebRuntime = field(init=False)
    graph: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.runtime = BrokeredWebRuntime(
            self.client,
            self.trajectory_id,
            self.progress_callback,
        )
        self.graph = _compile(self.runtime)

    def invoke(self, inputs: Any, config: Any = None, **kwargs: Any) -> dict[str, Any]:
        output = self.graph.invoke(inputs, config=config, **kwargs)
        release_arguments = {"purpose": "web_task"}
        self.runtime.notify(
            "action_requested",
            {
                "tool": "release_response",
                "capability": "response.release",
                "arguments": release_arguments,
            },
        )
        release = self.client.request(
            CapabilityRequest(
                trajectory_id=self.trajectory_id,
                capability_id="response.release",
                arguments={"response": output["response"], "purpose": "web_task"},
            )
        )
        release_trace = {
            "tool": "release_response",
            "capability": "response.release",
            "transaction_id": release.transaction_id,
            "status": release.status,
            "decision": release.decision,
            "disposition": release.disposition,
            "arguments": release_arguments,
        }
        self.runtime.tool_trace.append(release_trace)
        self.runtime.notify("shield_decided", release_trace)
        if release.status != "SUCCEEDED":
            raise BrokeredCapabilityError(release)
        return {
            **output,
            "response": release.value,
            "response_transaction_id": release.transaction_id,
            "tool_trace": list(self.runtime.tool_trace),
        }


def build_brokered_web_task_agent(
    client: BrokerClient,
    *,
    trajectory_id: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> BrokeredWebTaskAgent:
    return BrokeredWebTaskAgent(
        client,
        trajectory_id or f"web-task-{uuid4().hex[:10]}",
        progress_callback,
    )


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
        prompt = _message_text(state.get("messages", []))
        environment = requested if requested in WEB_ENVIRONMENTS else infer_environment(prompt)
        task_action = str(state.get("task_action") or "inspect")
        if environment == "shopping" and task_action == "inspect":
            task_action = infer_shopping_action(prompt)
        query = str(state.get("query") or "").strip() or infer_shopping_query(prompt)
        max_price = state.get("max_price")
        if max_price is None:
            max_price = infer_max_price(prompt)
        quantity = _quantity(state.get("quantity", 1))
        scope_guard = None
        if task_action == "place_order" and not has_explicit_order_confirmation(prompt):
            task_action = "add_to_cart"
            scope_guard = "模型提出下单，但用户没有明确确认；已收敛为加入购物车。"
        return {
            "environment": environment,
            "task_action": task_action,
            "query": query,
            "max_price": max_price,
            "quantity": quantity,
            "scope_guard": scope_guard,
        }

    def act(state: WebTaskState) -> dict[str, Any]:
        environment = state["environment"]
        page = runtime.call_tool(
            "read_web_page",
            environment=environment,
            page="search" if environment == "shopping" else "home",
            query=state.get("query", ""),
            max_price=state.get("max_price"),
        )
        if environment == "shopping":
            return _execute_shopping_action(runtime, state, page)
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
            "environment_state": page.value,
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


def infer_shopping_action(prompt: str) -> str:
    lowered = prompt.lower()
    if any(term in lowered for term in ("确认下单", "提交订单", "立即下单", "place the order", "submit order")):
        return "place_order"
    if any(term in lowered for term in ("加入购物车", "放入购物车", "购买", "buy", "add to cart", "挑选", "选择")):
        return "add_to_cart"
    if any(term in lowered for term in ("搜索", "查找", "寻找", "search", "find")):
        return "search"
    return "inspect"


def infer_shopping_query(prompt: str) -> str:
    lowered = prompt.lower()
    candidates = (
        ("降噪耳机", ("降噪", "noise cancelling")),
        ("人体工学机械键盘", ("人体工学键盘", "机械键盘", "ergonomic keyboard")),
        ("人体工学鼠标", ("人体工学鼠标", "ergonomic mouse")),
        ("2K 显示器", ("2k", "显示器", "monitor")),
    )
    for query, terms in candidates:
        if any(term in lowered for term in terms):
            return query
    return ""


def infer_max_price(prompt: str) -> float | None:
    match = re.search(r"(?:预算|不超过|最高|上限|under|below)\s*(?:为|是|¥|￥|rmb|cny)?\s*(\d+(?:\.\d+)?)", prompt, re.IGNORECASE)
    return float(match.group(1)) if match else None


def has_explicit_order_confirmation(prompt: str) -> bool:
    lowered = prompt.lower()
    return any(
        term in lowered
        for term in ("确认下单", "提交订单", "立即下单", "place the order", "submit order")
    )


def _execute_shopping_action(
    runtime: BrokeredWebRuntime,
    state: WebTaskState,
    page: ToolObservation,
) -> dict[str, Any]:
    items = page.value.get("items", []) if isinstance(page.value, dict) else []
    selected = choose_product(items)
    action = state.get("task_action", "inspect")
    environment_state: dict[str, Any] = {
        "storefront": page.value,
        "selected_product": selected,
        "cart": {"items": [], "item_count": 0, "total": 0.0, "currency": "CNY"},
        "order": None,
    }
    if selected is None:
        return {
            "response": "本地商店没有找到满足搜索词和预算的商品，未执行购物车或订单操作。",
            "tool_trace": list(runtime.tool_trace),
            "environment_state": environment_state,
            "scope_guard": state.get("scope_guard"),
        }
    detail = runtime.call_tool(
        "read_web_page",
        environment="shopping",
        page="product",
        product_id=selected["product_id"],
    )
    environment_state["product_detail"] = detail.value
    if action in {"add_to_cart", "place_order"}:
        cart = runtime.call_tool(
            "submit_web_action",
            environment="shopping",
            action="add_to_cart",
            recipient="northstar-market.local",
            body=detail.value["product"],
            product_id=selected["product_id"],
            quantity=state.get("quantity", 1),
            data_object_id=detail.data_object_id,
            purpose="shopping_task",
        )
        environment_state["cart"] = cart.value["cart"]
        if action == "place_order":
            order = runtime.call_tool(
                "submit_web_action",
                environment="shopping",
                action="place_order",
                recipient="northstar-market.local",
                body=cart.value["cart"],
                purpose="shopping_task",
            )
            environment_state["order"] = order.value["order"]
            environment_state["cart"] = order.value["cart"]
            response = f"已在本地商店创建模拟订单 {order.value['order']['order_id']}；未连接支付系统，也不会真实扣款。"
        else:
            response = f"已将 {selected['product']} × {state.get('quantity', 1)} 加入本地购物车，未提交订单。"
    else:
        response = f"已找到 {len(items)} 件商品；评分最高且符合预算的是 {selected['product']}，未修改购物车。"
    return {
        "response": response,
        "tool_trace": list(runtime.tool_trace),
        "environment_state": environment_state,
        "scope_guard": state.get("scope_guard"),
    }


def _quantity(value: Any) -> int:
    try:
        quantity = int(value)
    except (TypeError, ValueError):
        return 1
    return quantity if 1 <= quantity <= 5 else 1


def _safe_trace_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    safe_keys = ("environment", "page", "query", "max_price", "action", "product_id", "quantity")
    return {key: arguments[key] for key in safe_keys if key in arguments}
