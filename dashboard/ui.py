"""AgentShield — Agent Security Runtime Visualizer."""

from __future__ import annotations

import streamlit as st

from dashboard.components.audit_view import render_audit, render_effects
from dashboard.components.decision_view import render_decision
from dashboard.components.lineage_view import render_lineage
from dashboard.components.sidebar import render_sidebar
from dashboard.components.state_view import render_state
from dashboard.components.timeline import render_timeline
from dashboard.demo_loader import (
    DEMO_DEFINITIONS,
    DemoSession,
    resolve_pipl_approval,
    run_demo,
)


st.set_page_config(
    page_title="AgentShield Runtime Visualizer",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
      --as-border: color-mix(in srgb, currentColor 18%, transparent);
      --as-muted: color-mix(in srgb, currentColor 68%, transparent);
    }
    .block-container {max-width: 1320px; padding-top: 2rem; padding-bottom: 4rem;}
    .hero {
      border: 1px solid var(--as-border);
      border-radius: 18px;
      padding: 1.6rem 1.8rem;
      margin-bottom: 1.25rem;
      background: linear-gradient(135deg, rgba(37,99,235,.08), rgba(5,150,105,.04));
    }
    .eyebrow {font-size: .78rem; letter-spacing: .13em; text-transform: uppercase;
      color: #2563eb; font-weight: 750; margin-bottom: .4rem;}
    .hero h1 {font-size: 2.25rem; line-height: 1.05; margin: 0 0 .45rem 0;}
    .hero p {color: var(--as-muted); margin: 0; font-size: 1rem;}
    .timeline-row {display:flex; gap:.9rem; border-left:4px solid; padding:.7rem .85rem;
      margin:.45rem 0; border-radius:0 10px 10px 0;
      background:color-mix(in srgb, currentColor 4%, transparent);}
    .timeline-seq {font-family:monospace; color:var(--as-muted); min-width:1.8rem;}
    .timeline-content {min-width:0;}
    .timeline-status {font-size:.7rem; font-weight:800; letter-spacing:.08em;
      margin-right:.55rem;}
    .timeline-cap {font-family:monospace; font-size:.78rem; margin-left:.55rem;
      color:var(--as-muted);}
    .timeline-summary {font-size:.88rem; margin-top:.2rem;}
    .timeline-meta {font-family:monospace; font-size:.72rem; color:var(--as-muted);
      margin-top:.18rem;}
    [data-testid="stMetric"] {border:1px solid var(--as-border); border-radius:12px;
      padding:.7rem .9rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


def _drop_previous_session() -> None:
    previous = st.session_state.get("demo_session")
    if isinstance(previous, DemoSession):
        previous.close()
    st.session_state.pop("demo_session", None)


selected = render_sidebar()
if st.session_state.get("selected_demo") != selected:
    _drop_previous_session()
    st.session_state["selected_demo"] = selected

definition = DEMO_DEFINITIONS[selected]
session = st.session_state.get("demo_session")
snapshot = session.snapshot if isinstance(session, DemoSession) else None

run_status = "PROTECTED" if snapshot else "READY"
if snapshot and any(
    item["status"] == "WAITING_APPROVAL" for item in snapshot.transactions
):
    run_status = "APPROVAL REQUIRED"

st.markdown(
    f"""
    <section class="hero">
      <div class="eyebrow">Agent Security Runtime Visualizer</div>
      <h1>AgentShield</h1>
      <p>Lifecycle-Level Runtime Security for LLM Agents ·
      Status: <strong>{run_status}</strong> · Regulation:
      <strong>{definition.regulation}</strong></p>
    </section>
    """,
    unsafe_allow_html=True,
)

heading, action = st.columns([4, 1])
with heading:
    st.markdown(f"### {definition.title}")
    st.caption(definition.description)
with action:
    if st.button("Run secure demo", type="primary", width="stretch"):
        _drop_previous_session()
        try:
            with st.spinner("Running the real brokered workflow…"):
                session = run_demo(selected)
                st.session_state["demo_session"] = session
                snapshot = session.snapshot
            st.rerun()
        except Exception as exc:
            st.error(
                "The demo could not complete. "
                f"{type(exc).__name__}: {exc}"
            )
            snapshot = None

st.markdown("## Agent Execution")
st.markdown("**User request**")
st.info(f'"{definition.user_request}"')
if snapshot:
    proposals = [
        item["capability_id"]
        for item in snapshot.transactions
        if not item.get("repair_parent")
    ]
    st.markdown("**Agent proposed**")
    st.code("\n".join(proposals), language=None)
else:
    st.caption("Run the demo to inspect the actual capability requests.")

if snapshot and isinstance(session, DemoSession):
    if selected == "pipl":
        waiting = any(
            item["status"] == "WAITING_APPROVAL"
            for item in snapshot.transactions
        )
        st.markdown("### Human decision")
        if waiting:
            st.warning(
                "The email effect is paused. No backend execution has occurred."
            )
            approve, deny = st.columns(2)
            if approve.button("Approve and re-verify", type="primary", width="stretch"):
                try:
                    with st.spinner("Restarting broker and re-verifying policy…"):
                        snapshot = resolve_pipl_approval(session, "approve")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Approval failed: {type(exc).__name__}: {exc}")
            if deny.button("Deny", width="stretch"):
                try:
                    snapshot = resolve_pipl_approval(session, "deny")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Denial failed: {type(exc).__name__}: {exc}")
        else:
            outcome = session.result.get("operator_decision", "RESOLVED")
            count = session.result.get("email_messages_after_decision", 0)
            st.success(
                f"Decision: {outcome} · Actual email effects: {count}"
            )

    if selected == "gdpr":
        before = next(
            (
                item
                for item in snapshot.data_objects
                if item.contains_personal_data
            ),
            None,
        )
        after = next(
            (
                item
                for item in snapshot.data_objects
                if "AGGREGATE" in item.transformations
            ),
            None,
        )
        left, right = st.columns(2)
        with left:
            st.markdown("#### Before enforcement")
            if before:
                st.error(
                    f"{before.object_id} · "
                    f"{len(before.categories)} personal-data categories detected"
                )
            st.caption("Raw records were proposed for external transfer.")
        with right:
            st.markdown("#### After enforcement")
            if after:
                st.success(after.safe_summary or after.object_id)
            st.caption(
                f"Raw PII sent: {session.result['raw_pii_messages']} · "
                f"Aggregate messages: {session.result['aggregate_messages']}"
            )

    if selected == "idempotency":
        first, retry, actual = st.columns(3)
        first.metric("First request", session.result["first_request"])
        retry.metric("Retry", session.result["retry"])
        actual.metric(
            "Actual backend executions",
            session.result["email_messages_after_restart_and_retry"],
        )

    render_timeline(snapshot)
    state_column, decision_column = st.columns(2, gap="large")
    with state_column:
        render_state(snapshot)
    with decision_column:
        render_decision(snapshot)
    lineage_column, effect_column = st.columns([3, 2], gap="large")
    with lineage_column:
        render_lineage(snapshot)
    with effect_column:
        render_effects(snapshot)
    render_audit(snapshot)
else:
    st.markdown("---")
    st.markdown("### What this visualizer answers")
    one, two, three, four, five = st.columns(5)
    one.caption("What did the Agent do?")
    two.caption("What sensitive data exists?")
    three.caption("Which policy fired?")
    four.caption("What did AgentShield decide?")
    five.caption("What effect actually happened?")

st.markdown("---")
st.caption(
    "Local portfolio visualizer. Synthetic data and mock effects only. "
    "AgentShield provides selected technical controls—not legal advice or a "
    "legal-compliance guarantee."
)
