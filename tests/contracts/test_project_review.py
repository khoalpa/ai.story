from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from studio.overview import build_overview_model
from studio.project_assets import (
    inspect_project_assets,
    inspect_report_bindings,
    project_asset_path,
)
from studio.project_context import apply_project_directory
from studio.report_semantics import display_score, gate_summary, series_required
from studio.story_studio import _prepare_overrides, load_effective_package


def standalone_validation() -> dict:
    return {"active_profile": "ADULT_STANDARD", "summary": {}, "quality": {}, "engagement": {}, "scene_zone_map": [],
            "gates": [{"gate_id": "SAFETY", "status": "PASS"}, {
                "gate_id": "CONTINUITY_PORTABILITY", "status": "NOT_APPLICABLE",
                "metrics": {"applicability_reason": "standalone story"},
            }]}


def test_standalone_gate_is_not_a_failure_but_serial_gate_cannot_be_waived() -> None:
    report = standalone_validation()
    assert gate_summary(report)["ready"]
    assert gate_summary(report)["skipped"] == 1
    assert not series_required(report)
    report["active_profile"] = "SERIAL_DETECTIVE"
    assert not gate_summary(report)["ready"]
    assert series_required(report)


@pytest.mark.parametrize("mutation", ["no_reason", "safety", "unverified", "malformed"])
def test_gate_interpretation_fails_closed(mutation: str) -> None:
    report = standalone_validation()
    if mutation == "no_reason":
        report["gates"][1]["metrics"] = {}
    elif mutation == "safety":
        report["gates"][1]["gate_id"] = "SAFETY"
    elif mutation == "unverified":
        report["gates"][0]["status"] = "NOT_VERIFIED"
    else:
        report["gates"].append(None)
    assert not gate_summary(report)["ready"]


@pytest.mark.parametrize(("value", "expected"), [(94, "9.4/10"), (9.4, "9.4/10"), (0, "0.0/10"),
    (None, "—"), (float("nan"), "—"), (-1, "—"), (True, "—"), (101, "—")])
def test_score_normalization_handles_missing_invalid_and_legacy(value, expected) -> None:
    assert display_score(value) == expected


def test_uploaded_story_survives_widget_cleanup_and_never_leaks_to_other_project(tmp_path: Path) -> None:
    original = {"meta": {"title": "Disk"}, "characters": [], "outline": {}, "script": []}
    (tmp_path / "story.json").write_text(json.dumps(original), encoding="utf-8")
    state = {}
    overrides = _prepare_overrides(state, tmp_path)
    uploaded = {**original, "meta": {"title": "Upload"}}
    overrides["story"] = json.dumps(uploaded).encode()
    reports, statuses = load_effective_package(tmp_path, state)
    assert reports["story"]["meta"]["title"] == "Upload"
    assert "tệp thay thế" in statuses["story"]
    other = tmp_path / "other"
    other.mkdir()
    assert "story" not in load_effective_package(other, state)[0]
    _prepare_overrides(state, other)
    assert not state["story_overrides"]
    assert json.loads((tmp_path / "story.json").read_text())["meta"]["title"] == "Disk"


def test_invalid_override_is_not_silently_replaced_with_disk_report(tmp_path: Path) -> None:
    (tmp_path / "story.json").write_text(json.dumps({"meta": {}, "characters": [], "outline": {}, "script": []}))
    state = {}
    _prepare_overrides(state, tmp_path)["story"] = b"broken"
    reports, statuses = load_effective_package(tmp_path, state)
    assert "story" not in reports
    assert statuses["story"].startswith("Không hợp lệ")


def test_bindings_compare_exact_uploaded_bytes_not_disk(tmp_path: Path) -> None:
    (tmp_path / "story.json").write_bytes(b"old")
    reports = {"validation": {"story_sha256": hashlib.sha256(b"new").hexdigest()}}
    assert "đã cũ" in inspect_report_bindings(tmp_path, reports)[0]["status"]
    assert inspect_report_bindings(tmp_path, reports, story_bytes=b"new")[0]["status"] == "Khớp kịch bản"


def test_asset_changes_invalidate_cached_hash_and_path_escape_is_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "characters"
    directory.mkdir()
    image = directory / "hero.png"
    Image.new("RGB", (8, 8), "red").save(image)
    reports = {"story": {"characters": [{"character_id": "hero", "reference_asset": {
        "reference_image": "characters/hero.png", "file_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        "dimensions": {"width": 8, "height": 8},
    }}]}}
    def hero():
        return next(row for row in inspect_project_assets(tmp_path, reports) if row["group"] == "characters")
    assert hero()["hash_verified"]
    Image.new("RGB", (9, 9), "blue").save(image)
    assert "Hash không khớp báo cáo" in hero()["issues"]
    assert "Sai kích thước" in hero()["issues"]
    assert project_asset_path(tmp_path, "../outside.png") is None


