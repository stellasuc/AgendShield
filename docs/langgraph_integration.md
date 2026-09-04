# LangGraph integration

[简体中文](langgraph_integration.zh-CN.md)

## Tested API

The tested integration uses LangGraph 1.2.9 and `langchain-core` 1.5.6. A `StateGraph` is compiled into a runnable supporting `invoke` and `ainvoke`. The customer-service example contains separate planner and action nodes and uses the same tool registry/business code in protected and unprotected modes.

Relevant official documentation:

- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [CompiledStateGraph reference](https://reference.langchain.com/python/langgraph/graph/state/CompiledStateGraph)
- [LangGraph persistence and stores](https://docs.langchain.com/oss/python/langgraph/persistence)

## Wrapping flow

```python
agent = build_customer_service_agent()
secured_agent = AgentShield(["GDPR"]).wrap(agent)
result = secured_agent.invoke({"messages": [...]})
```

`wrap()` validates the runtime-bindable contract. At invocation it creates a fresh `LangGraphAdapter`, emits `USER_REQUEST`, recompiles the same graph around that runtime gateway, invokes it, ingests the generated response, and releases only the verified candidate.

## Hook capabilities

| Hook | Status | Mapping |
| --- | --- | --- |
| `on_user_request` | Supported | `USER_REQUEST` |
| `on_plan` | Interface only | Planning capability is false |
| `before_tool_call` | Supported | `TOOL_CALL` or `EXTERNAL_TRANSFER` |
| `after_tool_result` | Supported | `TOOL_RESULT` + data object |
| `before_memory_write` | Supported | `MEMORY_WRITE` before store |
| `after_memory_write` | Supported | Causal `TOOL_RESULT` after store |
| `before_response_release` | Supported | Response ingestion + `RESPONSE_GENERATED` |
| `after_response_release` | Supported | Return boundary |
| `on_agent_error` | Supported | `AGENT_ERROR` |

## Tool metadata

`@agentshield_tool` and `ToolRegistry` express `side_effect`, `data_source`, `data_sink`, `persistent_storage`, `trust_boundary`, and `source_trust_level`. Tool names are informational only. Registry entries can attach a result-object prefix and trusted policy metadata.

Unknown high-risk metadata is conservative: it requires approval before execution. Unknown classification on an external transfer follows the same path.

## Tool result ingestion

Data-source results become data objects. The adapter records source trust and suspicious instruction-like text, but never treats retrieved text as policy or executable instruction. The privacy detector populates classification/categories and data lineage supplies later calls with provenance by object ID.

## Memory integration

Persistent storage is represented as an explicitly registered tool. `before_memory_write` verifies referenced objects before the registry invokes the store callable. A blocked write cannot reach `MockMemoryStore.save`. A non-personal aggregate can pass because its classification is resolved from state.

This does not automatically wrap arbitrary direct calls to a LangGraph store or checkpointer. Production code must route long-term-memory effects through the runtime gateway.

## Response integration

The raw generated response is first ingested as a non-released object. The technical release guard detects PII and, if necessary, creates a redacted derivative. The release candidate then emits `RESPONSE_GENERATED` and goes through the policy engine. Enforce mode returns only that candidate; audit mode intentionally returns the original.

## Async and concurrency

`ainvoke` creates isolated per-run state and executes the synchronous protected invocation in a worker thread. UUID event/correlation/tool-call IDs remain independent. V1 supports sequential or controlled tool execution within one graph run. Parallel `ToolNode` fan-out, distributed state transactions, and nested parallel subgraphs are unsupported.

## Unsupported lifecycle boundaries

- arbitrary internal planning from an already-compiled graph;
- arbitrary `ToolNode` internals not routed through `ToolRuntimeGateway`;
- direct LangGraph checkpointer/store writes;
- streaming partial-response release;
- distributed/parallel tool commit coordination.
