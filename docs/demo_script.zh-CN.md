# 2–3 分钟演示视频脚本

[English](demo_script.md)

## 0:00–0:25 — 问题

“LLM Agent 已经不只是生成文本，它们会读取记录、发送邮件、写入记忆并发布响应。安全决策取决于数据来源、目的、转换、去向和审批状态，而不只是当前工具名称。”

展示 README 顶部并说：“AgentShield 在真实副作用发生前中介这些能力。”

## 0:25–0:50 — 架构

“LangGraph Agent 只持有窄接口 BrokerClient，独立进程持有已注册的 Mock 后端。Broker 先持久化事务，解析合规状态与血缘，执行精选策略控制；只有已授权事务才能到达 Effect Gateway。”

指向架构图并补充：“这是能力缩减，不是 OS 沙箱。”

## 0:50–1:40 — GDPR 修复

运行：

```bash
./scripts/record_gdpr_demo.sh
```

“用户只要求客户数量，但 Agent 提议发送取得的原始记录。运行时检测到个人数据，GDPR 最小化规则返回 `REPAIR: AGGREGATE`。AgentShield 创建派生对象，重新校验子事务，最后只发送 `EU customer count: 2`。”

突出真实结果：“原始 PII 邮件为 0，聚合邮件为 1。Agent 与 Broker PID 不同，Agent 正常表面没有原始后端句柄。”

## 1:40–2:10 — PIPL 审批

在 Dashboard 切换到 PIPL 并运行场景。“向外部传输敏感信息会进入 `WAITING_APPROVAL`，此时副作用数量仍为 0。点击 Approve 会调用真实 Broker API，记录精确范围证据，在重启后重建状态，并在执行前重新校验。”

展示 `Re-verification: PASS` 与一个已执行副作用。说明 Deny 会保持不执行，并且该演示不声称合成样本之外存在法律上的有效同意。

## 2:10–2:30 — 重启与幂等

运行：

```bash
./scripts/record_idempotency_demo.sh
```

“Broker 重启后，第二个请求使用相同 `effect_id`。系统返回 `IDEMPOTENT_REPLAY`，后端执行次数保持为 1。这是已提交本地副作用的完整性控制，不是分布式精确一次交付。”

## 2:30–2:50 — 证据与收尾

“项目当前通过 115 项自动化测试，其中包括 20 项 Broker 安全专项测试。100 次本地 Mock 基准测得 Broker 路径平均 14.5311 ms；这是透明的本地证据，不是生产延迟声明。”

最后停留在时间线：“项目的差异化是生命周期强制执行、对象级状态、血缘、能力中介和持久化副作用安全的组合。”

## 录屏辅助脚本

三个脚本都会创建新的临时数据库，并在退出时清理：

```bash
./scripts/record_gdpr_demo.sh
./scripts/record_pipl_demo.sh
./scripts/record_idempotency_demo.sh
```

若本机已有 `asciinema`，无需增加项目依赖即可录制：

```bash
asciinema rec -c './scripts/record_gdpr_demo.sh' gdpr-demo.cast
```
