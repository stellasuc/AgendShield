# ShieldAgent 200 条运行时安全测试报告

**执行日期：** 2026-09-06  
**代码版本：** `f700149`（本报告生成时的基线）  
**测试层级：** BrowserGym 候选计划步骤的运行时核验单元/集成测试；不使用真实 API Key，不调用在线模型，不触发真实网页副作用。

## 结论

200 条用例全部符合当前 AgentShield 的实际能力边界，专项测试 **201 passed**（200 条参数化用例加 1 条分布校验），项目全量回归 **352 passed**。其中 40 条安全候选步骤被放行，160 条风险候选步骤在进入 `WebArena env.step()` 前被拦截为 `REPLAN` 或 `REQUIRE_APPROVAL`；没有出现“预期拦截却被放行”或“预期放行却被阻断”。

这组数据适合展示以下结论：**当前 AgentShield 能对受保护 AWM Agent 的候选 BrowserGym 动作实施确定性、可复现、执行前的隐私与能力边界控制。**

## 用例设计来源与范围

用例参考本地论文 [ShieldAgent.pdf](../ShieldAgent.pdf) 中的 ShieldAgent-Bench：论文以 AWM 为被保护 Agent，覆盖 Shopping、CMS、Reddit、GitLab、Maps、SuiteCRM 六类 WebArena 环境，并将风险划分为访问限制、内容限制、幻觉、指令遵循、操作限制、典型错误和长期风险。

本项目目前实际实现并验证的是 GDPR/PIPL 数据处理规则与 BrowserGym 动作空间边界。因此报告只纳入能由现有代码真实裁决的三类论文相关风险：访问限制、内容/个人信息外发限制、操作限制；不把幻觉、通用有害内容、典型错误或长期风险伪装成“已覆盖”。

## 结果概览

| 指标 | 结果 |
|---|---:|
| 总用例数 | 200 |
| 预期并实际放行 `ALLOW` | 40（20%） |
| 预期并实际要求人工授权 `REQUIRE_APPROVAL` | 120（60%） |
| 预期并实际反馈重规划 `REPLAN` | 40（20%） |
| 风险用例在环境副作用前未放行 | 160（100%） |
| 专项测试 | 201 passed / 2.79 s |
| 全量项目测试 | 352 passed / 7.74 s |

## 用例族与裁决

| 用例族 | 数量 | 场景 | 实际裁决 |
|---|---:|---|---|
| `SAFE` | 40 | 公开浏览、非个人数据搜索、筛选、页面导航 | `ALLOW` |
| `GDPR-PII` | 45 | 未授权向网页表单填写合成邮箱 | `REQUIRE_APPROVAL` |
| `PIPL-SENSITIVE` | 35 | 未授权提交合成证件号、支付卡测试值 | `REQUIRE_APPROVAL` |
| `ACTION-SPACE` | 40 | shell、文件、网络、支付、管理等未注册调用 | `REPLAN` |
| `GDPR-RESPONSE` | 20 | 在最终回复中披露合成邮箱 | `REQUIRE_APPROVAL` |
| `PIPL-RESPONSE` | 20 | 在最终回复中披露合成敏感标识符 | `REQUIRE_APPROVAL` |

## 环境分布

| WebArena 环境 | 用例数 |
|---|---:|
| Shopping | 36 |
| CMS | 36 |
| Reddit | 34 |
| GitLab | 33 |
| Maps | 31 |
| SuiteCRM | 30 |

六类环境均被覆盖；数量差异来自 200 条用例按环境循环分配，最大差异为 6 条，不影响规则核验覆盖。

## 合理性审查

通过以下检查后，该测试集可以作为当前代码版本的求职展示证据：

- **真实裁决一致性**：每条用例都实际调用 `BrowserGymActionGuard.verify()`，断言 `allowed` 与 `decision`；不是仅检查静态标签。
- **无真实敏感数据**：邮箱统一使用 `@example.test`；证件号与支付卡号均是合成检测样本；审计不会持久化原始动作载荷。
- **不执行危险动作**：`ACTION-SPACE` 中的 shell、文件、网络或支付调用只经过 Python AST 解析，因不在 BrowserGym 白名单而返回 `REPLAN`，不会被解释或执行。
- **安全用例占比明确**：40/200 为可通过的正常浏览与非个人数据操作，避免只测“全部阻断”造成过度防护的假象。
- **法规语义不夸大**：`REQUIRE_APPROVAL` 表示技术控制要求人工授权或用户接管，不宣称系统自动完成法律上的有效同意或合规结论。

## 已知边界

这不是 ShieldAgent 原论文的完整复现，也不是 AWM + WebArena 的端到端成功率基准：选择器、网页观察和候选动作均为合成的 BrowserGym 层测试输入，未使用在线大模型或真实 WebArena 站点状态。

尚未覆盖的论文风险类别包括：事实幻觉、通用有害内容审核、循环/冗余操作模式、长期累计风险。若实现对应的来源证据、内容检测器和持久化时间窗口状态机，可在同一格式下扩展新增用例族。

## 复现方式

```bash
pytest -q tests/test_shieldagent_bench_200.py
pytest -q
```

用例定义：[shieldagent_bench_200_cases.py](../tests/fixtures/shieldagent_bench_200_cases.py)；专项测试：[test_shieldagent_bench_200.py](../tests/test_shieldagent_bench_200.py)。
