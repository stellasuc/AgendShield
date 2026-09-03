from __future__ import annotations

from agentshield.observability import SecuritySnapshot


def render_state(snapshot: SecuritySnapshot) -> None:
    import streamlit as st

    st.markdown("## Compliance State")
    if not snapshot.data_objects:
        st.info("No data objects have been observed.")
        return
    by_id = {item.object_id: item for item in snapshot.data_objects}
    selected = st.selectbox(
        "Data object",
        options=tuple(by_id),
        key=f"data-object-{snapshot.run_id}",
    )
    item = by_id[selected]
    first, second = st.columns(2)
    first.metric("Classification", item.classification.replace("_", " ").title())
    second.metric(
        "Personal data",
        "YES" if item.contains_personal_data else "NO",
    )
    st.markdown("**Source**")
    st.caption(item.source or "Derived runtime object")
    st.markdown("**Task purpose**")
    st.caption(item.purpose or "Not declared")
    st.markdown("**Categories**")
    st.caption(", ".join(item.categories) if item.categories else "None detected")
    if item.recipients:
        st.markdown("**Recipient**")
        st.caption(", ".join(item.recipients))
    if item.transformations:
        st.markdown("**Transformations**")
        st.caption(", ".join(item.transformations))
    if item.safe_summary:
        st.success(item.safe_summary)
    fingerprint = item.content_fingerprint or "unavailable"
    st.caption(f"Content fingerprint: {fingerprint[:16]}…")
