# 简历素材

[English](resume_material.md)

## 版本 A — 一句话

**AgentShield — LLM Agent 运行时安全与合规控制框架：**实现真实 LangGraph 集成、生命周期强制执行、独立进程 Capability Broker、对象级状态/血缘，以及 GDPR/PIPL 部分技术控制。

## 版本 B — 两条 Bullet

- 为 LangGraph Agent 构建生命周期级安全运行时，通过独立进程 Capability Broker 中介数据访问、邮件、记忆和响应发布，支持确定性策略决策、修复、审批与重新校验。
- 设计基于 SQLite 的合规状态、血缘、限定范围审批、事务恢复和 `effect_id` 重放保护；通过 113 项自动化测试，其中包含 20 项 Broker 安全专项测试。

## 版本 C — 三条技术 Bullet

- 开发类型化 Python/LangGraph 运行时，对 Agent 生命周期事件进行规范化，检测个人/敏感数据，解析对象级状态与血缘，并执行带官方来源解释的 GDPR/PIPL 精选技术规则。
- 构建本机回环 Capability Broker 与参考监控 Gateway，实现持久化事务、阻断父事务/重新校验子事务的修复、跨重启审批暂停/恢复，以及已完成副作用的应用层至多一次重放。
- 交付三个可重复安全演示和基于真实运行时数据的 Streamlit 可视化器；100 次本地 Mock 测量中 Broker 路径平均 14.5311 ms，并通过 113 项测试（20 项 Broker 安全专项）。

## 面试安全表述

使用“部分可在运行时执行的技术控制”，不要写“符合 GDPR/PIPL”。使用“已提交副作用的应用层至多一次重放”，不要写“精确一次”。使用“独立进程能力缩减”，不要写“沙箱”或“绝对隔离”。
