from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_release_smoke_covers_installed_wheel_and_gui_entrypoints() -> None:
    content = (ROOT / "scripts" / "release_smoke.py").read_text(encoding="utf-8")
    assert '"render-image-gui", "missing-streamlit"' in content
    assert '"ai-studio-gui", "missing-streamlit"' in content
    assert 'pip", "show", "ai-studio"' in content
    assert 'assert_installed_story_assets' in content
    assert 'resolve_assets_root' in content


def test_requirements_are_consolidated() -> None:
    root = ROOT
    assert (root / "requirements.txt").exists()
    assert not (root / "requirements-core.txt").exists()
    assert not (root / "requirements-gui.txt").exists()
    assert not (root / "requirements-test.txt").exists()
    assert not (root / "requirements-dev.txt").exists()

    requirements = (root / "requirements.txt").read_text(encoding="utf-8").lower()

    assert "edge-tts" in requirements
    assert "streamlit" in requirements
    assert "pytest" in requirements
    assert "wheel" in requirements


def test_release_smoke_uses_timeouts_and_offline_friendly_env() -> None:
    content = (ROOT / "scripts" / "release_smoke.py").read_text(encoding="utf-8")
    assert 'DEFAULT_TIMEOUT_SECONDS = 120' in content
    assert 'PIP_DISABLE_PIP_VERSION_CHECK' in content
    assert 'PIP_NO_INPUT' in content
    assert 'timeout=timeout' in content



def test_story_paths_resolution_strategy_is_explicit() -> None:
    content = (ROOT / "story" / "paths.py").read_text(encoding="utf-8")
    assert 'resolve_assets_root_for_module' in content
    assert 'resolve_common_package_assets_root' in content

    runtime = (ROOT / "common" / "runtime.py").read_text(encoding="utf-8")
    assert '_looks_like_source_checkout' in runtime
    assert 'resolve_common_package_assets_root' in runtime
    assert 'resolve_assets_root_for_module' in runtime


def test_release_smoke_runs_installed_wheel_probes_from_neutral_cwd() -> None:
    content = (ROOT / "scripts" / "release_smoke.py").read_text(encoding="utf-8")
    assert "cwd=tmpdir" in content

