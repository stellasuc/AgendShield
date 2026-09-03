# 安全评估

[English](security_evaluation.md)

## 可复现结果

使用 Python 3.12.13、确定性 Mock 后端、本机回环 HTTP 与 SQLite 重新测量：

| 检查项 | 实际结果 |
| --- | ---: |
| 全量自动化测试 | 118 passed |
| Broker 安全专项测试 | 20 passed |
| 性能测量次数 | 100（另有 5 次预热） |
| Broker 安全路径平均 / 中位数 / p95 | 14.531114 / 14.449521 / 15.350542 ms |
| 新增延迟平均 / 中位数 / p95 | 14.528934 / 14.447604 / 15.347958 ms |

复现命令：

```bash
python -m pytest -q
python -m pytest -q tests/test_broker_security.py
python -m evaluation.broker_runtime
```

机器可读证据位于 [`../evaluation/results/portfolio_validation.json`](../evaluation/results/portfolio_validation.json) 与 [`../evaluation/results/broker_runtime.json`](../evaluation/results/broker_runtime.json)。耗时包含进程/回环分派、策略检查、SQLite、审计、Gateway 持久化和 Mock 邮件副作用，不包含 LLM 推理或远程服务，也不是生产延迟声明。

## 已验证安全属性

- 未知能力在创建事务前被拒绝；
- Gateway 拒绝未授权或能力不匹配的分派；
- GDPR 原始个人记录被修复为聚合，原始 PII 邮件计数保持为零；
- 修复子事务和审批恢复事务都会重新校验；
- PIPL 传输持久暂停，精确范围审批可跨 Broker 重启；
- 不安全记忆持久化与响应泄露在发布前被拦截；
- 已完成 `effect_id` 在重启后重放，且不会重复执行 Mock 副作用；
- 结果不确定的执行中副作用进入人工审查，而非自动重试；
- 审计、CLI 时间线和 Dashboard 投影不包含原始载荷；
- 正常 Brokered Agent 表面不暴露原始 Mock 后端句柄。

## 如何理解这些结果

这些测试证明参考实现的确定性属性，不代表普遍安全或法律合规。检测器使用合成样本，后端均为本地 Mock，Broker 通信是未认证的本机回环 HTTP，并发与分布式故障语义有意不在范围内。最重要的证据是副作用前拦截断言、持久状态检查、重启测试和最终效果计数的组合，而不只是测试数量。
