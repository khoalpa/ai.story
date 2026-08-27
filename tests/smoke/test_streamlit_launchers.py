from __future__ import annotations

import importlib.metadata
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MINIMUM_STREAMLIT = (1, 49)


def _version_pair(value: str) -> tuple[int, int]:
    major, minor, *_ = value.split(".")
    return int(major), int(minor)


def test_streamlit_runtime_meets_supported_minimum() -> None:
    assert _version_pair(importlib.metadata.version("streamlit")) >= MINIMUM_STREAMLIT


def test_every_streamlit_launcher_opens_in_a_clean_runtime() -> None:
    probe = r'''
from streamlit.testing.v1 import AppTest
from pathlib import Path
from tempfile import TemporaryDirectory
cases = [
    ("audio.gui_entry", {"tts_provider": "edge_tts"}),
    ("video.gui_entry", {}),
    ("studio.gui_entry", {}),
]

for launcher_module, initial_state in cases:
    app = AppTest.from_string(
        f"from {launcher_module} import main\nmain()\n",
        default_timeout=60,
    )
    for key, value in initial_state.items():
        app.session_state[key] = value
    app.run()
    if app.exception:
        messages = [exception.message for exception in app.exception]
        raise AssertionError(f"{launcher_module}: {messages}")

studio = AppTest.from_string("from studio.gui_entry import main\nmain()\n", default_timeout=60)
studio.session_state["tts_provider"] = "edge_tts"
studio.run()

for workspace_name, child_radio_label in (
    ("Audio Studio", "Audio Studio"),
    ("Video Studio", "Video Studio"),
):
    workspace = next(radio for radio in studio.radio if radio.label == "Workspace")
    workspace.set_value(workspace_name).run()
    if studio.exception:
        raise AssertionError(
            f"Studio workspace {workspace_name}: {[item.message for item in studio.exception]}"
        )
    if not any(radio.label == child_radio_label for radio in studio.radio):
        raise AssertionError(f"Studio workspace {workspace_name} did not render {child_radio_label!r}")
'''
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(ROOT), existing_pythonpath) if part
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=180,
    )

    assert result.returncode == 0, result.stdout + result.stderr