@pytest.mark.parametrize("group", ["landscape", "portrait"])
def test_user_replaced_cover_is_notice_not_asset_error(tmp_path: Path, group: str) -> None:
    directory = tmp_path / group
    directory.mkdir()
    image = directory / "cover.png"
    dimensions = (3840, 2160) if group == "landscape" else (1080, 1920)
    Image.new("RGB", dimensions, "blue").save(image)
    reports = {
        "workflow": {"package_stage": "STAGE3"},
        "quality": {"image_evidence": {"asset_results": [{
            "path": f"{group}/cover.png",
            "file_sha256": hashlib.sha256(b"original cover").hexdigest(),
            "dimensions": {"width": dimensions[0], "height": dimensions[1]},
        }]}},
    }

    row = next(item for item in inspect_project_assets(tmp_path, reports) if item["name"] == f"{group}/cover.png")

    assert row["issues"] == []
    assert row["notices"] == ["Ảnh cover đã được người dùng thay đổi"]
    assert not row["hash_verified"]


def test_overview_standalone_not_blocked_and_cannot_publish_without_verified_video(tmp_path: Path) -> None:
    reports = {"story": {"meta": {}}, "validation": standalone_validation(), "quality": {"summary": {"publish_verdict": "PASS"}}}
    model = build_overview_model(reports, {"anchor": "Thiếu"}, {}, output_dir=tmp_path)
    assert model["pipeline"][0] == ("Story", "Đạt")
    assert model["pipeline"][-1] == ("Media đầu ra", "Chưa đủ kiểm định")
    assert not any("Bổ sung dữ liệu: Series" in action["text"] for action in model["actions"])
    video = tmp_path / "video.mp4"
    video.write_bytes(b"unverified")
    model = build_overview_model(reports, {}, {"video_last_output": str(video)}, output_dir=tmp_path)
    assert model["verdict"] != "Sẵn sàng xuất bản"


def test_stale_validation_blocks_story_and_provides_targeted_action(tmp_path: Path) -> None:
    (tmp_path / "story.json").write_bytes(b"changed")
    reports = {"story": {"meta": {}}, "validation": {**standalone_validation(), "story_sha256": "old"}}
    model = build_overview_model(reports, {}, {}, output_dir=tmp_path)
    assert model["pipeline"][0] == ("Story", "Cần xử lý")
    assert any(a.get("section") == "Kiểm định" and "đã cũ" in a["text"] for a in model["actions"])


def test_project_switch_clears_previous_render_results(tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    state = {}
    apply_project_directory(state, tmp_path)
    state.update(last_result_summary={"out_file": "old.wav"}, video_last_output="old.mp4")
    apply_project_directory(state, other)
    assert "last_result_summary" not in state
    assert "video_last_output" not in state


def test_ui_uses_same_override_when_navigating_to_evidence(tmp_path: Path) -> None:
    from streamlit.testing.v1 import AppTest

    story = {"meta": {"title": "Uploaded story"}, "characters": [], "outline": {},
             "script": [{"zone": "OPENING", "voice": "NARRATOR", "text": "Uploaded evidence text."}]}
    validation = standalone_validation()
    validation["quality"] = {"final_story_quality_score": 94, "dimension_scores": {"story_intent": 2}}
    validation["engagement"] = {"engagement_score": 94}
    validation["gates"][0]["evidence_locators"] = ["script:0-0"]
    (tmp_path / "story_validation.json").write_text(json.dumps(validation))
    app = AppTest.from_string(
        "from studio.story_studio import render_story_studio_workspace\n"
        "render_story_studio_workspace(embedded=True, show_navigation=False)", default_timeout=15,
    )
    app.session_state["story_studio_directory"] = str(tmp_path)
    app.session_state["story_override_root"] = str(tmp_path.resolve())
    app.session_state["story_overrides"] = {"story": json.dumps(story).encode()}
    app.session_state["story_studio_section"] = "Kiểm định"
    app.run()
    assert not app.exception
    assert next(m.value for m in app.metric if m.label == "Chất lượng") == "9.4/10"
    next(b for b in app.button if b.label == "Mở đoạn kịch bản").click().run()
    assert not app.exception
    assert app.session_state["story_studio_section"] == "Nội dung"
    assert any("Uploaded evidence text." in m.value for m in app.markdown)
    assert "story" in app.session_state["story_overrides"]
