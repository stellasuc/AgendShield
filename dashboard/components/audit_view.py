from __future__ import annotations

from agentshield.observability import SecuritySnapshot


def render_effects(snapshot: SecuritySnapshot) -> None:
    import streamlit as st

    st.markdown("#### 实际执行结果")
    effects = list(snapshot.effects)
    transactions = list(snapshot.transactions)
    effect = next(
        (
            item
            for item in reversed(effects)
            if item.get("capability_id") == "email.send"
        ),
        effects[-1] if effects else {},
    )
    latest = next(
        (
            item
            for item in transactions
            if item.get("transaction_id") == effect.get("transaction_id")
        ),
        transactions[-1] if transactions else {},
    )
    first, second = st.columns(2)
    first.metric("由 Broker 受控执行", "是" if snapshot.broker_mediated else "否")
    second.metric(
        "代理可直接访问原始后端",
        "是" if snapshot.raw_backend_exposed_to_agent else "否",
    )
    st.markdown("**受控能力**")
    st.code(
        effect.get("capability_id") or latest.get("capability_id", "N/A"),
        language=None,
    )
    st.markdown("**事务编号**")
    st.code(
        effect.get("transaction_id") or latest.get("transaction_id", "N/A"),
        language=None,
    )
    st.markdown("**效果编号**")
    st.code(
        effect.get("effect_id") or latest.get("effect_id", "N/A"),
        language=None,
    )
    st.markdown("**执行状态**")
    st.caption(effect.get("status") or latest.get("status", "N/A"))
    st.caption(
        "“否”仅表示正常情况下 Agent 通过 Broker API 操作，并非操作系统级隔离声明。"
    )


def render_audit(snapshot: SecuritySnapshot) -> None:
    import streamlit as st

    with st.expander("原始审计记录（敏感载荷已脱敏）", expanded=False):
        tab_tx, tab_effect, tab_approval = st.tabs(
            ["事务", "效果", "审批"]
        )
        with tab_tx:
            if snapshot.transactions:
                st.dataframe(
                    list(snapshot.transactions),
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.caption("没有事务记录")
        with tab_effect:
            if snapshot.effects:
                st.json(list(snapshot.effects), expanded=False)
            else:
                st.caption("没有实际效果执行")
        with tab_approval:
            if snapshot.approvals:
                st.json(list(snapshot.approvals), expanded=False)
            else:
                st.caption("没有审批记录")
