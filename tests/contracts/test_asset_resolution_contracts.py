from __future__ import annotations

from pathlib import Path

from story.runtime import resolve_assets_root_for_module
from story.paths import resolve_assets_root


ROOT = Path(__file__).resolve().parents[2]


def test_story_assets_resolution_prefers_package_assets() -> None:
    resolved = resolve_assets_root()
    assert resolved == (ROOT / "story" / "assets").resolve()
    assert (resolved / "llm" / "lmdeploy.yml").exists()


def test_runtime_assets_resolution_prefers_bundled_module_assets_outside_source_checkout(tmp_path: Path) -> None:
    site_packages = tmp_path / "site-packages"
    story_pkg = site_packages / "story"
    package_assets = story_pkg / "assets"
    module_file = story_pkg / "paths.py"

    module_file.parent.mkdir(parents=True, exist_ok=True)
    package_assets.mkdir(parents=True, exist_ok=True)
    (story_pkg / "runtime.py").write_text("# synthetic runtime\n", encoding="utf-8")
    module_file.write_text("# synthetic module\n", encoding="utf-8")
    (package_assets / "llm").mkdir(parents=True, exist_ok=True)
    (package_assets / "llm" / "lmdeploy.yml").write_text("provider_id: lmdeploy\n", encoding="utf-8")

    resolved = resolve_assets_root_for_module(module_file, project_root=tmp_path / "not-a-repo")
    assert resolved == package_assets.resolve()

