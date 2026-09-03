# Capability Broker 设计

[English](capability_broker.md)

## 目的

`CapabilityBroker` 将 Agent 动作从直接 Python 函数调用变为策略感知的事务提案。它持有能力注册表、已有 AgentShield 校验器、审批管理器、SQLite 存储和副作用网关。`BrokerClient` 不包含后端对象或凭据。

实现有意保持为适合面试现场阅读的规模：

- `agentshield/capabilities/models.py`：请求/响应契约；
- `agentshield/capabilities/registry.py`：四项允许的能力；
- `agentshield/capabilities/broker.py`：策略与事务编排；
- `agentshield/capabilities/service.py`：本机回环进程边界；
- `agentshield/effects/transactions.py`：事务创建与状态转换；
- `agentshield/effects/gateway.py`：最终授权检查与 Mock 副作用；
- `agentshield/effects/store.py`：持久化 SQLite 状态；
- `agentshield/approval/manager.py`：精确范围审批。

## 接口契约

请求示例：

```python
CapabilityRequest(
    request_id="...",
    trajectory_id="...",
    capability_id="email.send",
    arguments={"recipient": "...", "body": {...}, "purpose": "..."},
    referenced_data_objects=("customer-records-001",),
    effect_id="调用方可选的稳定 ID",
)
```

响应包含持久标识符、状态/决策、适用时的安全结果值、数据对象 ID、重放标记、处理结果、触发规则和错误。

能力不是任意工具名称。当前注册表只接受 `customer.read`、`email.send`、`memory.write` 和 `response.release`，并显式声明数据源/汇、持久写入、副作用和信任边界属性。

## 端到端授权

```text
客户端提案
  -> 注册表白名单
  -> 已完成 effect_id 查询
  -> 持久化 CREATED 事务
  -> 策略 CHECKING
  -> 阻断 / 暂停 / 修复子事务 / 授权
  -> 持久化 EXECUTING
  -> 网关重新加载并校验事务
  -> Mock 后端副作用
  -> 持久化 effect 与 SUCCEEDED 事务
  -> 载荷最小化审计/响应
```

网关有意采用有状态设计：仅提供看似合理的参数不足以执行，调用方必须引用与同一能力绑定的持久授权状态。

## 重启后的数据对象连续性

策略检查依赖对象分类与血缘。对于暂停事务，SQLite 会保存引用对象 ID 与原始载荷。新 Broker 进程审批该事务时，会在新的按轨迹 Adapter 会话中重建对象，然后再执行策略校验。

这足以支持确定性的参考 Fixture。生产系统应独立持久化完整合规状态与血缘模型，并提供 Schema 版本和保留期控制，而不是从事务参数重建。

## 审批是证据，不是覆盖开关

预期范围由持久化提案计算：

```json
{
  "data_objects": ["customer-records-001"],
  "purpose": "customer_service",
  "recipient": "partner@example.test",
  "operation": "email.send"
}
```

范围不匹配会被拒绝。匹配的审批会被记录，并提供相应可信生命周期证据；最终仍由策略引擎决策。这样可以防止一个通用 `approved=true` 标记绕过无关规则或执行前的参数修改。

## 幂等

稳定副作用 ID 可以由调用方提供，也可以根据规范化的轨迹、能力、参数和对象引用计算 SHA-256 摘要。`effects.effect_id` 主键是去重点。成功重放使用已存储的非敏感副作用元数据；邮件与记忆载荷正文不会写入 effects 表。

限制包括：

- 语义输入变化会生成不同的派生 effect ID；
- 调用方提供 ID 时必须遵守正确使用纪律；
- 去重范围限于一个数据库；
- 真实服务商也应接收服务商原生幂等键；
- `EXECUTING` 状态下崩溃会产生不确定性，因此自动重放不安全。

## 操作参考服务

求职演示会自动启动临时本机 Broker：

```bash
agentshield demo gdpr
```

如需持久化运维交互，请指定数据库路径：

```bash
agentshield demo pipl --pause-only --db .agentshield/runtime.db
agentshield transactions list --db .agentshield/runtime.db
agentshield approve <transaction_id> --db .agentshield/runtime.db
```

服务端点（`/capabilities`、`/approve`、`/deny`、`/transactions`、`/approvals`、`/audit`、`/metrics`、`/stats`、`/health`）是没有认证的参考 API。不要将该服务器暴露到受控本地演示之外。

## 生产加固方向

生产后续版本需要加入：认证 Unix Domain Socket 或 mTLS、按主体能力授权、请求签名/Nonce、数据库加密与迁移、服务商级幂等、租约/栅栏、优雅关闭、持久化血缘、防篡改远端审计、限流、可观测性和明确的人工恢复手册。

这些是文档化的扩展方向，不是本阶段已经实现的能力。
