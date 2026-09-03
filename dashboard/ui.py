"""用户可操作的企业客户服务 Agent 工作台。"""

from __future__ import annotations

from html import escape
import time

import streamlit as st

from agentshield.planning import (
    MODEL_PROVIDERS,
    ModelConfig,
    ModelPlanningError,
    model_provider,
    verify_model_connection,
)
from dashboard.components.audit_view import render_audit, render_effects
from dashboard.components.decision_view import render_decision
from dashboard.components.lineage_view import render_lineage
from dashboard.components.state_view import render_state
from dashboard.demo_loader import (
    DemoSession,
    inspect_policy,
    resolve_pipl_approval,
    run_demo,
)


AGENT_NAME = "WebArena 风格 Web Task Agent"
EXAMPLES = {
    "购物站任务": "在购物网站查看商品页面，并提交一项受控的购买后操作。",
    "内容管理任务": "在 CMS 中查看季度更新草稿，并提交一项受控的发布准备操作。",
    "社区任务": "在 Reddit 风格社区查看支持帖子，并提交一项受控的跟进操作。",
    "代码协作任务": "在 GitLab 中查看合并请求，并提交一项受控的代码协作操作。",
    "地图任务": "在地图服务中查看地点信息，并提交一项受控的路线规划操作。",
    "CRM 任务": "在 SuiteCRM 中查看客户记录，并提交一项受控的后续处理操作。",
}


