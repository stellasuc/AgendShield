# ShieldAgent 200 条可执行测试用例

本测试集参考本地 [ShieldAgent.pdf](../ShieldAgent.pdf) 的 ShieldAgent-Bench 设计：被保护 Agent 为 AWM，环境为 Shopping、CMS、Reddit、GitLab、Maps、SuiteCRM 六类 WebArena 场景；论文附录 E.1 将风险轨迹划分为访问限制、内容限制、幻觉、指令遵循、操作限制、典型错误和长期风险。

当前 AgentShield 没有实现论文中的通用内容审核、事实核查、循环检测或长期记忆风险模型，因此本集只纳入本仓库能够真正运行并裁决的控制，不把未实现能力标为“已拦截”。所有联系方式、身份证件和支付卡号码均为合成测试值；测试动作只被 AST 解析和规则核验，绝不执行。

| 结果 | 数量 | 代表范围 | 当前实际裁决 |
|---|---:|---|---|
| 正常运行 | 40 | 六个 WebArena 环境中的公开浏览、搜索、筛选与非个人数据输入 | `ALLOW` |
| GDPR 个人数据表单输入 | 45 | 合成邮箱 | `REQUIRE_APPROVAL` |
| PIPL 敏感信息表单输入 | 35 | 合成证件号、支付卡测试值 | `REQUIRE_APPROVAL` |
| 越界工具/动作空间调用 | 40 | shell、文件、网络、支付、管理工具调用 | `REPLAN` |
| GDPR 个人数据回复外发 | 20 | 合成邮箱回复 | `REQUIRE_APPROVAL` |
| PIPL 敏感信息回复外发 | 20 | 合成证件信息回复 | `REQUIRE_APPROVAL` |
| **合计** | **200** | **40 条允许（20%）+ 160 条拦截或要求人工授权（80%）** | |

用例定义在 [shieldagent_bench_200_cases.py](../tests/fixtures/shieldagent_bench_200_cases.py)，运行测试：

```bash
pytest -q tests/test_shieldagent_bench_200.py
```

每条用例都包含唯一 ID、中文标题、环境、论文风险类别、法规、合成任务 Prompt、候选 BrowserGym 动作、预期裁决和预期放行状态。它验证的是当前项目的确定性 fail-closed 核验，不是对论文训练后的 ASPM 权重、MLN 概率推理或论文基准成绩的复现。
