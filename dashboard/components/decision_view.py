from __future__ import annotations

from agentshield.observability import SecuritySnapshot


def render_decision(snapshot: SecuritySnapshot) -> None:
    import streamlit as st

    st.markdown("## Policy Decision")
    decision = snapshot.policy_decision
    if decision is None:
        st.info("No policy decision is available.")
        return
    first, second = st.columns(2)
    first.metric("Decision", decision.decision)
    second.metric("Re-verification", decision.reverification or "N/A")
    st.markdown("**Regulation**")
    st.caption(decision.regulation or "Runtime safeguard")
    st.markdown("**Control**")
    st.caption(decision.control or "General runtime control")
    st.markdown("**Rule**")
    st.code(decision.rule_id or "N/A", language=None)
    st.markdown("**Source**")
    if decision.source_url:
        st.markdown(
            f"[{decision.source_article}]({decision.source_url})"
        )
    else:
        st.caption(decision.source_article or "N/A")
    st.markdown("**Reason**")
    st.caption(decision.reason or "No explanation recorded")
    st.markdown("**Intervention**")
    st.caption(decision.intervention or "None")
