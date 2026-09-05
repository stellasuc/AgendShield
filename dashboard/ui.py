"""用户可操作的企业客户服务 Agent 工作台。"""

from __future__ import annotations

from html import escape
import json
import os
from pathlib import Path
import time

import streamlit as st

from agentshield.planning import (
    MODEL_PROVIDERS,
    ModelConfig,
    ModelPlanningError,
    model_provider,
    verify_model_connection,
)
from agentshield.integrations.awm_webarena import (
    AWMWebArenaConfig,
    AWMWebArenaRunner,
    awm_runtime_ready,
    default_awm_python,
)
from agentshield.integrations.upstreams import inspect_upstreams
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
from examples.web_task_agent.brokered import infer_environment
from examples.web_task_agent.shopping import storefront_snapshot


AGENT_NAME = "AWM Web Task Agent + ShieldAgent"
EXAMPLES = {
    "购物站任务（推荐）": "在购物网站中寻找预算不超过 600 元的降噪耳机，选择评分最高的一款加入购物车，不要下单。",
    "内容管理任务": "在 CMS 中查看季度更新草稿，并提交一项受控的发布准备操作。",
    "社区任务": "在 Reddit 风格社区查看支持帖子，并提交一项受控的跟进操作。",
    "代码协作任务": "在 GitLab 中查看合并请求，并提交一项受控的代码协作操作。",
    "地图任务": "在地图服务中查看地点信息，并提交一项受控的路线规划操作。",
    "CRM 任务": "在 SuiteCRM 中查看客户记录，并提交一项受控的后续处理操作。",
}

WEB_TARGETS = {
    "shopping": ("SHOPPING", "shopping"),
    "cms": ("SHOPPING_ADMIN", "shopping_admin"),
    "reddit": ("REDDIT", "reddit"),
    "gitlab": ("GITLAB", "gitlab"),
    "maps": ("MAP", "map"),
}

