from __future__ import annotations

from html import escape

from agentshield.observability import SecuritySnapshot


STATUS_COLORS = {
    "INFO": "#64748b",
    "ALLOW": "#2563eb",
    "WARNING": "#d97706",
    "BLOCK": "#dc2626",
    "REPAIR": "#7c3aed",
    "APPROVAL": "#c2410c",
    "SUCCESS": "#059669",
}


def render_timeline(snapshot: SecuritySnapshot) -> None:
    import streamlit as st

    st.markdown("## Lifecycle / Security Timeline")
    st.caption(
        "Structured from the persisted AgentShield audit stream; payload fields "
        "remain fingerprinted."
    )
    if not snapshot.events:
        st.info("No runtime events are available for this run.")
        return
    blocks = []
    for event in snapshot.events:
        color = STATUS_COLORS[event.status]
        capability = (
            f"<span class='timeline-cap'>{escape(event.capability_id)}</span>"
            if event.capability_id
            else ""
        )
        rule = (
            f"<div class='timeline-meta'>Rule: {escape(event.primary_rule_id)}</div>"
            if event.primary_rule_id
            else ""
        )
        blocks.append(
            "<div class='timeline-row' style='border-left-color:"
            + color
            + "'>"
            + f"<div class='timeline-seq'>{event.sequence:02d}</div>"
            + "<div class='timeline-content'>"
            + f"<span class='timeline-status' style='color:{color}'>"
            + escape(event.status)
            + "</span>"
            + f"<strong>{escape(event.event_type)}</strong>{capability}"
            + f"<div class='timeline-summary'>{escape(event.summary)}</div>"
            + rule
            + "</div></div>"
        )
    st.markdown("".join(blocks), unsafe_allow_html=True)
