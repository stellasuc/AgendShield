"""Launch the optional local Streamlit portfolio dashboard."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys


def launch_dashboard() -> int:
    if importlib.util.find_spec("streamlit") is None:
        raise SystemExit(
            "Dashboard dependencies are not installed. "
            "Run: pip install -e '.[dashboard]'"
        )
    app = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"
    if not app.is_file():
        raise SystemExit(f"Dashboard entry point not found: {app}")
    try:
        return subprocess.call(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(app),
                "--server.address",
                "127.0.0.1",
                "--browser.gatherUsageStats",
                "false",
            ]
        )
    except KeyboardInterrupt:
        return 130