st.set_page_config(
    page_title="AgentShield · 安全执行工作台",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .block-container {max-width:1180px;padding-top:1.4rem;padding-bottom:4rem;}
    .hero {padding:1.8rem 2rem;border-radius:20px;color:#fff;background:linear-gradient(120deg,#0d2243,#174d72 56%,#08736a);box-shadow:0 16px 38px rgba(13,34,67,.16);margin-bottom:1.25rem;}
    .eyebrow {color:#9ae9da;font-size:.78rem;font-weight:800;letter-spacing:.12em;}.hero h1 {font-size:2.25rem;margin:.35rem 0 .45rem;line-height:1.1;}.hero p {max-width:800px;margin:0;color:#d9e9f7;font-size:1.03rem;line-height:1.55;}.hero-badge {display:inline-block;margin-top:1rem;padding:.34rem .68rem;border-radius:999px;background:rgba(255,255,255,.16);font-weight:700;font-size:.82rem;}
    .agent-card,.policy-ready,.track {border:1px solid #dfe7ef;border-radius:14px;background:#fff;padding:1rem 1.05rem;}.agent-card h3,.track h3 {font-size:1rem;margin:.1rem 0 .4rem;color:#172033;}.agent-card p,.track p {font-size:.9rem;color:#64748b;line-height:1.48;margin:0;}.agent-tag {font-size:.76rem;font-weight:800;color:#08736a;letter-spacing:.08em;}.policy-ready {border-color:#b9d9f8;background:#f5faff;color:#25445f;font-size:.9rem;line-height:1.55;margin:.6rem 0;}
    .result {border-radius:16px;padding:1.15rem 1.3rem;margin:1rem 0;border:1px solid #a7ded3;background:#effbf8;}.result.waiting {border-color:#f5c77e;background:#fff8e9;}.result h2 {font-size:1.3rem;margin:0 0 .35rem;color:#13453e;}.result.waiting h2 {color:#754b00;}.result p {margin:0;color:#4b5e6d;line-height:1.5;}
    .metric-card {border:1px solid #e2e8f0;border-radius:13px;padding:.85rem .95rem;background:#fbfdff;}.metric-label {font-size:.78rem;font-weight:700;color:#64748b;}.metric-value {font-size:1.18rem;font-weight:800;color:#172033;margin-top:.18rem;}
    .track {min-height:280px;background:#fbfdff;}.track.security {background:#f4fbf9;border-color:#b7ded6;}.track-label {font-size:.76rem;font-weight:800;letter-spacing:.08em;color:#08736a;margin-bottom:.65rem;}.process-step {display:flex;gap:.7rem;padding:.58rem 0;border-top:1px solid #e8edf2;}.process-step:first-of-type {border-top:0;}.step-dot {height:1.45rem;width:1.45rem;min-width:1.45rem;border-radius:50%;background:#dceaf8;color:#14507a;font-size:.72rem;font-weight:800;display:flex;align-items:center;justify-content:center;}.security .step-dot {background:#cceee5;color:#07665e;}.step-copy {font-size:.88rem;color:#334155;line-height:1.42;}.step-copy small {display:block;color:#718096;margin-top:.08rem;}
    [data-testid="stMetric"] {border:1px solid #e2e8f0;border-radius:12px;padding:.7rem .9rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


def _close_previous() -> None:
    session = st.session_state.get("demo_session")
    if isinstance(session, DemoSession):
        session.close()
    st.session_state.pop("demo_session", None)


def _scenario(regulation: str) -> str:
    return "pipl" if regulation == "PIPL" else "gdpr"


def _render_rule_content(inspection) -> None:
    st.caption("法规要求与工程控制保持分离。当前系统使用相同原子谓词进行确定性核验；未实现论文中的概率规则电路权重学习。")
    requirement_tab, rule_tab = st.tabs(("法规要求如何变成控制", "符号化运行时规则"))
    with requirement_tab:
        for requirement in inspection.requirements:
            with st.expander(f"{requirement.requirement_id} · {requirement.article}"):
                st.markdown("**法规要求摘要**")
                st.write(requirement.legal_requirement)
                st.markdown("**工程化解释**")
                st.write(requirement.engineering_interpretation)
                st.markdown("**运行时如何执行**")
                st.write(requirement.runtime_enforcement)
                st.caption("生命周期阶段：" + " · ".join(requirement.lifecycle_stages))
                st.markdown(f"[查看官方来源]({requirement.source_url})")
    with rule_tab:
        for rule in inspection.rules:
            with st.expander(f"{rule.rule_id} · {rule.intervention}"):
                st.markdown("**规则含义**")
                st.write(rule.description)
                st.markdown("**LTL 风格形式逻辑**")
                st.code(rule.formal_logic, language=None)
                st.caption("原子谓词在每次行动核验时被赋予 TRUE / FALSE；ALWAYS 表示在相关行动出现时持续约束。")
                st.dataframe(
                    [
                        {
                            "符号": item.symbol,
                            "运行时变量": item.source_variable,
                            "规则中的预期值": item.expected_value,
                            "角色": item.role,
                        }
                        for item in rule.predicates
                    ],
                    width="stretch",
                    hide_index=True,
                )
                st.markdown("**对应法规条款**")
                for article, source_url in zip(rule.source_articles, rule.source_urls):
                    st.markdown(f"[{article}]({source_url})")


@st.dialog("正在解析法规并编译规则", width="small")
def _compile_policy_dialog(regulation: str) -> None:
    progress = st.progress(5, text="读取法规映射包…")
    time.sleep(0.12)
    progress.progress(35, text="验证法规来源与工程化要求…")
    inspection = inspect_policy((regulation,))
    time.sleep(0.12)
    progress.progress(75, text="将原子谓词编译为运行时规则…")
    time.sleep(0.12)
    progress.progress(100, text="解析完成")
    st.session_state["policy_inspection"] = inspection
    st.session_state["compiled_regulation"] = regulation
    time.sleep(0.35)
    st.rerun()


@st.dialog("已解析的法规规则", width="large")
def _rule_dialog(inspection) -> None:
    _render_rule_content(inspection)


def _model_config() -> ModelConfig | None:
    config: ModelConfig | None = None
    with st.expander("第 2 步：配置在线模型连接（必填）", expanded=True):
        st.caption("安全执行前，在线模型会根据你的任务 Prompt 生成受限行动计划。未配置 API Key 时不能执行任务。支持主流模型服务商与自定义兼容端点。")
        provider_id = st.selectbox(
            "模型服务商",
            options=tuple(item.provider_id for item in MODEL_PROVIDERS),
            format_func=lambda item: model_provider(item).label,
            key="model_provider",
        )
        provider = model_provider(provider_id)
        if st.session_state.get("applied_model_provider") != provider_id:
            st.session_state["model_endpoint"] = provider.base_url
            st.session_state["model_name"] = provider.suggested_model
            st.session_state["applied_model_provider"] = provider_id
        api_key = st.text_input("模型 API Key", type="password", key="model_api_key")
        model = st.text_input("模型名称", key="model_name", placeholder="填写你的账户可用模型名称")
        endpoint_label = "OpenAI 兼容 API 地址" if provider.protocol == "openai" else "Anthropic Messages API 地址"
        endpoint = st.text_input(endpoint_label, key="model_endpoint")
        protocol_label = "OpenAI Chat Completions 兼容协议" if provider.protocol == "openai" else "Anthropic Messages 原生协议"
        st.caption(f"当前连接方式：{protocol_label}。可按你的账户权限修改模型名称和 API 地址。")
        if provider.documentation_url:
            st.markdown(f"[查看 {provider.label} 官方配置说明]({provider.documentation_url})")
        st.caption("Key 仅保留在当前浏览器会话中，不写入文件、数据库或审计日志。")
        st.caption("点击“安全执行”后，任务 Prompt 与受限能力说明将发送至该端点；模型输出的计划会再由 AgentShield 依据法规逐项核验。")
        if api_key and model.strip():
            try:
                config = ModelConfig(
                    api_key=api_key,
                    model=model,
                    base_url=endpoint,
                    provider_id=provider.provider_id,
                    protocol=provider.protocol,
                )
            except ValueError as exc:
                st.error(f"模型连接配置无效：{exc}")
        if st.button("测试 API 连接", width="content", disabled=config is None):
            try:
                with st.spinner("正在发送最小测试请求…"):
                    verified = verify_model_connection(config)
                st.success(f"连接成功：{verified.model} 可通过当前 API 配置访问。")
            except Exception as exc:
                st.error(f"连接测试失败：{type(exc).__name__}: {exc}")
        st.caption("测试只发送一条“Reply with OK.”的最小请求，不执行 Agent 任务；模型服务可能收取少量调用费用。")
        if st.button(
            "清除当前会话的 API Key",
            width="content",
            on_click=lambda: st.session_state.pop("model_api_key", None),
        ):
            st.rerun()
    return config


def _render_setup() -> tuple[tuple[str, ...], str, ModelConfig | None]:
    st.markdown(f"## {AGENT_NAME}")
    st.caption("论文式 Web 任务 Agent：根据你的 Prompt 在 WebArena 风格环境中读取页面并提交受控动作；实际环境由模型生成的受限计划选择。")
    st.markdown("<div class='agent-card'><div class='agent-tag'>AGENT 能力范围</div><h3>受保护的 Web 任务执行，不是通用万能助手</h3><p>支持：购物、CMS、Reddit、GitLab、地图与 SuiteCRM 环境中的页面读取与动作提交。<br>不支持：真实网站登录、未注册工具调用、绕过 Broker、直接访问原始后端或擅自扩展业务范围。</p></div>", unsafe_allow_html=True)
    st.markdown("### 第 1 步：选择要遵守的法律法规")
    regulation_column, rule_column, spacer = st.columns((2.2, 1, 1.8), gap="medium", vertical_alignment="bottom")
    with regulation_column:
        regulation = st.selectbox(
            "选择要遵守的法律法规",
            options=("请选择法规", "GDPR", "PIPL"),
            label_visibility="collapsed",
        )
    inspection = st.session_state.get("policy_inspection")
    compiled = st.session_state.get("compiled_regulation")
    ready = regulation in {"GDPR", "PIPL"} and compiled == regulation
    with rule_column:
        if ready and st.button("查看规则", width="stretch"):
            _rule_dialog(inspection)
    if regulation in {"GDPR", "PIPL"} and not ready:
        _compile_policy_dialog(regulation)
    if ready:
        st.caption("已完成法规解析。点击“查看规则”可查看原子谓词、形式逻辑与执行控制。")
    model_config = _model_config()
    st.markdown("### 第 3 步：描述你希望 Web Agent 完成的任务")
    selected_example = st.selectbox("任务 Prompt 示例", options=tuple(EXAMPLES), format_func=lambda item: item, label_visibility="collapsed")
    if st.button("填入示例", width="content"):
        st.session_state["task_prompt"] = EXAMPLES[selected_example]
    prompt = st.text_area("任务 Prompt", key="task_prompt", height=116, placeholder="例如：在 GitLab 中查看合并请求，并提交一项受控的代码协作操作。", label_visibility="collapsed")
    st.caption("请勿输入真实个人数据或密钥。演练使用本地 WebArena 风格页面与模拟外部服务。")
    return ((regulation,) if ready else ()), prompt.strip(), model_config


def _result_copy(scenario: str, session: DemoSession) -> tuple[str, str, bool]:
    if session.web_environment:
        repaired = session.result.get("repair_transactions", 0)
        if repaired:
            return "ShieldAgent 已修复并重新核验 Web 动作", f"{session.web_environment} 环境中的原始数据动作已被最小化处理后再执行。", False
        return "ShieldAgent 已安全完成 Web 动作", f"已在 {session.web_environment} 环境完成 Broker 受控的网页动作。", False
    waiting = scenario == "pipl" and any(item["status"] == "WAITING_APPROVAL" for item in session.snapshot.transactions)
    if waiting:
        return "敏感操作已暂停，等待人工决定", "系统尚未发送邮件。批准后会重新核验；拒绝则安全终止。", True
    if scenario == "gdpr":
        return "已阻止原始个人数据外发", "系统将原始客户资料改为汇总统计，并在发送前重新验证。", False
    if session.result.get("operator_decision") == "DENY":
        return "该操作已被拒绝", "敏感信息没有离开受控流程。", False
    return "人工批准后已安全完成", "系统已再次核验后执行了获批准的操作。", False


def _step(number: int, title: str, detail: str) -> str:
    return f"<div class='process-step'><div class='step-dot'>{number}</div><div class='step-copy'><strong>{escape(title)}</strong><small>{escape(detail)}</small></div></div>"


def _render_execution_flow(session: DemoSession) -> None:
    requests = [event.capability_id for event in session.snapshot.events if event.event_type == "CAPABILITY_REQUEST" and event.capability_id]
    unique_requests = list(dict.fromkeys(requests))
    decision = session.snapshot.policy_decision
    planner_detail = f"在线模型 {session.model_plan.model} 生成受限计划：{session.model_plan.explanation}" if session.model_plan else "在线模型未返回可执行计划。"
    normal_steps = [
        ("接收 Web 任务 Prompt", "任务仅在当前会话中处理。"),
        ("生成任务行动计划", planner_detail),
        ("产生动作轨迹", " → ".join(unique_requests) or "未记录能力请求"),
        ("请求受控工具执行", "任务 Agent 无法直接调用外部后端。"),
    ]
    security_steps = [
        ("加载已编译法规规则", "本次运行使用：" + "、".join(session.regulations)),
        ("核验每个能力请求", "先检查数据分类、目的、接收方与副作用。"),
        ("执行干预", f"策略结果：{decision.decision if decision else 'ALLOW'}；控制：{decision.intervention if decision else '无'}"),
        ("记录并验证实际效果", "每次效果都经 Broker 持久化与审计。"),
    ]
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("<section class='track'><div class='track-label'>左侧 · TASK AGENT ACTION TRAJECTORY</div><h3>Web 任务 Agent 的正常执行轨迹</h3>" + "".join(_step(index, *row) for index, row in enumerate(normal_steps, 1)) + "</section>", unsafe_allow_html=True)
    with right:
        st.markdown("<section class='track security'><div class='track-label'>右侧 · SHIELDAGENT SHIELDING TRAJECTORY</div><h3>ShieldAgent 如何保护每个动作</h3>" + "".join(_step(index, *row) for index, row in enumerate(security_steps, 1)) + "</section>", unsafe_allow_html=True)
        _render_shielding_plan(session)


def _render_shielding_plan(session: DemoSession) -> None:
    traces = [
        event.details.get("shielding_plan")
        for event in session.snapshot.events
        if event.details.get("shielding_plan")
    ]
    if not traces:
        st.caption("当前动作没有产生可展示的 Shielding Plan。")
        return
    trace = traces[-1]
    st.markdown("#### 本次动作的 Shielding Plan")
    st.caption("由实际运行时审计生成；规则权重尚未训练，使用确定性 fail-closed 形式化核验。")
    for operation in trace.get("operations", []):
        st.markdown(f"`{operation['status']}` · **{operation['operation']}**：{operation['detail']}")
    for circuit in trace.get("circuits", []):
        with st.expander(f"{circuit['rule_id']} · {circuit['verification']}"):
            st.code(circuit["formula"], language=None)
            st.dataframe(
                [
                    {
                        "符号": assignment["symbol"],
                        "运行时变量": assignment["variable"],
                        "真值": assignment["truth_value"],
                        "角色": assignment["role"],
                    }
                    for assignment in circuit["assignments"]
                ],
                width="stretch",
                hide_index=True,
            )
            st.caption("法规来源：" + "、".join(circuit["source_articles"]))


def _render_result(scenario: str, session: DemoSession) -> None:
    title, text, waiting = _result_copy(scenario, session)
    st.markdown(f"<section class='result{' waiting' if waiting else ''}'><h2>{escape(title)}</h2><p>{escape(text)}</p></section>", unsafe_allow_html=True)
    if scenario == "pipl" and not session.web_environment and waiting:
        st.markdown("### 需要你的决定")
        approve, deny = st.columns(2)
        if approve.button("批准并重新核验", type="primary", width="stretch"):
            try:
                with st.spinner("正在重新核验…"):
                    resolve_pipl_approval(session, "approve")
                st.rerun()
            except Exception as exc:
                st.error(f"审批失败：{type(exc).__name__}: {exc}")
        if deny.button("拒绝这次操作", width="stretch"):
            try:
                resolve_pipl_approval(session, "deny")
                st.rerun()
            except Exception as exc:
                st.error(f"拒绝失败：{type(exc).__name__}: {exc}")
    values = (("Web 环境", session.web_environment), ("受控网页动作", f"{session.result.get('web_actions', 0)} 次"), ("ShieldAgent 复核", "已完成")) if session.web_environment else (("原始个人数据外发", "0 次"), ("安全汇总外发", f"{session.result.get('aggregate_messages', 0)} 次"), ("发送前重新核验", "通过")) if scenario == "gdpr" else (("人工决定", session.result.get("operator_decision", "等待审批")), ("实际邮件效果", f"{session.result.get('email_messages_after_decision', 0)} 次"), ("策略复核", "已完成" if not waiting else "等待人工决定"))
    columns = st.columns(3)
    for column, (label, value) in zip(columns, values):
        column.markdown(f"<div class='metric-card'><div class='metric-label'>{escape(label)}</div><div class='metric-value'>{escape(value)}</div></div>", unsafe_allow_html=True)


st.markdown("""<section class="hero"><div class="eyebrow">SHIELDAGENT · WEB AGENT RUNTIME GUARDRAIL</div><h1>让 Web 任务 Agent 在每个网页动作前获得保护。</h1><p>任务模型在 Shopping、CMS、Reddit、GitLab、Maps 或 SuiteCRM 环境中生成动作轨迹；ShieldAgent 检索动作规则电路、赋值原子谓词、执行形式化核验，并在页面读取、外部提交、记忆写入与响应发布前实施防护。</p><div class="hero-badge">动作轨迹治理 · 法规规则电路 · 真实 Broker 执行</div></section>""", unsafe_allow_html=True)

regulations, prompt, model_config = _render_setup()
scenario = _scenario(regulations[0]) if regulations else "gdpr"
signature = (regulations, prompt, bool(model_config), model_config.model if model_config else "", model_config.base_url if model_config else "")
if st.session_state.get("run_signature") not in (None, signature):
    _close_previous()

run_column, hint_column = st.columns((1.35, 3.65), vertical_alignment="center")
with run_column:
    run = st.button("安全执行", type="primary", width="stretch", disabled=not (prompt and regulations and model_config))
with hint_column:
    if not regulations:
        st.caption("请先完成第 1 步：选择法规。系统会自动解析并编译对应的运行时规则。")
    elif not model_config:
        st.caption("请完成第 2 步：填写 API Key、模型名称和 API 地址。配置完成后才能在线安全执行。")
    elif not prompt:
        st.caption("请完成第 3 步：输入或填入一段任务 Prompt。")
    else:
        st.caption("已满足执行条件：在线模型先生成受限行动计划，再由 AgentShield Broker 按所选法规逐项核验。")

if run:
    _close_previous()
    try:
        with st.spinner("Agent 正在规划任务，AgentShield 正在加载规则并受控执行…"):
            session = run_demo(scenario, task_prompt=prompt, regulations=regulations, model_config=model_config, web_task=True)
        st.session_state["demo_session"] = session
        st.session_state["run_signature"] = signature
        st.rerun()
    except ModelPlanningError as exc:
        st.error(f"模型计划未通过安全格式核验：{exc}")
        st.info("请确认模型名称正确；可先点击“测试 API 连接”。若服务商会附加推理或 Markdown，系统现已自动兼容常见格式，但不会接受缺少 route / explanation 字段或超出 Agent 范围的计划。")
    except Exception as exc:
        st.error(f"安全执行未完成：{type(exc).__name__}: {exc}")

session = st.session_state.get("demo_session")
if isinstance(session, DemoSession):
    st.markdown("---")
    st.markdown("## 本次安全执行结果")
    st.caption(f"任务 Prompt：{session.task_prompt}")
    _render_result(scenario, session)
    st.markdown("### 执行过程：业务路径与治理路径")
    _render_execution_flow(session)
    with st.expander("查看数据状态、策略决定与审计证据", expanded=False):
        data_column, decision_column = st.columns(2, gap="large")
        with data_column:
            render_state(session.snapshot)
        with decision_column:
            render_decision(session.snapshot)
        render_lineage(session.snapshot)
        execution_column, audit_column = st.columns((2, 3), gap="large")
        with execution_column:
            render_effects(session.snapshot)
        with audit_column:
            render_audit(session.snapshot)
else:
    st.markdown("---")
    st.markdown("### 安全执行会做什么？")
    one, two, three = st.columns(3)
    for column, title, text in ((one, "1 · 受限规划", "大模型只能为固定能力范围生成行动计划。"), (two, "2 · 逐项核验", "每个数据读取与外部效果都必须通过法规规则。"), (three, "3 · 可审计结果", "系统记录采取的控制与真实执行结果。")):
        column.markdown(f"<div class='agent-card'><div class='agent-tag'>{title}</div><p>{text}</p></div>", unsafe_allow_html=True)

st.markdown("---")
st.caption("本地演练使用合成数据与模拟效果。AgentShield 提供技术控制，不构成法律意见或完整合规保证。")
