# AutoPolicy、AWM 与 WebArena 集成

## 目标

本项目只实现 ShieldAgent 防护 Agent。法规抽取、任务 Agent 和 Web 环境复用论文使用或对应的开放项目，并以固定 revision 接入。这样可以把求职项目的技术贡献准确限定在运行时安全层，而不把自研玩具环境表述成论文系统。

## 可信边界

三个上游都位于 AgentShield 的可信运行时之外：

- AutoPolicy 的 LLM 输出是不可信候选数据；
- AWM 的模型输出是不可信动作提案；
- WebArena 页面内容是不可信环境观察；
- 只有人工审核的规则包、AgentShield 代码和受保护 Broker 配置属于策略执行信任根。

因此，AutoPolicy 输出不会自动激活，AWM 动作不会直接执行，页面文本也不能修改规则或关闭 ShieldAgent。

## AutoPolicy 适配

`agentshield.integrations.autopolicy` 通过参数数组调用固定上游，不使用 shell，也不把 API Key 放入参数。运行完成后，它要求并校验六类输出：

1. `*_all_extracted_policies.json`
2. `*_all_extracted_rules.json`
3. `*_risk_categories.json`
4. `*_policy_rule_mapping.json`
5. `*_extraction_report.json`
6. 可选的 `*_ltl_rules.json`

结构化政策必须具有 `policy_id`、术语定义、适用范围、政策描述、可追溯引用。自然语言规则必须具有唯一 `rule_id`，并引用已存在的 policy。LTL 候选必须具有谓词、描述、公式和 action/physical 类型。

通过结构校验仍不代表语义正确。Bundle 固定标记为 `REVIEW_REQUIRED` 和 `executable=false`。审核人还必须检查：

- 引用是否真的支持抽取内容；
- 规则是否改变了原文限定范围；
- 谓词是否可由运行时可信证据观察；
- LTL 是否与自然语言规则同义；
- action rule 与 physical rule 是否分类正确；
- 违反规则时应阻断、修复、重新规划、请求同意还是请求审批；
- 规则冲突如何处理。

完成这些工作后，才能生成本仓库 `regulations/*` 使用的审核后规则包。

## AWM 适配

`ShieldedBrowserAgent` 使用组合而非 fork：它持有原 AWM Agent，并转发 `obs_preprocessor` 和 `action_set`。每次 `get_action` 返回后，动作先进入 `BrowserGymActionGuard`。

Guard 使用 Python AST 解析高层动作，不执行动作文本。随后根据动作和观察将提案规范化为生命周期事件：

- `fill/type/upload_file`：潜在外部传输；
- `send_msg_to_user`：响应发布；
- `click/press/select_option/drag_and_drop`：结合页面证据判断是否可能产生副作用；
- 纯导航与读取：普通工具动作。

动作字符串只在内存中用于检测和校验。持久化审计保存 SHA-256、长度、动作类型、命中规则、谓词真值和决定，不保存原始动作内容。

## 在线重新规划

当 ShieldAgent 不允许动作时，适配器不会调用 WebArena。它把防护决定和相关规则 ID 转换为 `last_action_error`，再调用同一个 AWM Agent 重新规划。这样保留了 AWM 自己的提示、工作流记忆和动作空间。

达到最大重新规划次数后，适配器返回 BrowserGym `send_msg_to_user(...)` 安全终止动作。终止文本由本地代码固定生成，不能由被阻断动作控制。

## 用户接管检查点

并非所有拒绝都适合自动重新规划。当法规规则返回 `REQUIRE_APPROVAL` 或 `REQUIRE_CONSENT` 时，组合适配器会生成 `PENDING_USER` 检查点并立即结束当前自动轨迹，高风险动作不会到达 `env.step()`。检查点只包含随机 ID、动作指纹、接收方指纹、相关规则 ID、证据类型和三十分钟有效期，不保存动作原文或个人信息。

Dashboard 会把检查点显示为一项用户待办。用户应在目标网站或受控渠道中亲自完成敏感步骤，再提交“已完成”证明。系统验证检查点 ID、状态和有效期，持久化范围绑定的完成凭证，然后启动一条独立续跑轨迹。续跑 Prompt 明确禁止 AWM 再次请求、读取、填写或输出已由用户处理的个人信息，只允许完成原任务剩余的非敏感步骤。

固定版 BrowserGym 不支持从进程外原地恢复同一浏览器轨迹，因此这里采用“停止旧轨迹、验证凭证、新轨迹续跑”。当前证据等级是 `USER_ATTESTATION`，表示管理员声明已完成；若部署环境提供可信回调、签名收据或页面状态证明，应将其替换为机器可验证证据。

## WebArena 适配

WebArena 站点本身由官方开源仓库部署，BrowserGym 负责环境接口。本仓库检查 canonical WebArena 源码 revision，以及运行所需的站点 URL 环境变量。它不会内置账号、复制数据库镜像或替用户启动外部站点。

集成支持两种任务来源：`webarena.<id>` 使用官方基准任务及其真实 intent；`openended` 使用 BrowserGym 通用环境，把用户 Prompt 作为 `goal`，并把起始 URL 限定到已部署的 WebArena 站点。后者使用真实 WebArena 网站，但不是官方基准任务。Prompt 通过子进程环境传递，不出现在启动参数或审计载荷中。

运行结果保留两套相互独立的证据：

- BrowserGym/ExpArgs 的环境轨迹，用于任务与页面行为复查；
- AgentShield 的载荷最小化审计，用于证明每个动作在执行前经过何种规则核验。

## 已知限制

- 当前审核后运行时包只覆盖 GDPR/PIPL 的部分技术控制；
- AutoPolicy 开放 revision 中自然语言抽取固定使用 Claude，LTL 抽取固定使用 GPT-4o；
- AWM revision 使用 BrowserGym 0.3 与较旧的 LangChain API，依赖安装需要隔离环境；
- 隔离环境不安装主项目的 `langgraph` 依赖；子进程以项目根目录为工作目录直接加载 ShieldAgent，避免把不兼容的依赖组合伪装为可用；
- 上游 AWM requirements 存在一处换行排版错误；项目侧 `requirements-paper.txt` 只修正安装清单，不修改 submodule；
- WebArena 需要独立部署多个站点，不能仅通过 Python 包启动完整环境；
- 当前 ShieldAgent 采用确定性 fail-closed 规则，没有论文训练得到的概率权重；
- 页面动作语义分类仍可通过更细的 DOM target 解析与站点能力模型增强。
