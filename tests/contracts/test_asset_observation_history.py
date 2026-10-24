import hashlib

import pytest

from studio.asset_history import (
    content_fingerprint,
    history_path,
    load_asset_history,
    observation_status,
    record_asset_observations,
)


def _row(raw=b"image"):
    return {"name": "landscape/cover.png", "sha256": hashlib.sha256(raw).hexdigest(),
            "dimensions": (1920, 1080), "hash_verified": True, "issues": [], "notices": []}


def test_revisions_only_increase_when_image_content_changes_and_failed_checks_are_retained(tmp_path):
    root, cache = tmp_path / "package", tmp_path / "cache"
    root.mkdir()
    source = root / "story.json"
    source.write_bytes(b'{"schema_version":"4.1.3"}')
    before = source.read_bytes()
    row = _row()
    first = record_asset_observations(root, [row], "source-a", storage_directory=cache)
    record = first["assets"][row["name"]]
    assert record["revision"] == 1
    again = record_asset_observations(root, [row], "source-a", storage_directory=cache)
    assert again["assets"][row["name"]]["revision"] == 1
    changed = _row(b"new image")
    second = record_asset_observations(root, [changed], "source-b", storage_directory=cache)
    assert second["assets"][row["name"]]["revision"] == 2
    missing = {**changed, "sha256": "", "dimensions": None, "issues": ["Thiếu ảnh"]}
    third = record_asset_observations(root, [missing], "source-b", storage_directory=cache)
    latest = third["assets"][row["name"]]
    assert latest["revision"] == 2 and latest["sha256"] == changed["sha256"]
    assert latest["last_attempt"]["status"] == "failed"
    assert len(latest["revisions"]) == 2
    assert source.read_bytes() == before
    assert list(root.iterdir()) == [source]
    assert load_asset_history(root, cache) == third


def test_rechecking_unchanged_image_does_not_rebind_it_to_new_content(tmp_path):
    row = _row()
    record_asset_observations(tmp_path, [row], "source-a", storage_directory=tmp_path / "cache")
    data = record_asset_observations(tmp_path, [row], "source-b", storage_directory=tmp_path / "cache")
    record = data["assets"][row["name"]]
    assert record["source_fingerprint"] == "source-a"
    assert record["last_attempt"]["source_fingerprint"] == "source-b"
    assert "Nội dung truyện đã đổi" in observation_status(row, record, "source-b")
    assert "Ảnh đã thay đổi" in observation_status(_row(b"other"), record, "source-a")


def test_invalid_history_is_never_silently_overwritten(tmp_path):
    path = history_path(tmp_path, tmp_path)
    path.write_bytes(b'{broken')
    with pytest.raises(ValueError, match="giữ nguyên"):
        record_asset_observations(tmp_path, [_row()], "source", storage_directory=tmp_path)
    assert path.read_bytes() == b'{broken'


def test_content_fingerprint_includes_overrides_and_ignores_json_key_order(tmp_path):
    first = content_fingerprint(tmp_path, {"story": {"title": "A", "script": ["hello"]}})
    assert first == content_fingerprint(tmp_path, {"story": {"script": ["hello"], "title": "A"}})
    assert first != content_fingerprint(tmp_path, {"story": {"title": "B", "script": ["hello"]}})
    assert content_fingerprint(tmp_path, {}) == ""


def test_asset_panel_records_local_inspection_and_manifest_hashes(monkeypatch, tmp_path):
    from PIL import Image
    from streamlit.testing.v1 import AppTest

    from studio import asset_history
    from studio.project_assets import inspect_project_assets

    root = tmp_path / "package"
    (root / "landscape").mkdir(parents=True)
    image = root / "landscape" / "cover.png"
    Image.new("RGB", (1920, 1080)).save(image)
    reports = {"story": {"title": "A"}, "workflow": {"stage": 2, "files": [
        {"path": "landscape/cover.png", "sha256": hashlib.sha256(image.read_bytes()).hexdigest()},
    ]}}
    assert next(row for row in inspect_project_assets(root, reports) if row["name"] == "landscape/cover.png")["hash_verified"]
    original_path = asset_history.history_path
    monkeypatch.setattr(asset_history, "history_path", lambda project, storage_directory=None: original_path(project, tmp_path / "cache"))
    app = AppTest.from_string('''
from pathlib import Path
import streamlit as st
from studio.project_assets import render_project_assets
render_project_assets(Path(st.session_state['root']), st.session_state['reports'])
''', default_timeout=20)
    app.session_state["root"] = str(root)
    app.session_state["reports"] = reports
    app.run()
    assert not app.exception
    next(button for button in app.button if button.label == "Kiểm tra và ghi nhận ảnh hiện tại").click().run()
    assert not app.exception
    data = load_asset_history(root)
    assert data["assets"]["landscape/cover.png"]["revision"] == 1
    assert data["assets"]["landscape/cover.png"]["last_attempt"]["operation"] == "local_inspection"
    assert not (root / "asset_manifest.json").exists()
