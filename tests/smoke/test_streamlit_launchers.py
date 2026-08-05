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

cases = [
    ("story.gui_entry", {}),
    ("audio.gui_entry", {"tts_provider": "edge_tts"}),
    (
        "image.gui_entry",
        {
            "image_provider": "stable_diffusion_remote",
            "image_local_preload_model_on_startup": False,
        },
    ),
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
