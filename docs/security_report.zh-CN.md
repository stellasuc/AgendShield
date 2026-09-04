# 安全工程报告

[English](security_report.md)

## 结果

当前系统使用独立进程 Capability Broker、持久化副作用事务、限定范围审批和跨重启幂等，解决了 Adapter-only 参考应用中最强的绕过点：原始后端与 Agent 同处一个进程。

实现复用了已有 LangGraph Adapter、血缘模型、策略引擎、GDPR/PIPL 法规包、修复循环和响应保护，没有新增法规，也没有扩大法律声明。

## 已交付范围

| 交付项 | 证据 |
| --- | --- |
| Capability Broker | 固定四项能力注册表和窄接口客户端 |
| Brokered 邮件/记忆/响应 | 原始 Mock 后端仅由 Broker 网关构造 |
| 持久化副作用事务 | 显式状态机、修复父事务与执行次数 |
| SQLite 持久化 | `transactions`、`effects`、`approvals`、`audit_events` |
| 幂等副作用 | 唯一稳定 `effect_id`；跨重启重放演示 |
| 审批暂停/恢复 | 对象/目的/接收方/操作精确范围与重新校验 |
| GDPR Broker 演示 | 不同 PID、Agent 无后端句柄、聚合 1、原始 PII 0 |
| PIPL 审批演示 | 等待状态跨重启；审批前邮件 0、审批后邮件 1 |
| 幂等演示 | 重启后第二次请求被重放，计数保持 1 |
| 安全测试 | Broker 聚焦测试 20 项；全套 141 项通过 |
| 性能 | 5 次预热、100 次测量及组件耗时 |
| 求职文档 | Broker 设计、架构、威胁模型、报告与面试指南 |

## 演示结果

### GDPR 能力缩减与修复

```text
separate_process: true
raw_backend_exposed_on_agent_surface: false
email_messages: 1
raw_pii_messages: 0
aggregate_messages: 1
repair_transactions: 1
authorized_repair_children: 1
```

### PIPL 持久化审批

```text
initial_status: WAITING_APPROVAL
persisted_status_after_restart: WAITING_APPROVAL
email_messages_before_approval: 0
approval_result: SUCCEEDED
approval_disposition: EXECUTED
email_messages_after_approval: 1
approval_records: 1
```

### 跨重启幂等

```text
first_request: EXECUTED
retry: IDEMPOTENT_REPLAY
replayed: true
email_messages_after_first: 1
email_messages_after_restart_and_retry: 1
```

## 验证

```bash
.venv/bin/pytest -q tests/test_broker_security.py
# 20 passed

.venv/bin/pytest -q
# 141 passed
```

安全套件覆盖：创建事务前拒绝、原始传输修复、修复子事务重新校验、记忆写入前阻断及重试、响应脱敏、未授权网关调用、同进程与跨重启幂等、等待审批持久化、范围不匹配、审批后重新校验、拒绝审批、审计最小化、崩溃恢复、授权恢复、来源恢复、API 表面、进程分离和 CLI 最小化。

## 性能

数据来源：`evaluation/results/broker_runtime.json`。

| 指标 | 平均值 | 中位数 | p95 |
| --- | ---: | ---: | ---: |
| 直接 Mock | 0.002180 ms | 0.002083 ms | 0.003250 ms |
| Broker 安全副作用 | 14.531114 ms | 14.449521 ms | 15.350542 ms |
| 新增延迟 | 14.528934 ms | 14.447604 ms | 15.347958 ms |
| 策略校验 | 0.393274 ms | 0.381521 ms | 0.477708 ms |
| SQLite 事务持久化 | 1.605186 ms | 1.573478 ms | 1.838167 ms |
| 幂等查询 | 0.155808 ms | 0.150375 ms | 0.193417 ms |
| 审计持久化 | 0.748956 ms | 0.729104 ms | 0.897957 ms |

这是本机回环 HTTP、SQLite 与 Mock 的测试。它适合作为实现基线，而不是生产容量数据。组件计时没有覆盖完整请求，特别是 HTTP/进程调度以及网关/effect 持久化。

## 安全解读

Brokered 架构显著提升了参考路径上的能力约束和恢复语义。正确声明是：

> 正常 Brokered Agent 无法通过其 API 获得原始 Mock 副作用对象；每个注册副作用在网关分派前都会根据持久事务进行检查。

错误声明是：

> Agent 已经被沙箱化，或无法执行任何未经批准的副作用。

要支持后一个声明，还需要限制所有 OS/网络/插件/文件能力，认证 Broker 端点，保护数据库与进程，并证明服务商级执行语义。

## 已知局限

- 未认证的本机 HTTP 参考服务；
- 除进程持有关系外，没有 OS 沙箱或凭据隔离；
- 原始参数以未加密形式保存在可信 SQLite 状态；
- 单机与进程内锁；
- Mock 后端，不具有真实外部服务原子性；
- 结果不确定的崩溃需要人工审查；
- 审批重启时重建血缘，而不是完整持久化血缘；
- 法规包覆盖局部，检测器可能出错；
- 审批证据不是法律证明。

明确列出这些边界，是为了让项目同时展示安全判断力与实现能力。
