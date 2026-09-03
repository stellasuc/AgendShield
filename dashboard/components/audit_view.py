from __future__ import annotations

from agentshield.observability import SecuritySnapshot


def render_effects(snapshot: SecuritySnapshot) -> None:
    import streamlit as st

    st.markdown("## Effect / Broker")
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
    first.metric("Broker mediated", "YES" if snapshot.broker_mediated else "NO")
    second.metric(
        "Raw backend exposed to agent",
        "YES" if snapshot.raw_backend_exposed_to_agent else "NO",
    )
    st.markdown("**Capability**")
    st.code(
        effect.get("capability_id") or latest.get("capability_id", "N/A"),
        language=None,
    )
    st.markdown("**Transaction ID**")
    st.code(
        effect.get("transaction_id") or latest.get("transaction_id", "N/A"),
        language=None,
    )
    st.markdown("**Effect ID**")
    st.code(
        effect.get("effect_id") or latest.get("effect_id", "N/A"),
        language=None,
    )
    st.markdown("**Status**")
    st.caption(effect.get("status") or latest.get("status", "N/A"))
    st.caption(
        "“NO” describes the normal brokered agent API surface; it is not an "
        "OS-level isolation claim."
    )


def render_audit(snapshot: SecuritySnapshot) -> None:
    import streamlit as st

    with st.expander("Payload-safe runtime evidence", expanded=False):
        tab_tx, tab_effect, tab_approval = st.tabs(
            ["Transactions", "Effects", "Approvals"]
        )
        with tab_tx:
            if snapshot.transactions:
                st.dataframe(
                    list(snapshot.transactions),
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.caption("No transactions")
        with tab_effect:
            if snapshot.effects:
                st.json(list(snapshot.effects), expanded=False)
            else:
                st.caption("No effects executed")
        with tab_approval:
            if snapshot.approvals:
                st.json(list(snapshot.approvals), expanded=False)
            else:
                st.caption("No approval records")