# The recommended deployment keeps the protected WebArena Shopping container on
# the same host as AgentShield. Administrators can override every address with
# an environment variable or in the current Streamlit session.
DEFAULT_WEBARENA_URLS = {
    "SHOPPING": "http://127.0.0.1:7770",
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
    .visualization-intro{border:1px solid #cde5df;border-radius:16px;background:linear-gradient(115deg,#f1fbf8,#f8fbff);padding:1.15rem 1.2rem;margin:.1rem 0 1rem}.visualization-intro h3{font-size:1.1rem;color:#172033;margin:.15rem 0 .35rem}.visualization-intro>p{margin:0;color:#526579;font-size:.9rem;line-height:1.55}.visualization-flow{display:grid;grid-template-columns:1fr 72px 1fr 72px 1fr;align-items:center;gap:.45rem;margin-top:.95rem}.visualization-node{border:1px solid #d7e4ec;border-radius:11px;background:#fff;padding:.7rem .75rem;min-height:76px}.visualization-node strong{display:block;color:#172033;font-size:.86rem;margin-bottom:.18rem}.visualization-node span{color:#64748b;font-size:.75rem;line-height:1.35}.visualization-node.shield{border-color:#9ddbcf;background:#f0fbf8}.visualization-arrow{text-align:center;color:#0f766e;font-weight:900;font-size:.78rem}@media(max-width:800px){.visualization-flow{grid-template-columns:1fr;gap:.3rem}.visualization-arrow{transform:rotate(90deg);height:25px}.visualization-node{min-height:auto}}
    .result {border-radius:16px;padding:1.15rem 1.3rem;margin:1rem 0;border:1px solid #a7ded3;background:#effbf8;}.result.waiting {border-color:#f5c77e;background:#fff8e9;}.result h2 {font-size:1.3rem;margin:0 0 .35rem;color:#13453e;}.result.waiting h2 {color:#754b00;}.result p {margin:0;color:#4b5e6d;line-height:1.5;}
    .metric-card {border:1px solid #e2e8f0;border-radius:13px;padding:.85rem .95rem;background:#fbfdff;}.metric-label {font-size:.78rem;font-weight:700;color:#64748b;}.metric-value {font-size:1.18rem;font-weight:800;color:#172033;margin-top:.18rem;}
    .mapping-source{border:1px solid #cfe0f2;border-left:4px solid #3b82f6;border-radius:12px;background:#f7fbff;padding:.85rem 1rem}.mapping-kicker{font-size:.69rem;font-weight:900;letter-spacing:.07em;color:#2563eb;margin-bottom:.3rem}.mapping-title{font-size:.9rem;font-weight:750;color:#1e293b;line-height:1.5}.mapping-meta{font-size:.72rem;color:#64748b;margin-top:.38rem}.mapping-meta a{color:#2563eb;text-decoration:none}.mapping-arrow{text-align:center;color:#64748b;font-size:.73rem;font-weight:800;padding:.55rem 0}
    .store-shell {border:1px solid #dce3ec;border-radius:18px;background:#f8fafc;overflow:hidden;margin:.65rem 0 1rem;box-shadow:0 8px 24px rgba(15,23,42,.06);}.store-top {display:flex;justify-content:space-between;align-items:center;padding:.85rem 1rem;background:#111827;color:#fff;}.store-brand {font-size:1rem;font-weight:900;letter-spacing:.04em}.store-meta {font-size:.78rem;color:#cbd5e1}.store-search {margin:.9rem 1rem;padding:.68rem .8rem;background:#fff;border:1px solid #d8e0ea;border-radius:10px;color:#475569;font-size:.86rem}.product-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.75rem;padding:0 1rem 1rem}.product-card {position:relative;background:#fff;border:1px solid #e2e8f0;border-radius:13px;padding:.9rem;min-height:154px}.product-card.selected {border:2px solid #0f766e;background:#f0fdfa}.product-category {font-size:.7rem;font-weight:800;color:#0f766e;letter-spacing:.08em}.product-title {font-size:.92rem;font-weight:800;color:#172033;margin:.35rem 0;line-height:1.35}.product-desc {font-size:.76rem;color:#64748b;line-height:1.4}.product-bottom {display:flex;justify-content:space-between;align-items:end;margin-top:.65rem}.product-price {font-size:1.05rem;font-weight:900;color:#b45309}.product-rating {font-size:.75rem;color:#64748b}.selected-tag {position:absolute;right:.6rem;top:.55rem;background:#0f766e;color:#fff;border-radius:999px;padding:.16rem .42rem;font-size:.66rem;font-weight:800}.cart-bar {margin:0 1rem 1rem;padding:.75rem .85rem;border-radius:11px;background:#ecfdf5;border:1px solid #a7f3d0;color:#065f46;font-size:.84rem}.order-bar {margin:0 1rem 1rem;padding:.75rem .85rem;border-radius:11px;background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;font-size:.84rem}.env-note {font-size:.78rem;color:#64748b;padding:0 1rem 1rem}@media(max-width:800px){.product-grid{grid-template-columns:1fr}.store-top{align-items:flex-start;gap:.35rem;flex-direction:column}}
    .execution-board {border:1px solid #dce5ee;border-radius:18px;background:#f8fafc;overflow:hidden;margin:.75rem 0 1rem;box-shadow:0 10px 28px rgba(15,23,42,.06)}
    .execution-status {display:flex;align-items:center;gap:.55rem;padding:.72rem 1rem;border-bottom:1px solid #dce5ee;background:#fff;color:#475569;font-size:.82rem}.execution-status strong{color:#172033}.live-pulse{width:.55rem;height:.55rem;border-radius:50%;background:#10b981;box-shadow:0 0 0 0 rgba(16,185,129,.45);animation:pulse 1.45s infinite}.execution-status.complete .live-pulse{animation:none;box-shadow:none}@keyframes pulse{70%{box-shadow:0 0 0 7px rgba(16,185,129,0)}100%{box-shadow:0 0 0 0 rgba(16,185,129,0)}}
    .lane-heads,.execution-pair {display:grid;grid-template-columns:minmax(0,1fr) 116px minmax(0,1fr);gap:.8rem}.lane-heads{padding:1rem 1rem .45rem}.lane-title{display:flex;align-items:center;gap:.6rem}.lane-title.right{grid-column:3}.lane-icon{height:2rem;width:2rem;border-radius:9px;display:flex;align-items:center;justify-content:center;background:#e8f1fb;color:#14507a;font-weight:900}.lane-title.right .lane-icon{background:#dff5ee;color:#08736a}.lane-name{font-size:.96rem;font-weight:900;color:#172033}.lane-sub{font-size:.72rem;color:#64748b;margin-top:.06rem}
    .execution-list{padding:.35rem 1rem 1.1rem}.execution-pair{position:relative;align-items:stretch;padding:.42rem 0}.execution-pair:not(:last-child){margin-bottom:1.05rem}.execution-pair:not(:last-child)::after{content:'↓  下一步';position:absolute;left:50%;bottom:-1.16rem;transform:translateX(-50%);font-size:.68rem;font-weight:800;color:#94a3b8;background:#f8fafc;padding:0 .4rem;z-index:2}
    .agent-node,.shield-node{position:relative;border-radius:13px;padding:.84rem .9rem;background:#fff;border:1px solid #dbe5ef;min-height:96px}.agent-node{border-left:4px solid #3b82f6}.shield-node{border-left:4px solid #10b981;background:#f3fbf8}.execution-pair.pending .shield-node{border-left-color:#f59e0b;background:#fffbeb}.execution-pair.block .shield-node{border-left-color:#ef4444;background:#fff7f7}.execution-pair.repair .shield-node{border-left-color:#8b5cf6;background:#faf8ff}.node-top{display:flex;justify-content:space-between;align-items:center;gap:.5rem;margin-bottom:.3rem}.node-step{font-size:.68rem;font-weight:900;letter-spacing:.06em;color:#2563eb}.shield-node .node-step{color:#08736a}.node-state{font-size:.65rem;font-weight:900;padding:.15rem .42rem;border-radius:999px;background:#dcfce7;color:#166534}.pending .node-state{background:#fef3c7;color:#92400e}.block .node-state{background:#fee2e2;color:#991b1b}.repair .node-state{background:#ede9fe;color:#6d28d9}.node-title{font-size:.9rem;font-weight:850;color:#172033;line-height:1.35}.node-detail{font-size:.75rem;color:#64748b;line-height:1.45;margin-top:.27rem}.handoff{display:flex;flex-direction:column;justify-content:center;gap:.42rem;color:#64748b}.arrow-line{display:flex;align-items:center;gap:.32rem;font-size:.63rem;font-weight:800;white-space:nowrap}.arrow-line::before,.arrow-line::after{content:'';height:1px;background:#94a3b8;flex:1}.arrow-line.out{color:#2563eb}.arrow-line.back{color:#059669;flex-direction:row-reverse}.pending .arrow-line.back{color:#d97706}.block .arrow-line.back{color:#dc2626}.arrow-symbol{font-size:1.15rem;line-height:1}.board-empty{padding:1.1rem;color:#64748b;font-size:.84rem}
    @media(max-width:800px){.lane-heads{display:none}.execution-pair{grid-template-columns:1fr;gap:.45rem}.handoff{min-height:42px}.arrow-line{justify-content:center}.arrow-line::before,.arrow-line::after{max-width:70px}.arrow-line.out .arrow-symbol{transform:rotate(90deg)}.arrow-line.back{display:none}.execution-pair:not(:last-child)::after{display:none}}
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
    st.session_state.pop("upstream_result", None)


def _scenario(regulation: str) -> str:
    return "pipl" if regulation == "PIPL" else "gdpr"


INTERVENTION_LABELS = {
    "AUDIT_ONLY": "记录审计",
    "REPLAN": "要求重新规划",
    "REDACT": "自动脱敏",
    "AGGREGATE": "转换为汇总数据",
    "REQUIRE_CONSENT": "要求用户同意",
    "REQUIRE_APPROVAL": "要求人工审批",
    "PREVENT_MEMORY_WRITE": "禁止写入记忆",
    "BLOCK": "阻止执行",
}

LIFECYCLE_LABELS = {
    "DATA_ACCESS": "读取数据时",
    "TOOL_CALL": "调用工具时",
    "EXTERNAL_TRANSFER": "向外部发送时",
    "RESPONSE_GENERATED": "生成回答时",
    "MEMORY_WRITE": "写入记忆时",
    "LOG_WRITE": "写入日志时",
}


def _humanized_intervention(intervention: str) -> str:
    return INTERVENTION_LABELS.get(intervention, intervention.replace("_", " ").title())


def _humanized_stages(stages: tuple[str, ...]) -> str:
    return "、".join(LIFECYCLE_LABELS.get(stage, stage) for stage in stages)


def _render_rule_content(inspection) -> None:
    requirement_ids = {item.requirement_id for item in inspection.requirements}
    linked_rule_ids = {
        rule.rule_id
        for rule in inspection.rules
        if requirement_ids.intersection(rule.requirement_ids)
    }
    summary_a, summary_b, summary_c = st.columns(3)
    summary_a.metric("法规要求", len(inspection.requirements))
    summary_b.metric("运行时规则", len(inspection.rules))
    summary_c.metric("映射覆盖", f"{len(linked_rule_ids)}/{len(inspection.rules)}")
    st.caption("点击任一法规要求，即可沿着“法规条款 → 工程解释 → 符号规则 → 执行控制”查看完整对应关系。")

    for requirement_index, requirement in enumerate(inspection.requirements, 1):
        matched_rules = [
            rule
            for rule in inspection.rules
            if requirement.requirement_id in rule.requirement_ids
        ]
        rule_count = f"{len(matched_rules)} 条运行时规则" if matched_rules else "尚无运行时规则"
        with st.expander(
            f"{requirement_index}. {requirement.article} · {rule_count}",
            expanded=requirement_index == 1,
        ):
            st.markdown(
                f"<div class='mapping-source'><div class='mapping-kicker'>法规要求 · {escape(requirement.requirement_id)}</div>"
                f"<div class='mapping-title'>{escape(requirement.legal_requirement)}</div>"
                f"<div class='mapping-meta'>来源：{escape(requirement.article)} · <a href='{escape(requirement.source_url)}' target='_blank'>查看官方条文</a></div></div>",
                unsafe_allow_html=True,
            )
            st.markdown("<div class='mapping-arrow'>↓　转译为可执行的工程含义</div>", unsafe_allow_html=True)
            interpretation_column, enforcement_column = st.columns(2, gap="medium")
            with interpretation_column:
                st.markdown("**系统需要理解什么**")
                st.write(requirement.engineering_interpretation)
            with enforcement_column:
                st.markdown("**系统需要采取什么控制**")
                st.write(requirement.runtime_enforcement)
            st.caption("可能触发的执行阶段：" + _humanized_stages(requirement.lifecycle_stages))
            st.markdown(
                f"<div class='mapping-arrow'>↓　拆分并编译为 {len(matched_rules)} 条符号化运行时规则</div>",
                unsafe_allow_html=True,
            )
            if not matched_rules:
                st.warning("这条法规要求当前没有对应的可执行规则，不能进入安全执行。")
                continue
            for rule_index, rule in enumerate(matched_rules, 1):
                with st.container(border=True):
                    title_column, control_column = st.columns((3.4, 1.3), vertical_alignment="center")
                    with title_column:
                        st.markdown(f"**规则 {rule_index} · `{rule.rule_id}`**")
                        st.write(rule.description)
                    with control_column:
                        st.caption("不满足时")
                        st.markdown(f"**{_humanized_intervention(rule.intervention)}**")
                    st.caption("检查时机：" + _humanized_stages(rule.lifecycle_stages))
                    st.markdown("**机器执行的布尔公式**")
                    st.code(rule.formal_logic, language=None)
                    st.dataframe(
                        [
                            {
                                "检查类型": item.role,
                                "布尔符号": item.symbol,
                                "运行时证据": item.source_variable,
                                "必须满足": item.expected_value,
                            }
                            for item in rule.predicates
                        ],
                        width="stretch",
                        hide_index=True,
                    )
            st.caption("执行时，ShieldAgent 会为上述谓词赋予 TRUE / FALSE，并据此决定允许、修复、审批或阻断。")


@st.dialog("正在加载审核后的法规规则包", width="small")
def _compile_policy_dialog(regulation: str) -> None:
    progress = st.progress(5, text="读取审核后的法规映射包…")
    time.sleep(0.12)
    progress.progress(35, text="验证来源、要求与规则关联…")
    inspection = inspect_policy((regulation,))
    time.sleep(0.12)
    progress.progress(75, text="加载已批准的原子谓词与运行时规则…")
    time.sleep(0.12)
    progress.progress(100, text="规则包就绪")
    st.session_state["policy_inspection"] = inspection
    st.session_state["compiled_regulation"] = regulation
    time.sleep(0.35)
    st.rerun()


@st.dialog("法规要求与运行时控制", width="large")
def _rule_dialog(inspection) -> None:
    _render_rule_content(inspection)


def _model_config(execution_backend: str = "fixture") -> ModelConfig | None:
    config: ModelConfig | None = None
    with st.expander("第 2 步：配置在线模型连接（必填）", expanded=True):
        if execution_backend == "paper":
            st.caption("AWM 会在每个 WebArena 步骤调用该模型生成 BrowserGym 动作；动作仍须先通过 ShieldAgent。未配置 API Key 时不能执行。")
        else:
            st.caption("本地回归夹具使用该模型生成固定 Schema 行动计划；计划和每个动作都受 AgentShield 限制。")
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
        st.caption("点击“安全执行”后，任务 Prompt 与 Agent 能力说明将发送至该端点；模型输出不能绕过 ShieldAgent。")
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


def _render_shopping_environment(environment_state: dict | None = None) -> None:
    state = environment_state or {
        "storefront": storefront_snapshot(),
        "selected_product": None,
        "cart": {"items": [], "item_count": 0, "total": 0.0, "currency": "CNY"},
        "order": None,
    }
    storefront = state.get("storefront") or storefront_snapshot()
    selected = state.get("selected_product") or {}
    cart = state.get("cart") or {"items": [], "item_count": 0, "total": 0.0}
    cards = []
    for product in storefront.get("items", []):
        is_selected = product.get("product_id") == selected.get("product_id")
        cards.append(
            "<article class='product-card{selected_class}'>"
            "{selected_tag}<div class='product-category'>{category}</div>"
            "<div class='product-title'>{title}</div><div class='product-desc'>{description}</div>"
            "<div class='product-bottom'><div class='product-price'>¥{price:.2f}</div>"
            "<div class='product-rating'>★ {rating} · {reviews} 条评价<br>库存 {stock}</div></div></article>".format(
                selected_class=" selected" if is_selected else "",
                selected_tag="<span class='selected-tag'>AGENT 已选择</span>" if is_selected else "",
                category=escape(str(product.get("category", "商品"))),
                title=escape(str(product.get("product", ""))),
                description=escape(str(product.get("description", ""))),
                price=float(product.get("price", 0)),
                rating=escape(str(product.get("rating", "-"))),
                reviews=escape(str(product.get("reviews", 0))),
                stock=escape(str(product.get("stock", 0))),
            )
        )
    query = storefront.get("query") or "全部商品"
    budget = "不限" if storefront.get("max_price") is None else f"¥{float(storefront['max_price']):.2f}"
    order = state.get("order")
    order_html = ""
    if order:
        order_html = (
            f"<div class='order-bar'><strong>模拟订单 {escape(str(order['order_id']))}</strong> · "
            f"总额 ¥{float(order['total']):.2f} · 状态：仅本地记录，未扣款</div>"
        )
    st.markdown(
        "<section class='store-shell'><div class='store-top'><div class='store-brand'>NORTHSTAR MARKET</div>"
        "<div class='store-meta'>本地 WebArena 风格环境 · 不连接真实支付</div></div>"
        f"<div class='store-search'>🔎 {escape(str(query))}　预算：{escape(budget)}　·　找到 {len(cards)} 件商品</div>"
        f"<div class='product-grid'>{''.join(cards)}</div>"
        f"<div class='cart-bar'><strong>购物车</strong> · {int(cart.get('item_count', 0))} 件商品 · 合计 ¥{float(cart.get('total', 0)):.2f}</div>"
        f"{order_html}<div class='env-note'>页面观察同时生成 HTML 与 accessibility tree；Agent 只能通过 Capability Broker 读取页面和修改购物车。</div></section>",
        unsafe_allow_html=True,
    )


def _render_stack_selector() -> tuple[str, dict[str, str]]:
    statuses = inspect_upstreams()
    st.markdown(
        "<section class='visualization-intro'><div class='agent-tag'>这个工作台展示什么</div>"
        "<h3>把一次网页 Agent 的安全执行过程变得看得见。</h3>"
        "<p>输入任务、选择需要遵守的法规后，系统会逐步展示任务 Agent 提议的每个网页动作，"
        "以及 ShieldAgent 在动作真正执行前如何检查规则、要求修复或阻止风险操作。</p>"
        "<div class='visualization-flow'>"
        "<div class='visualization-node'><strong>1. 任务 Agent 提议动作</strong><span>例如搜索商品、读取页面或加入购物车</span></div>"
        "<div class='visualization-arrow'>→</div>"
        "<div class='visualization-node shield'><strong>2. ShieldAgent 前置检查</strong><span>将法规规则应用到当前动作和页面证据</span></div>"
        "<div class='visualization-arrow'>→</div>"
        "<div class='visualization-node'><strong>3. 放行、修复或阻止</strong><span>结果会同步呈现在下方左右两条轨迹中</span></div>"
        "</div></section>",
        unsafe_allow_html=True,
    )
    with st.expander("管理员设置：连接演示网站与查看复现信息", expanded=False):
        st.caption("普通使用者无需理解这些配置。仅在部署 WebArena 演示网站或复现实验时填写。")
        mode = st.radio(
            "运行环境",
            options=("paper", "fixture"),
            format_func=lambda value: (
                "在线演示环境（推荐）"
                if value == "paper"
                else "开发验证环境（不面向演示）"
            ),
            horizontal=True,
            key="execution_backend",
        )
        if mode == "paper":
            st.markdown("#### 连接已部署的演示网站")
            st.caption("Shopping 已按同机部署方式提供默认地址。其他地址可以通过服务器环境变量预设，也可以仅在当前浏览器会话中填写。")
            labels = {
                "SHOPPING": "购物网站",
                "SHOPPING_ADMIN": "内容管理网站",
                "REDDIT": "社区网站",
                "GITLAB": "代码协作网站",
                "MAP": "地图网站",
            }
            urls = {
                variable: st.text_input(
                    f"{labels[variable]}（{variable}）",
                    value=os.environ.get(variable, DEFAULT_WEBARENA_URLS.get(variable, "")),
                    placeholder="http://已部署的网站地址",
                    key=f"webarena_url_{variable.lower()}",
                ).strip()
                for variable in labels
            }
        else:
            urls = {}
            st.warning("开发验证环境只用于验证 ShieldAgent，不使用真实网页任务 Agent 或演示网站。")

        st.markdown("#### 复现组件状态")
        columns = st.columns(3)
        for column, status in zip(columns, statuses):
            label = "版本已锁定" if status.ready else "未就绪"
            column.metric(status.project.display_name, label)
            column.caption(f"{status.project.license} · {status.detail}")
        st.caption("AWM 提供被保护的网页任务 Agent，WebArena 提供开源网页环境；本项目实现并可视化 ShieldAgent 的动作前防护。")
    return mode, urls


def _render_setup() -> tuple[tuple[str, ...], str, ModelConfig | None, str, dict[str, str]]:
    st.markdown("## 配置一次安全执行")
    st.caption("完成以下三项后即可在线执行。执行时，下方会以左右对照的方式展示“任务 Agent 正常轨迹”与“ShieldAgent 防护轨迹”。")
    execution_backend, webarena_urls = _render_stack_selector()
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
        st.caption("已加载审核后的法规规则包。点击“查看规则”可查看来源、原子谓词、形式逻辑与执行控制；AutoPolicy 的 LLM 抽取候选不会在未审核时直接激活。")
    model_config = _model_config(execution_backend)
    st.markdown("### 第 3 步：描述你希望 Web Agent 完成的任务")
    selected_example = st.selectbox("任务 Prompt 示例", options=tuple(EXAMPLES), format_func=lambda item: item, label_visibility="collapsed")
    if st.button("填入示例", width="content"):
        st.session_state["task_prompt"] = EXAMPLES[selected_example]
    prompt = st.text_area("任务 Prompt", key="task_prompt", height=116, placeholder="例如：在 GitLab 中查看合并请求，并提交一项受控的代码协作操作。", label_visibility="collapsed")
    st.caption("请勿输入真实个人数据或密钥。论文同源模式会把 Prompt 作为 BrowserGym openended goal，起始页限定到对应 WebArena 站点。")
    return ((regulation,) if ready else ()), prompt.strip(), model_config, execution_backend, webarena_urls


def _paper_target(prompt: str, urls: dict[str, str]) -> tuple[str, str, str] | None:
    environment = infer_environment(prompt)
    target = WEB_TARGETS.get(environment)
    if target is None:
        return None
    variable, workflow = target
    url = urls.get(variable, "").strip()
    return environment, workflow, url


def _paper_pairs(result: dict[str, object]) -> list[dict[str, str]]:
    trace_path = Path(str(result.get("shield_trace_path", "")))
    if not trace_path.is_file():
        return []
    pairs = []
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        decision = str(item.get("decision", "BLOCK"))
        names = ", ".join(item.get("action_names") or ()) or "无法解析的动作"
        state = "ALLOW" if item.get("allowed") else ("REPAIR" if decision == "REPLAN" else "BLOCK")
        pairs.append({
            "agent_title": f"AWM 提议：{names}",
            "agent_detail": f"动作指纹 {str(item.get('action_sha256', ''))[:16]}…；原始载荷不写入审计",
            "shield_title": f"ShieldAgent：{decision}",
            "shield_detail": str(item.get("explanation") or "已完成规则电路核验"),
            "state": state,
            "return_label": "允许进入 WebArena" if item.get("allowed") else "反馈 AWM 重新规划",
        })
    return pairs


def _result_copy(scenario: str, session: DemoSession) -> tuple[str, str, bool]:
    if session.web_environment:
        if session.web_environment == "shopping":
            action = session.result.get("task_action")
            if action == "place_order":
                return "本地模拟订单已通过安全执行", "订单仅写入本地 Broker 后端，没有连接支付系统或产生真实扣款。", False
            if action == "add_to_cart":
                return "商品已安全加入本地购物车", "Agent 完成了检索、预算过滤、商品选择和受控购物车修改；没有提交订单。", False
            return "商品检索已安全完成", "Agent 读取了真实本地商品目录并完成筛选，没有产生购物车或订单副作用。", False
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


def _action_copy(capability: str, arguments: dict) -> tuple[str, str]:
    page = arguments.get("page")
    action = arguments.get("action")
    if capability == "web.page.read" and page == "search":
        query = arguments.get("query") or "全部商品"
        budget = arguments.get("max_price")
        detail = f"搜索“{query}”" + (f"，预算不超过 ¥{float(budget):.2f}" if budget else "")
        return "读取商品搜索页", detail
    if capability == "web.page.read" and page == "product":
        return "读取候选商品详情", f"查看商品 {arguments.get('product_id') or '候选项'} 的页面信息"
    if capability == "web.action.submit" and action == "add_to_cart":
        return "将选中商品加入购物车", f"数量 {arguments.get('quantity', 1)}，通过受控 Web 能力提交"
    if capability == "web.action.submit" and action == "place_order":
        return "提交本地模拟订单", "仅创建演示订单，不连接支付或产生真实扣款"
    if capability == "response.release":
        return "发布任务结果", "在返回用户之前提交最终响应检查"
    if capability == "web.page.read":
        return "读取 Web 页面", f"页面：{page or 'home'}"
    if capability == "web.action.submit":
        return "提交网页动作", f"动作：{action or '完成用户任务'}"
    return "请求受控能力", capability


def _shield_copy(trace: dict, events=()) -> tuple[str, str, str, str]:
    decision = str(trace.get("decision") or "ALLOW").upper()
    status = str(trace.get("status") or "SUCCEEDED").upper()
    shielding = next(
        (event.details.get("shielding_plan") for event in events if event.details.get("shielding_plan")),
        None,
    )
    circuit_count = len(shielding.get("circuits", [])) if shielding else 0
    predicate_count = sum(
        len(circuit.get("assignments", []))
        for circuit in (shielding.get("circuits", []) if shielding else [])
    )
    if decision == "REPAIR":
        title, state, return_label = "发现风险并执行最小化修复", "REPAIR", "修复后继续"
    elif decision in {"REQUIRE_APPROVAL", "REQUIRE_CONSENT"}:
        title, state, return_label = "需要人工授权后才能继续", "PENDING", "等待授权"
    elif decision in {"BLOCK", "DENIED"} or status != "SUCCEEDED":
        title, state, return_label = "阻断不合规动作", "BLOCK", "已阻断"
    else:
        title, state, return_label = "法规规则核验通过", "ALLOW", "允许继续"
    facts = []
    if circuit_count:
        facts.append(f"核验 {circuit_count} 个规则电路、{predicate_count} 个原子谓词")
    facts.append(f"策略裁决 {decision}")
    facts.append("执行已审计" if status == "SUCCEEDED" else f"执行状态 {status}")
    return title, " · ".join(facts), state, return_label


def _planning_pair(session: DemoSession) -> dict:
    if session.model_plan:
        agent_detail = (
            f"{session.model_plan.model} 生成 {session.model_plan.environment} / "
            f"{session.model_plan.task_action} 受限计划：{session.model_plan.explanation}"
        )
    else:
        agent_detail = "本地测试解释器生成固定能力范围内的行动计划。"
    return {
        "agent_title": "理解任务并生成行动计划",
        "agent_detail": agent_detail,
        "shield_title": "锁定法规与 Agent 能力边界",
        "shield_detail": "加载 " + "、".join(session.regulations) + " 规则；禁止未注册工具、越权环境与未确认下单",
        "state": "ALLOW",
        "return_label": "计划可执行",
    }


def _execution_pairs(session: DemoSession) -> list[dict]:
    pairs = [_planning_pair(session)]
    events_by_transaction: dict[str, list] = {}
    for event in session.snapshot.events:
        if event.transaction_id:
            events_by_transaction.setdefault(event.transaction_id, []).append(event)
    traces = list(session.result.get("tool_trace", []))
    traced_transactions = {str(item.get("transaction_id")) for item in traces}
    for event in session.snapshot.events:
        if (
            event.event_type == "CAPABILITY_REQUEST"
            and event.transaction_id
            and event.transaction_id not in traced_transactions
        ):
            traces.append(
                {
                    "capability": event.capability_id or "runtime.action",
                    "transaction_id": event.transaction_id,
                    "status": "SUCCEEDED",
                    "decision": next(
                        (
                            item.decision
                            for item in events_by_transaction[event.transaction_id]
                            if item.decision
                        ),
                        "ALLOW",
                    ),
                    "arguments": {},
                }
            )
            traced_transactions.add(event.transaction_id)
    for trace in traces:
        capability = str(trace.get("capability") or "runtime.action")
        agent_title, agent_detail = _action_copy(capability, dict(trace.get("arguments") or {}))
        related = events_by_transaction.get(str(trace.get("transaction_id")), [])
        shield_title, shield_detail, state, return_label = _shield_copy(trace, related)
        pairs.append(
            {
                "agent_title": agent_title,
                "agent_detail": agent_detail,
                "shield_title": shield_title,
                "shield_detail": shield_detail,
                "state": state,
                "return_label": return_label,
            }
        )
    return pairs


def _process_board_html(pairs: list[dict], *, complete: bool) -> str:
    rows = []
    for index, pair in enumerate(pairs, 1):
        state = str(pair.get("state") or "PENDING").upper()
        css_state = {"PENDING": "pending", "BLOCK": "block", "REPAIR": "repair"}.get(state, "allow")
        state_label = {"PENDING": "检查中", "ALLOW": "已通过", "BLOCK": "已阻断", "REPAIR": "已修复"}.get(state, state)
        rows.append(
            f"<div class='execution-pair {css_state}'>"
            f"<div class='agent-node'><div class='node-top'><span class='node-step'>执行第 {index} 步</span><span class='node-state'>已发起</span></div>"
            f"<div class='node-title'>{escape(str(pair['agent_title']))}</div><div class='node-detail'>{escape(str(pair['agent_detail']))}</div></div>"
            f"<div class='handoff'><div class='arrow-line out'><span>交给防护</span><span class='arrow-symbol'>→</span></div>"
            f"<div class='arrow-line back'><span>{escape(str(pair.get('return_label') or '检查中'))}</span><span class='arrow-symbol'>←</span></div></div>"
            f"<div class='shield-node'><div class='node-top'><span class='node-step'>防护第 {index} 步</span><span class='node-state'>{escape(state_label)}</span></div>"
            f"<div class='node-title'>{escape(str(pair['shield_title']))}</div><div class='node-detail'>{escape(str(pair['shield_detail']))}</div></div></div>"
        )
    status = "执行完成 · 每个 Agent 动作都经过 ShieldAgent" if complete else f"安全执行中 · 已输出 {len(pairs)} 步"
    empty_state = '<div class="board-empty">正在等待 Agent 产生第一个动作…</div>'
    execution_rows = "".join(rows) if rows else empty_state
    return (
        f"<section class='execution-board'><div class='execution-status{' complete' if complete else ''}'><span class='live-pulse'></span><strong>{status}</strong><span>动作与防护一一对应</span></div>"
        "<div class='lane-heads'><div class='lane-title'><div class='lane-icon'>A</div><div><div class='lane-name'>任务 Agent</div><div class='lane-sub'>左侧 · 正常执行轨迹</div></div></div>"
        "<div class='lane-title right'><div class='lane-icon'>S</div><div><div class='lane-name'>ShieldAgent</div><div class='lane-sub'>右侧 · 实时安全防护</div></div></div></div>"
        f"<div class='execution-list'>{execution_rows}</div></section>"
    )


class _LiveExecutionFlow:
    def __init__(self) -> None:
        self.slot = st.empty()
        self.pairs: list[dict] = []

    def _draw(self, *, complete: bool = False) -> None:
        self.slot.markdown(
            _process_board_html(self.pairs, complete=complete),
            unsafe_allow_html=True,
        )
        time.sleep(0.08)

    def on_progress(self, event: str, payload) -> None:
        if event == "planning_started":
            self.pairs = [{
                "agent_title": "理解任务并生成行动计划",
                "agent_detail": "在线模型正在把 Prompt 转换为固定范围的 Web 动作…",
                "shield_title": "加载法规与能力边界",
                "shield_detail": "正在准备 " + "、".join(payload.get("regulations", ())) + " 运行时规则",
                "state": "PENDING",
                "return_label": "检查中",
            }]
        elif event == "planning_completed" and self.pairs:
            self.pairs[0].update({
                "agent_detail": f"{payload.get('model')} 生成 {payload.get('environment')} / {payload.get('task_action')} 计划：{payload.get('explanation')}",
                "shield_title": "计划范围核验通过",
                "shield_detail": "环境、动作类型与参数均在 Agent 已注册能力范围内",
                "state": "ALLOW",
                "return_label": "计划可执行",
            })
        elif event == "action_requested":
            capability = str(payload.get("capability") or "runtime.action")
            title, detail = _action_copy(capability, dict(payload.get("arguments") or {}))
            self.pairs.append({
                "agent_title": title,
                "agent_detail": detail,
                "shield_title": "正在拦截并核验此动作",
                "shield_detail": f"ShieldAgent 正在检查 {capability} 的规则、数据与副作用",
                "state": "PENDING",
                "return_label": "检查中",
            })
        elif event == "shield_decided" and self.pairs:
            title, detail, state, return_label = _shield_copy(dict(payload))
            self.pairs[-1].update({
                "shield_title": title,
                "shield_detail": detail,
                "state": state,
                "return_label": return_label,
            })
        self._draw()

    def finalize(self, session: DemoSession) -> None:
        self.pairs = _execution_pairs(session)
        self._draw(complete=True)


def _render_execution_flow(session: DemoSession) -> None:
    st.markdown(_process_board_html(_execution_pairs(session), complete=True), unsafe_allow_html=True)
    _render_shielding_plan(session)


def _render_shielding_plan(session: DemoSession) -> None:
    traces = [
        (event.capability_id or "runtime.action", event.details.get("shielding_plan"))
        for event in session.snapshot.events
        if event.details.get("shielding_plan")
    ]
    if not traces:
        st.caption("当前动作没有产生可展示的 Shielding Plan。")
        return
    st.markdown("#### 各动作的 Shielding Plan")
    st.caption("以下内容来自本次实际运行时审计，展示每个动作命中的规则、谓词检查与防护结果。")
    for trace_index, (capability, trace) in enumerate(traces, 1):
        with st.expander(f"动作 {trace_index} · {capability} · {trace.get('final_label', 'verified')}"):
            for operation in trace.get("operations", []):
                st.markdown(f"`{operation['status']}` · **{operation['operation']}**：{operation['detail']}")
            for circuit in trace.get("circuits", []):
                st.markdown(f"**{circuit['rule_id']} · {circuit['verification']}**")
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
    if session.web_environment == "shopping":
        state = session.result.get("environment_state", {})
        cart = state.get("cart", {})
        values = (("Web 环境", "Shopping"), ("受控副作用", f"{session.result.get('web_actions', 0)} 次"), ("购物车 / 订单", f"{cart.get('item_count', 0)} 件 / {'已创建' if state.get('order') else '未创建'}"))
    elif session.web_environment:
        values = (("Web 环境", session.web_environment), ("受控网页动作", f"{session.result.get('web_actions', 0)} 次"), ("ShieldAgent 复核", "已完成"))
    elif scenario == "gdpr":
        values = (("原始个人数据外发", "0 次"), ("安全汇总外发", f"{session.result.get('aggregate_messages', 0)} 次"), ("发送前重新核验", "通过"))
    else:
        values = (("人工决定", session.result.get("operator_decision", "等待审批")), ("实际邮件效果", f"{session.result.get('email_messages_after_decision', 0)} 次"), ("策略复核", "已完成" if not waiting else "等待人工决定"))
    columns = st.columns(3)
    for column, (label, value) in zip(columns, values):
        column.markdown(f"<div class='metric-card'><div class='metric-label'>{escape(label)}</div><div class='metric-value'>{escape(value)}</div></div>", unsafe_allow_html=True)
    if session.web_environment == "shopping":
        st.markdown("### Agent 操作后的 Shopping 环境")
        _render_shopping_environment(session.result.get("environment_state"))
        if session.result.get("scope_guard"):
            st.warning(session.result["scope_guard"])


st.markdown("""<section class="hero"><div class="eyebrow">AGENTSHIELD · 安全执行可视化</div><h1>看见 Agent 如何安全地完成网页任务。</h1><p>输入任务并选择要遵守的法规。任务 Agent 每提出一个网页操作，ShieldAgent 都会先检查是否符合规则；页面会清楚展示该动作是被放行、要求调整，还是被阻止。</p><div class="hero-badge">每一个动作，都有可解释的安全决定</div></section>""", unsafe_allow_html=True)

regulations, prompt, model_config, execution_backend, webarena_urls = _render_setup()
scenario = _scenario(regulations[0]) if regulations else "gdpr"
paper_target = _paper_target(prompt, webarena_urls) if prompt else None
awm_python = default_awm_python()
browsergym_ready = awm_runtime_ready(awm_python)
paper_ready = bool(
    execution_backend == "paper"
    and paper_target
    and paper_target[2]
    and browsergym_ready
    and model_config
    and model_config.protocol == "openai"
)
signature = (regulations, prompt, execution_backend, tuple(sorted(webarena_urls.items())), bool(model_config), model_config.model if model_config else "", model_config.base_url if model_config else "")
if st.session_state.get("run_signature") not in (None, signature):
    _close_previous()

run_column, hint_column = st.columns((1.35, 3.65), vertical_alignment="center")
with run_column:
    ready_to_run = bool(prompt and regulations and model_config) and (
        execution_backend == "fixture" or paper_ready
    )
    run = st.button("安全执行", type="primary", width="stretch", disabled=not ready_to_run)
with hint_column:
    if not regulations:
        st.caption("请先完成第 1 步：选择法规。系统会加载已完成 AutoPolicy 候选抽取和人工审核的运行时规则包。")
    elif not model_config:
        st.caption("请完成第 2 步：填写 API Key、模型名称和 API 地址。配置完成后才能在线安全执行。")
    elif not prompt:
        st.caption("请完成第 3 步：输入或填入一段任务 Prompt。")
    elif execution_backend == "paper" and not browsergym_ready:
        st.caption("在线演示环境尚未安装。请由管理员完成 AWM 运行环境配置。")
    elif execution_backend == "paper" and model_config.protocol != "openai":
        st.caption("固定版本 AWM 使用 ChatOpenAI 接口；请选择 OpenAI 或 OpenAI 兼容服务（包括 MiniMax 兼容端点）。")
    elif execution_backend == "paper" and paper_target is None:
        st.caption("当前任务未能识别为已支持的购物、内容管理、社区、代码协作或地图场景。请使用任务示例，或在 Prompt 中明确网站场景。")
    elif execution_backend == "paper" and not paper_target[2]:
        st.caption(f"请在“管理员设置：连接演示网站与查看复现信息”中填写 {WEB_TARGETS[paper_target[0]][0]} 的网站地址。")
    else:
        st.caption("已满足执行条件：AWM 生成动作，ShieldAgent 执行前核验，允许后才进入 WebArena。")

ran_now = False
run_failed = False
if run:
    _close_previous()
    st.markdown("---")
    st.markdown("## 安全执行过程")
    st.caption(f"任务 Prompt：{prompt}")
    if execution_backend == "paper":
        try:
            environment, workflow, start_url = paper_target
            status = st.status("正在启动 AWM + WebArena 安全执行…", expanded=True)
            status.write("1/4 已加载固定版本 AWM 与 WebArena")
            status.write("2/4 已把用户 Prompt 注入 BrowserGym goal")
            status.write("3/4 ShieldAgent 已位于 AWM get_action 与 WebArena env.step 之间")
            model_name = model_config.model
            if not model_name.startswith("openai/"):
                model_name = f"openai/{model_name}"
            process_environment = {
                **webarena_urls,
                "OPENAI_API_KEY": model_config.api_key,
                "OPENAI_API_BASE": model_config.base_url,
            }
            result = AWMWebArenaRunner(python_executable=awm_python).run(
                AWMWebArenaConfig(
                    task_name="openended",
                    task_prompt=prompt,
                    start_url=start_url,
                    model_name=model_name,
                    regulations=regulations,
                    workflow=workflow,
                    headless=True,
                ),
                Path(".agentshield/webarena-ui"),
                environment=process_environment,
            )
            status.write("4/4 WebArena 执行结束，已保存 BrowserGym 轨迹与 ShieldAgent 审计")
            status.update(label="安全执行已完成", state="complete", expanded=False)
            st.session_state["upstream_result"] = dict(result)
            st.session_state["run_signature"] = signature
            pairs = _paper_pairs(dict(result))
            st.markdown(_process_board_html(pairs, complete=True), unsafe_allow_html=True)
            ran_now = True
        except Exception as exc:
            run_failed = True
            st.error(f"AWM / WebArena 安全执行未完成：{type(exc).__name__}: {exc}")
    else:
        live_flow = _LiveExecutionFlow()
        try:
            session = run_demo(
                scenario,
                task_prompt=prompt,
                regulations=regulations,
                model_config=model_config,
                web_task=True,
                progress_callback=live_flow.on_progress,
            )
            st.session_state["demo_session"] = session
            st.session_state["run_signature"] = signature
            live_flow.finalize(session)
            ran_now = True
        except ModelPlanningError as exc:
            run_failed = True
            st.error(f"模型计划未通过安全格式核验：{exc}")
        except Exception as exc:
            run_failed = True
            st.error(f"本地回归执行未完成：{type(exc).__name__}: {exc}")

session = st.session_state.get("demo_session")
upstream_result = st.session_state.get("upstream_result")
if isinstance(upstream_result, dict):
    if not ran_now:
        st.markdown("---")
        st.markdown("## 安全执行过程")
        st.markdown(_process_board_html(_paper_pairs(upstream_result), complete=True), unsafe_allow_html=True)
    st.success("真实 AWM + WebArena 运行已完成；每个动作均在进入环境前通过 ShieldAgent。")
    st.caption(f"BrowserGym 轨迹：{upstream_result.get('experiment_directory')} · ShieldAgent 审计：{upstream_result.get('shield_trace_path')}")
elif isinstance(session, DemoSession):
    if not ran_now:
        st.markdown("---")
        st.markdown("## 安全执行过程")
        st.caption(f"任务 Prompt：{session.task_prompt}")
        _render_execution_flow(session)
    else:
        _render_shielding_plan(session)
    st.markdown("### 执行结果")
    _render_result(scenario, session)
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
elif not run_failed:
    st.markdown("---")
    st.markdown("### 安全执行会做什么？")
    one, two, three = st.columns(3)
    for column, title, text in ((one, "1 · AWM 提议动作", "开源任务 Agent 根据 WebArena 观察生成 BrowserGym 动作。"), (two, "2 · ShieldAgent 前置核验", "动作不经核验不能到达 WebArena env.step。"), (three, "3 · 反馈或执行", "允许则执行；不安全则反馈 AWM 重新规划并保留审计。")):
        column.markdown(f"<div class='agent-card'><div class='agent-tag'>{title}</div><p>{text}</p></div>", unsafe_allow_html=True)

st.markdown("---")
st.caption("论文同源模式使用固定 AWM 与开源 WebArena；本地回归模式仅使用合成夹具。AgentShield 提供技术控制，不构成法律意见或完整合规保证。")
