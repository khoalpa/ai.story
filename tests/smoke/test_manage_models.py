from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODEL_STORE = ROOT / "audio" / "model_store.py"
MANAGE_MODELS = ROOT / "scripts" / "manage_models.py"


def load_model_store_module():
    spec = importlib.util.spec_from_file_location("model_store_under_test", MODEL_STORE)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_model_store_inventory_reports_sizes_and_kinds(tmp_path: Path) -> None:
    module = load_model_store_module()
    module.models_root = lambda _anchor=None: tmp_path / "models"
    anchor = tmp_path / "audio" / "fake.py"
    anchor.parent.mkdir()
    anchor.write_text("", encoding="utf-8")
    (tmp_path / "models" / "audio" / "vieneu").mkdir(parents=True)
    (tmp_path / "models" / "audio" / "vieneu" / "model.gguf").write_bytes(b"12345")
    (tmp_path / "models" / "_cache" / "image").mkdir(parents=True)
    (tmp_path / "models" / "_cache" / "image" / "blob.bin").write_bytes(b"12")

    report = module.scan_model_store(anchor, include_cache=True, max_depth=3)
    entries = {entry.relative_path: entry for entry in report.entries}

    assert entries["audio/"].kind == "provider"
    assert entries["audio/vieneu/"].kind == "model"
    assert entries["_cache/image/"].kind == "cache"
    assert report.size_bytes >= 7
    assert report.file_count >= 2


def test_model_store_remove_is_dry_run_by_default(tmp_path: Path) -> None:
    module = load_model_store_module()
    module.models_root = lambda _anchor=None: tmp_path / "models"
    anchor = tmp_path / "audio" / "fake.py"
    anchor.parent.mkdir()
    anchor.write_text("", encoding="utf-8")
    target = tmp_path / "models" / "story" / "local-model"
    target.mkdir(parents=True)
    (target / "config.json").write_text("{}", encoding="utf-8")

    resolved = module.remove_model_store_path("story/local-model", anchor)

    assert resolved == target.resolve()
    assert target.exists()

    module.remove_model_store_path("story/local-model", anchor, apply=True)

    assert not target.exists()


def test_manage_models_cli_exposes_safe_commands() -> None:
    content = MANAGE_MODELS.read_text(encoding="utf-8")
    assert "prune-empty" in content
    assert "remove" in content
    assert "--apply" in content
    assert "Dry run only" in content

