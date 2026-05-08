from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_studio_gui_exposes_project_tools_workspace() -> None:
    content = (ROOT / "studio" / "gui_entry.py").read_text(encoding="utf-8")
    assert "render_project_tools_workspace" in content
    assert '"Project Tools"' in content


def test_common_gui_lazy_exports_project_tools() -> None:
    content = (ROOT / "common" / "gui" / "__init__.py").read_text(encoding="utf-8")
    assert "def render_project_tools_workspace" in content
    assert ".project_tools" in content


def test_project_tools_gui_surfaces_cleanup_and_models() -> None:
    content = (ROOT / "common" / "gui" / "project_tools.py").read_text(encoding="utf-8")
    assert "build_cleanup_plan" in content
    assert "apply_cleanup_plan" in content
    assert "scan_model_store" in content
    assert "remove_model_store_path" in content
    assert "Confirm cleanup" in content
    assert "Apply remove" in content
    assert "Download JSON report" in content


def test_project_tools_gui_surfaces_qa_release_commands() -> None:
    content = (ROOT / "common" / "gui" / "project_tools.py").read_text(encoding="utf-8")
    assert "QA / Release" in content
    assert "check_dependency_direction.py" in content
    assert "check_wheel_contents.py" in content
    assert "release_smoke.py" in content
    assert "build_dist.py" in content
    assert "sync_version.py" in content
    assert "make_clean_release.py" in content
    assert "Confirm build dist" in content
    assert "Confirm sync version" in content
    assert "Confirm clean release zip" in content

