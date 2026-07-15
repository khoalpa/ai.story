from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLEAN_PROJECT = ROOT / "scripts" / "clean_project.py"


def load_clean_project_module():
    spec = importlib.util.spec_from_file_location("clean_project", CLEAN_PROJECT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_clean_project_dry_run_is_default_and_apply_is_explicit() -> None:
    content = CLEAN_PROJECT.read_text(encoding="utf-8")
    assert "--apply" in content
    assert "Dry run only" in content
    assert "include_models" in content
    assert "audio.project_cleanup" in content


def test_clean_project_finds_and_removes_expected_artifacts(tmp_path: Path) -> None:
    module = load_clean_project_module()

    (tmp_path / "pkg" / "__pycache__").mkdir(parents=True)
    (tmp_path / "pkg" / "__pycache__" / "mod.pyc").write_bytes(b"cache")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "artifact.whl").write_text("wheel", encoding="utf-8")
    (tmp_path / "run.log").write_text("log", encoding="utf-8")
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "story.wav").write_text("audio", encoding="utf-8")
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "model.bin").write_bytes(b"model")
    (tmp_path / "source.py").write_text("print('keep')", encoding="utf-8")

    plan = module.build_cleanup_plan(tmp_path, include_runtime=True)

    planned = {path.relative_to(tmp_path) for path in [*plan.directories, *plan.files]}
    assert Path("pkg/__pycache__") in planned
    assert Path("dist") in planned
    assert Path("run.log") in planned
    assert Path("output") in planned
    assert Path("models") not in planned

    module.apply_cleanup_plan(plan)

    assert not (tmp_path / "pkg" / "__pycache__").exists()
    assert not (tmp_path / "dist").exists()
    assert not (tmp_path / "run.log").exists()
    assert not (tmp_path / "output").exists()
    assert (tmp_path / "models").exists()
    assert (tmp_path / "source.py").exists()


def test_clean_project_skips_models_and_runtime_contents_without_flags(tmp_path: Path) -> None:
    module = load_clean_project_module()

    (tmp_path / "image" / "local_models" / "_cache").mkdir(parents=True)
    (tmp_path / "image" / "local_models" / "_cache" / "download.log").write_text("log", encoding="utf-8")
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "render.log").write_text("log", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "tool.log").write_text("log", encoding="utf-8")
    (tmp_path / "root.log").write_text("log", encoding="utf-8")

    plan = module.build_cleanup_plan(tmp_path)
    planned = {path.relative_to(tmp_path) for path in [*plan.directories, *plan.files]}

    assert Path("root.log") in planned
    assert Path("image/local_models/_cache/download.log") not in planned
    assert Path("output/render.log") not in planned
    assert Path(".venv/tool.log") not in planned

