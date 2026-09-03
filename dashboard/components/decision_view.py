from __future__ import annotations

from agentshield.observability import SecuritySnapshot


def render_decision(snapshot: SecuritySnapshot) -> None:
    import streamlit as st

    st.markdown("#### 策略处理依据")
    decision = snapshot.policy_decision
    if decision is None:
        st.info("本次运行没有可展示的策略决定。")
        return
    first, second = st.columns(2)
    first.metric("策略决定", decision.decision)
    second.metric("重新核验", decision.reverification or "无")
    st.markdown("**适用规则包**")
    st.caption(decision.regulation or "Runtime safeguard")
    st.markdown("**技术控制**")
    st.caption(decision.control or "通用运行时控制")
    st.markdown("**规则编号**")
    st.code(decision.rule_id or "无", language=None)
    st.markdown("**规则来源**")
    if decision.source_url:
        st.markdown(
            f"[{decision.source_article}]({decision.source_url})"
        )
    else:
        st.caption(decision.source_article or "无")
    st.markdown("**触发原因**")
    st.caption(decision.reason or "未记录说明")
    st.markdown("**系统处理**")
    st.caption(decision.intervention or "无")
