# 简历素材

[English](resume_material.md)

## 版本 A — 一句话

**AgentShield — LLM Agent 运行时安全与合规控制框架：**以固定版本 AutoPolicy、AWM 和 WebArena 构建论文同源执行链，并在每个 BrowserGym 动作进入环境前完成可验证规则核验、反馈重规划或阻断。

## 版本 B — 两条 Bullet

- 组合而非改写开源 AWM，在 `get_action()` 与 WebArena `env.step()` 之间实现 ShieldAgent 前置防护；不安全动作携带规则反馈返回原 Agent 重新规划。
- 接入 AutoPolicy 的文档解析、结构化政策、自然语言规则与 LTL 候选抽取，并以来源关联、哈希校验和人工审核门阻止候选规则自动进入执行信任根；全套 141 项测试通过。

## 版本 C — 三条技术 Bullet

- 固定 AutoPolicy、AWM、WebArena 的 revision 与许可证边界；将开放法规抽取结果标记为 `REVIEW_REQUIRED`，生成不可执行的人工审核模板。
- 开发 BrowserGym 动作 Guard，对 AWM 动作执行 AST 解析、规则电路检索、三值谓词赋值与 fail-closed 核验，并在实际网页副作用前反馈重规划或安全终止。
- 构建本机回环 Capability Broker 与参考监控 Gateway，实现持久化事务、阻断父事务/重新校验子事务的修复、跨重启审批暂停/恢复，以及已完成副作用的应用层至多一次重放。
- 交付 AWM/ShieldAgent 双轨迹可视化与本地可重复安全夹具；通过 141 项测试（20 项 Broker 安全专项），100 次本地 Mock 测量中 Broker 路径平均 14.5311 ms。

## 面试安全表述

使用“部分可在运行时执行的技术控制”，不要写“符合 GDPR/PIPL”。使用“已提交副作用的应用层至多一次重放”，不要写“精确一次”。使用“独立进程能力缩减”，不要写“沙箱”或“绝对隔离”。
