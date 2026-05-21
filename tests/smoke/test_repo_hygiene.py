from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCANNED_DIRS = [ROOT / name for name in ("audio", "story", "image", "video", "common", "tests", "scripts")]
SCANNED_FILES = [ROOT / name for name in ("conftest.py", "pyproject.toml", "package_api_policy.json", "pytest.ini")]


def test_video_launchers_use_canonical_gui_app() -> None:
    video_launcher = (ROOT / "video" / "gui_entry.py").read_text(encoding="utf-8")
    studio_launcher = (ROOT / "studio" / "gui_entry.py").read_text(encoding="utf-8")
    assert "video.gui_app" not in video_launcher
    assert "video.gui_app" not in studio_launcher
    assert "video.gui.app" in video_launcher
    assert "video.gui.app" in studio_launcher


def test_no_legacy_gui_wrappers_left_in_repo() -> None:
    for rel_path in [
        "video/gui_app.py",
        "audio/_streamlit_app.py",
        "story/_streamlit_app.py",
        "video/_streamlit_app.py",
        "audio/gui_launcher.py",
        "story/gui_launcher.py",
        "video/gui_launcher.py",
    ]:
        assert not (ROOT / rel_path).exists(), rel_path


def test_pytest_ini_collects_root_tests() -> None:
    content = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert "testpaths = tests" in content
    assert "python_files = test_*.py" in content


def test_no_dead_streamlit_helper() -> None:
    runtime_text = (ROOT / "common/runtime.py").read_text(encoding="utf-8")
    assert "def launch_streamlit_app" not in runtime_text
    assert "_streamlit_app.py" not in runtime_text


def test_no_cache_or_runtime_artifacts_in_repo() -> None:
    banned_dirs = {"__pycache__", ".pytest_cache"}
    banned_files = {"jobs.json"}

    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=False,
    )
    tracked_paths = [
        ROOT / rel_path.decode("utf-8")
        for rel_path in result.stdout.split(b"\0")
        if rel_path
    ]

    for path in tracked_paths:
        if any(part in banned_dirs for part in path.parts):
            raise AssertionError(f"Unexpected tracked cache artifact: {path}")
        if path.name in banned_files and ".render_audio_gui" in path.parts:
            raise AssertionError(f"Unexpected tracked runtime artifact: {path}")

