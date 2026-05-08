from __future__ import annotations

import shlex
import sys


def build_missing_streamlit_message(script_name: str, *, requirements_file: str = "requirements.txt") -> str:
    """Return a normalized user-facing message for missing Streamlit.

    Uses the current Python interpreter so the suggested commands remain correct in
    virtualenvs and on non-Windows platforms.
    """
    python_cmd = shlex.quote(sys.executable or "python")
    return (
        "Missing dependency: streamlit\n"
        "Install required packages first, for example:\n"
        f"  {python_cmd} -m pip install -r {requirements_file}\n"
        "Then run again with:\n"
        f"  {python_cmd} -m streamlit run {script_name}"
    )
