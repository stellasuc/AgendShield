"""Spawn-safe Streamlit entry point for the AgentShield visualizer."""

from __future__ import annotations

import importlib
import sys

from streamlit.runtime.scriptrunner import get_script_run_ctx


def main() -> None:
    # Streamlit reruns this entry point in one interpreter, so reload the view
    # module after its first render instead of returning the import cache.
    module = sys.modules.get("dashboard.ui")
    if module is None:
        importlib.import_module("dashboard.ui")
    else:
        importlib.reload(module)


# A spawned broker imports this file as ``__mp_main__`` without a Streamlit
# script context. The guard prevents the child from rendering a second UI.
if get_script_run_ctx(suppress_warning=True) is not None:
    main()
