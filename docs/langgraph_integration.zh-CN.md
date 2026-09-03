# LangGraph 集成

[English](langgraph_integration.md)

## 已测试 API

当前已测试集成使用 LangGraph 1.2.9 与 `langchain-core` 1.5.6。`StateGraph` 被编译为支持 `invoke` 与 `ainvoke` 的 Runnable。客户服务示例包含独立的 planner 和 action 节点，受保护与未保护模式复用同一工具注册表和业务代码。

相关官方文档：

- [LangGraph 概览](https://docs.langchain.com/oss/python/langgraph/overview)
- [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [CompiledStateGraph 参考](https://reference.langchain.com/python/langgraph/graph/state/CompiledStateGraph)
- [LangGraph 持久化与 Store](https://docs.langchain.com/oss/python/langgraph/persistence)

## 包装流程

```python
agent = build_customer_service_agent()
secured_agent = AgentShield(["GDPR"]).wrap(agent)
result = secured_agent.invoke({"messages": [...]})
```

`wrap()` 会校验可绑定运行时的契约。调用时，它创建新的 `LangGraphAdapter`，发出 `USER_REQUEST`，围绕该运行时网关重新编译同一张图，执行图，接收生成响应，并只发布经过校验的候选响应。

## Hook 能力

| Hook | 状态 | 映射 |
| --- | --- | --- |
| `on_user_request` | 支持 | `USER_REQUEST` |
| `on_plan` | 仅接口 | 规划能力为 false |
| `before_tool_call` | 支持 | `TOOL_CALL` 或 `EXTERNAL_TRANSFER` |
| `after_tool_result` | 支持 | `TOOL_RESULT` + 数据对象 |
| `before_memory_write` | 支持 | Store 前的 `MEMORY_WRITE` |
| `after_memory_write` | 支持 | Store 后具有因果关系的 `TOOL_RESULT` |
| `before_response_release` | 支持 | 响应接收 + `RESPONSE_GENERATED` |
| `after_response_release` | 支持 | 返回边界 |
| `on_agent_error` | 支持 | `AGENT_ERROR` |

## 工具元数据

`@agentshield_tool` 和 `ToolRegistry` 显式描述 `side_effect`、`data_source`、`data_sink`、`persistent_storage`、`trust_boundary` 与 `source_trust_level`。工具名称仅用于标识，不参与风险推断。注册项可以附带结果对象前缀和可信策略元数据。

未知的高风险元数据会被保守处理：执行前需要审批。外部传输中的未知数据分类采用相同策略。

## 工具结果接收

数据源结果会成为数据对象。Adapter 记录来源可信度和疑似指令式文本，但绝不会把检索文本当作策略或可执行指令。隐私检测器填充分类与类别，数据血缘通过对象 ID 为后续调用提供来源信息。

## 记忆集成

持久存储被表示为显式注册工具。`before_memory_write` 会在注册表调用 Store 函数前校验引用对象。被阻断的写入无法到达 `MockMemoryStore.save`。非个人信息聚合可以通过，因为其分类会从状态中解析。

该机制不会自动包装对 LangGraph Store 或 Checkpointer 的任意直接调用。生产代码必须让长期记忆副作用经过运行时网关。

## 响应集成

原始生成响应首先作为尚未发布的对象接收。技术性发布保护会检测 PII，必要时创建脱敏派生对象。候选响应随后发出 `RESPONSE_GENERATED` 并经过策略引擎。Enforce 模式只返回该候选；Audit 模式会有意返回原始值。

## 异步与并发

`ainvoke` 为每次运行创建隔离状态，并在线程池中执行同步保护调用。UUID 事件、关联和工具调用 ID 保持独立。V1 支持一次图运行中的顺序或受控工具执行，不支持并行 `ToolNode` 扇出、分布式状态事务或嵌套并行子图。

## 不支持的生命周期阶段

- 对已编译图内部任意规划过程的拦截；
- 未经过 `ToolRuntimeGateway` 的任意 `ToolNode` 内部调用；
- 直接 LangGraph Checkpointer/Store 写入；
- 流式局部响应发布；
- 分布式或并行工具提交协调。

Brokered Agent 将 Adapter 放入可信 Broker 进程，以缩小 Agent 直接持有原始后端造成的绕过面；上述框架集成限制仍适用于 Adapter-only 模式。
