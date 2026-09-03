from __future__ import annotations

from dashboard.demo_loader import DEMO_DEFINITIONS


def render_sidebar() -> str:
    import streamlit as st

    with st.sidebar:
        st.markdown("### Demo")
        selected = st.radio(
            "Select a scenario",
            options=tuple(DEMO_DEFINITIONS),
            format_func=lambda key: DEMO_DEFINITIONS[key].title,
            label_visibility="collapsed",
        )
        definition = DEMO_DEFINITIONS[selected]
        st.markdown("---")
        st.markdown("### Applicable Regulations")
        st.checkbox(
            definition.regulation,
            value=True,
            disabled=True,
            help="Regulation configuration is fixed by the selected demo.",
        )
        for regulation in ("GDPR", "PIPL"):
            if regulation != definition.regulation:
                st.checkbox(regulation, value=False, disabled=True)
        st.caption(
            "Demo policy configuration is locked to prevent inconsistent "
            "scenario/regulation combinations."
        )
        st.markdown("---")
        st.caption("Local synthetic data · Mock effects · No external services")
    return selected
