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

## WebArena 适配

WebArena 站点本身由官方开源仓库部署，BrowserGym 负责环境接口。本仓库检查 canonical WebArena 源码 revision，以及运行所需的站点 URL 环境变量。它不会内置账号、复制数据库镜像或替用户启动外部站点。

集成支持两种任务来源：`webarena.<id>` 使用官方基准任务及其真实 intent；`openended` 将用户 Prompt 作为 BrowserGym `goal`，并把起始 URL 限定到已部署的 WebArena 站点。Prompt 通过子进程环境传递，不出现在启动参数或审计载荷中。

运行结果保留两套相互独立的证据：

- BrowserGym/ExpArgs 的环境轨迹，用于任务与页面行为复查；
- AgentShield 的载荷最小化审计，用于证明每个动作在执行前经过何种规则核验。

## 已知限制

- 当前审核后运行时包只覆盖 GDPR/PIPL 的部分技术控制；
- AutoPolicy 开放 revision 中自然语言抽取固定使用 Claude，LTL 抽取固定使用 GPT-4o；
- AWM revision 使用较旧的 BrowserGym/LangChain API，依赖安装需要隔离环境；
- 上游 AWM requirements 存在一处换行排版错误；项目侧 `requirements-paper.txt` 只修正安装清单，不修改 submodule；
- WebArena 需要独立部署多个站点，不能仅通过 Python 包启动完整环境；
- 当前 ShieldAgent 采用确定性 fail-closed 规则，没有论文训练得到的概率权重；
- 页面动作语义分类仍可通过更细的 DOM target 解析与站点能力模型增强。
