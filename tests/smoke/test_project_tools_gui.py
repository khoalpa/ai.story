from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_studio_gui_exposes_project_tools_workspace() -> None:
    content = (ROOT / "studio" / "gui_entry.py").read_text(encoding="utf-8")
    assert "render_project_tools_workspace" in content
    assert '"Project Tools"' in content


def test_studio_owns_project_tools() -> None:
    content = (ROOT / "studio" / "project_tools.py").read_text(encoding="utf-8")
    assert "def render_project_tools_workspace" in content
    assert "common" not in content


def test_package_tools_keep_cleanup_and_models_local() -> None:
    assert "build_cleanup_plan" in (ROOT / "audio" / "gui" / "project_tools.py").read_text(encoding="utf-8")
    assert "scan_model_store" in (ROOT / "scripts" / "manage_models.py").read_text(encoding="utf-8")


def test_project_tools_gui_surfaces_qa_release_commands() -> None:
    content = (ROOT / "studio" / "project_tools.py").read_text(encoding="utf-8")
    assert "check_dependency_direction.py" in content
    assert "check_wheel_contents.py" in content
    assert "release_smoke.py" in content

