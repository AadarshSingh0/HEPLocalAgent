"""Console launcher for the Streamlit HEP-agent interface."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Start the packaged Streamlit application."""

    app_path = Path(__file__).with_name(
        "web_app.py"
    )

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        *sys.argv[1:],
    ]

    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
