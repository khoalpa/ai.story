from __future__ import annotations

import hashlib
import json
import zipfile
from io import BytesIO

import pytest

from studio.overview import build_overview_model
from studio.project_assets import inspect_project_assets
from studio.project_review import (
    LOCAL_ZIP_SOURCE,
    VERIFICATION_ROOT_KEY,
    VERIFICATION_SOURCE_KEY,
    inspect_selected_workflow,
    review_package,
)
from studio.story_studio import load_story_package
from studio.workflow_builder import build_workflow_package, publish_package_atomic
from studio.workflow_package import (
    PURPOSES,
    STAGES,
    VALIDATION_FIELDS,
    expected_files,
    inspect_directory,
    inspect_members,
    owner_stage,
    package_digest,
    read_archive,
    read_json,
)
from studio.workflow_views import (
    video_plan_error_rows,
    video_plan_model,
    video_source_checks,
    visual_bible_summary,
)


def test_video_plan_error_rows_collapses_repeated_clip_messages() -> None:
    rows = video_plan_error_rows([
        "Clip 1: digest sai.",
        "Clip 1: span chồng lấn.",
        "Lỗi toàn kế hoạch.",
    ], 2)
    assert rows[0] == {
        "Clip": "clip_0001", "Trạng thái": "FAIL", "Lỗi": "digest sai. · span chồng lấn.",
    }
    assert rows[1]["Trạng thái"] == "PASS"
    assert rows[2]["Clip"] == "Toàn kế hoạch"


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def fixture_package(stage="STAGE1", parent=None, anchor=False):
    story = {"meta": {}, "characters": [{"character_id": "hero"}], "outline": {}, "script": []}
    members = {name: b"{}" if name.endswith(".json") else b"asset bytes" for name in expected_files(stage, story, anchor)[1:]}
    members["story.json"] = encoded(story)
    members["story_validation.json"] = encoded({"active_profile": "ADULT_STANDARD", "gates": [{"gate_id": "SAFETY", "status": "PASS"}], "summary": {}})
    if parent:
        for name in members:
            if name in parent and owner_stage(name) != stage:
                members[name] = parent[name]
    rows = [{"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw),
             "owner_stage": owner_stage(name), "mutation_status": "CREATED_CURRENT_STAGE" if owner_stage(name) == stage else "READ_ONLY"}
            for name, raw in members.items()]
    index = STAGES.index(stage)
    manifest = {"schema_version": "1.0", "package_stage": stage, "package_purpose": PURPOSES[index], "operation_mode": "CREATE",
                "created_by_prompt_version": "3.13.0", "active_profile": "ADULT_STANDARD",
                "story_sha256": hashlib.sha256(members["story.json"]).hexdigest(),
                "parent_package_digest_sha256": read_json(parent["workflow_manifest.json"])["package_digest_sha256"] if parent else None,
                "allowed_next_stage": STAGES[index + 1] if index < 3 else None, "file_count": len(members) + 1, "files": rows,
                "validation": dict.fromkeys(VALIDATION_FIELDS, "PASS"), "package_digest_sha256": package_digest(rows)}
    return {"workflow_manifest.json": encoded(manifest), **members}


def checks(result):
    return {item["check"]: item["status"] for item in result["checks"]}


def write_members(root, members):
    for name, raw in members.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)


def archive_bytes(members):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, raw in members.items():
            archive.writestr(name, raw)
    return buffer.getvalue()


def test_builder_creates_deterministic_reopened_current_package(tmp_path):
    source = fixture_package()
    files = {name: raw for name, raw in source.items() if name != "workflow_manifest.json"}
    first, inspection = build_workflow_package("STAGE1", "CREATE", files)
    second, _ = build_workflow_package("STAGE1", "CREATE", files)
    assert first == second
    assert inspection["integrity_status"] == "PASS"
    assert inspection["publish_status"] == "PASS"
    destination = tmp_path / "story.zip"
    publish_package_atomic(destination, first)
    assert destination.read_bytes() == first


def test_builder_rejects_noncanonical_file_order():
    source = fixture_package()
    files = {name: raw for name, raw in reversed(list(source.items())) if name != "workflow_manifest.json"}
    with pytest.raises(ValueError, match="canonical order"):
        build_workflow_package("STAGE1", "CREATE", files)


def test_builder_accepts_direct_parent_when_ancestor_is_unavailable():
    stage1 = fixture_package()
    stage2 = fixture_package("STAGE2", stage1)
    assert checks(inspect_members(stage2, archive=True))["parent_binding"] == "WARN"
    stage3 = fixture_package("STAGE3", stage2)
    files = {name: raw for name, raw in stage3.items() if name != "workflow_manifest.json"}

    _, inspection = build_workflow_package("STAGE3", "CREATE", files, parent=stage2)

    assert checks(inspection)["parent_binding"] == "PASS"
    assert inspection["integrity_status"] == "PASS"


@pytest.mark.parametrize("stage,count", [("STAGE1", 4), ("STAGE2", 15), ("STAGE3", 25), ("STAGE4", 26)])
def test_stage_allowlists(stage, count):
    story = {"characters": [{"character_id": "hero"}]}
    files = expected_files(stage, story, False)
    assert len(files) == count
    assert len(expected_files(stage, story, True)) == count + 1
    assert ("visual_bible.json" in files) == (stage == "STAGE2")
    assert ("video_prompts.json" in files) == (stage == "STAGE4")
    assert ("package_quality_report.json" in files) == (stage in {"STAGE3", "STAGE4"})


def test_optional_stage_certification_does_not_block_verified_package():
    members = read_archive(archive_bytes(fixture_package()))
    result = inspect_members(members, archive=True)
    assert checks(result)["file_digest"] == "PASS"
    assert checks(result)["package_digest"] == "PASS"
    assert checks(result)["archive_reopen"] == "PASS"
    assert checks(result)["stage_gate"] == "WARN"
    assert result["status"] == "PASS"
    assert result["stage_gate_status"] == "PASS"


def test_shared_local_zip_source_reopens_archive_and_matches_directory(tmp_path):
    members = fixture_package()
    write_members(tmp_path, members)
    (tmp_path / "story.zip").write_bytes(archive_bytes(members))
    state = {
        VERIFICATION_ROOT_KEY: str(tmp_path.resolve()),
        VERIFICATION_SOURCE_KEY: LOCAL_ZIP_SOURCE,
    }
    result = inspect_selected_workflow(tmp_path, state)
    assert checks(result)["archive_reopen"] == "PASS"
    assert checks(result)["source_match"] == "PASS"
    assert result["source_comparison"]["status"] == "PASS"


def test_shared_local_zip_source_rejects_directory_zip_mismatch(tmp_path):
    members = fixture_package()
    write_members(tmp_path, members)
    (tmp_path / "story.zip").write_bytes(archive_bytes(members))
    (tmp_path / "story.json").write_bytes(b'{"changed":true}')
    state = {
        VERIFICATION_ROOT_KEY: str(tmp_path.resolve()),
        VERIFICATION_SOURCE_KEY: LOCAL_ZIP_SOURCE,
    }
    result = inspect_selected_workflow(tmp_path, state)
    assert checks(result)["source_match"] == "FAIL"
    assert result["integrity_status"] == "FAIL"
    assert result["publish_status"] == "FAIL"


def test_stage4_video_prompt_failure_is_shared_with_overview_review(tmp_path):
    write_members(tmp_path, fixture_package("STAGE4", fixture_package("STAGE3", fixture_package("STAGE2", fixture_package()))))
    reports, statuses = load_story_package(tmp_path)
    review = review_package(tmp_path, reports, statuses, {})
    assert checks(review["workflow"])["video_prompt_plan"] == "FAIL"
    assert review["workflow"]["stage_gate_status"] == "FAIL"
    assert review["workflow"]["publish_status"] == "FAIL"
    assert any(issue["section"] == "Kế hoạch video" for issue in review["issues"])


@pytest.mark.parametrize("mutation,failed", [("bytes", "file_digest"), ("extra", "file_set"),
        ("missing", "file_set"), ("purpose", "manifest_schema"), ("owner", "stage_ownership"),
        ("schema", "manifest_schema"), ("count_bool", "manifest_schema")])
def test_manifest_pass_cannot_hide_mutations(mutation, failed):
    parent = fixture_package()
    members = fixture_package("STAGE2", parent)
    manifest = read_json(members["workflow_manifest.json"])
    if mutation == "bytes":
        members["story.json"] += b" "
    elif mutation == "extra":
        members["unwanted.txt"] = b"extra"
    elif mutation == "missing":
        del members["landscape/cover.png"]
    elif mutation == "purpose":
        manifest["package_purpose"] = "LANDSCAPE_CHECKPOINT"
    elif mutation == "owner":
        manifest["files"][0]["owner_stage"] = "STAGE2"
    elif mutation == "count_bool":
        manifest["file_count"] = True
    else:
        manifest["unknown"] = True
    members["workflow_manifest.json"] = encoded(manifest)
    result = inspect_members(members, archive=True, parent=parent)
    assert result["status"] == "FAIL"
    assert checks(result)[failed] == "FAIL"


@pytest.mark.parametrize(
    ("stage", "cover"),
    [("STAGE2", "landscape/cover.png"), ("STAGE3", "portrait/cover.png")],
)
def test_user_replaced_cover_warns_without_integrity_failure(stage, cover):
    parent = fixture_package("STAGE1")
    if stage == "STAGE3":
        parent = fixture_package("STAGE2", parent)
    members = fixture_package(stage, parent)
    members[cover] += b" user replacement"

    result = inspect_members(members, archive=True, parent=parent)

    assert checks(result)["file_digest"] == "WARN"
    assert checks(result)["package_digest"] == "WARN"
    assert result["integrity_status"] == "PASS"
    assert next(row for row in result["files"] if row["path"] == cover)["status"] == "WARN"


def test_parent_verification_is_optional_and_reports_mismatches_as_warnings():
    parent = fixture_package()
    members = fixture_package("STAGE2", parent)
    assert checks(inspect_members(members, archive=True))["parent_binding"] == "WARN"
    assert checks(inspect_members(members, archive=True, parent=parent))["parent_binding"] == "PASS"
    members["characters/hero.png"] += b"changed"
    manifest = read_json(members["workflow_manifest.json"])
    for row in manifest["files"]:
        raw = members[row["path"]]
        row.update(sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw))
    manifest["package_digest_sha256"] = package_digest(manifest["files"])
    members["workflow_manifest.json"] = encoded(manifest)
    result = inspect_members(members, archive=True, parent=parent)
    assert checks(result)["file_digest"] == "PASS"
    assert checks(result)["parent_binding"] == "WARN"


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/escape", "a\\b", "a/./b", "a//b", "name.", "a/"])
def test_unsafe_archive_paths_rejected(name):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("placeholder")
        info.filename = name  # Avoid Windows ZipInfo constructor normalizing backslashes.
        archive.writestr(info, b"bad")
    with pytest.raises(ValueError):
        read_archive(buffer.getvalue())


def test_duplicate_and_symlink_archive_entries_rejected():
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("story.json", b"one")
        archive.writestr("STORY.json", b"two")
    with pytest.raises(ValueError):
        read_archive(buffer.getvalue())
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        archive.writestr(info, "../target")
    with pytest.raises(ValueError):
        read_archive(buffer.getvalue())


@pytest.mark.parametrize("raw", [b'\xef\xbb\xbf{}', b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}',
    '{"e\u0301":1,"é":2}'.encode(), b'{"child":{"x":1,"x":2}}', b'{} trailing'])
def test_strict_current_json_rejects_bad_input(raw):
    with pytest.raises(ValueError):
        read_json(raw)


def test_stage1_overview_does_not_require_later_assets_or_media(tmp_path):
    members = fixture_package()
    write_members(tmp_path, members)
    reports, statuses = load_story_package(tmp_path)
    assert statuses["quality"] == "Chưa áp dụng ở stage này"
    assert statuses["video_prompts"] == "Chưa áp dụng ở stage này"
    assets = inspect_project_assets(tmp_path, reports)
    assert not any(r["group"] in {"landscape", "portrait"} for r in assets)
    model = build_overview_model(reports, statuses, {}, output_dir=tmp_path)
    assert model["workflow"]["stage"] == "STAGE1"
    assert not any(a["workspace"] in {"Audio Studio", "Video Studio"} for a in model["actions"])
    assert not any(r[0].startswith("Ảnh ·") for r in model["resources"])
    assert not model["review"]["package_ready"]


def test_stage4_labels_visual_bible_as_stage2_only_artifact(tmp_path):
    stage1 = fixture_package()
    stage2 = fixture_package("STAGE2", stage1)
    stage3 = fixture_package("STAGE3", stage2)
    write_members(tmp_path, fixture_package("STAGE4", stage3))

    _reports, statuses = load_story_package(tmp_path)

    assert statuses["visual_bible"] == "Không thuộc gói Stage 4 · chỉ dùng ở Stage 2"


def test_preview_and_directory_do_not_claim_archive_verification(tmp_path):
    write_members(tmp_path, fixture_package())
    result = inspect_directory(tmp_path, overridden=True)
    assert checks(result)["archive_reopen"] == "WARN"
    assert checks(result)["preview_override"] == "NOT_VERIFIED"


def test_missing_manifest_never_infers_current_stage():
    result = inspect_members({"story.json": b"{}", "video_prompts.json": b"{}"}, archive=True)
    assert result["stage"] is None
    assert result["compatibility"] == "MIGRATION_REQUIRED"


def test_stage4_failure_does_not_mutate_stage3():
    stage1 = fixture_package()
    stage2 = fixture_package("STAGE2", stage1)
    stage3 = fixture_package("STAGE3", stage2)
    original = dict(stage3)
    prior = inspect_members(stage3, archive=True, parent=stage2)
    stage4 = fixture_package("STAGE4", stage3)
    stage4["video_prompts.json"] = b"changed"
    assert inspect_members(stage4, archive=True, parent=stage3)["status"] == "FAIL"
    assert stage3 == original
    assert inspect_members(stage3, archive=True, parent=stage2) == prior


def test_video_plan_rejects_overlap_and_incorrect_count():
    plan = {"schema_version": "1.0", "generator_target": {}, "source_binding": {},
            "project": {"clip_count": 2, "planned_video_duration_seconds": 8, "total_story_duration_seconds": 8,
                        "coverage_mode": "FULL_STORY", "coverage_exclusions": []},
            "global_continuity_lock": {}, "clips": [{"clip_id": "clip_0001", "sequence_index": 1,
                "duration_seconds": 8, "source_script": {"start_time_seconds": 1, "end_time_seconds": 8}}], "validation": {}}
    result = video_plan_model(plan)
    assert any("clip_count" in e for e in result["errors"])
    assert any("khoảng trống" in e for e in result["errors"])


def test_optional_safety_and_no_invented_event_gates_do_not_block_export():
    from studio.video_prompt_validation import export_gate_eligible

    statuses = {
        "schema": "PASS", "source_binding": "PASS", "semantic_continuity": "PASS",
        "no_invented_event": "NOT_VERIFIED", "safety": "NOT_VERIFIED",
    }
    assert export_gate_eligible(statuses, []) is True
    assert export_gate_eligible({**statuses, "source_binding": "NOT_VERIFIED"}, []) is False
    assert export_gate_eligible(statuses, ["schema error"]) is False


@pytest.mark.parametrize("plan", [{}, {"clips": [None]}, {"clips": {}, "project": []}])
def test_video_view_handles_malformed_json_objects(plan):
    assert video_plan_model(plan)["errors"]


def test_repair_preserves_read_only_members_and_binds_same_stage():
    parent = fixture_package()
    repaired = dict(parent)
    manifest = read_json(repaired["workflow_manifest.json"])
    manifest["operation_mode"] = "REPAIR"
    manifest["parent_package_digest_sha256"] = manifest["package_digest_sha256"]
    for row in manifest["files"]:
        row["mutation_status"] = "READ_ONLY"
    repaired["workflow_manifest.json"] = encoded(manifest)
    result = inspect_members(repaired, archive=True, parent=parent)
    assert checks(result)["stage_ownership"] == "PASS"
    assert checks(result)["parent_binding"] == "PASS"
    repaired["characters/hero.png"] += b"changed"
    assert checks(inspect_members(repaired, archive=True, parent=parent))["parent_binding"] == "WARN"


def test_parent_claim_with_missing_source_bytes_cannot_bind():
    parent = fixture_package()
    child = fixture_package("STAGE2", parent)
    del parent["story.json"]
    assert checks(inspect_members(child, archive=True, parent=parent))["parent_binding"] == "WARN"


def test_extracted_directory_can_verify_against_uploaded_parent(tmp_path):
    parent = fixture_package()
    child = fixture_package("STAGE2", parent)
    write_members(tmp_path, child)

    assert checks(inspect_directory(tmp_path))["parent_binding"] == "WARN"
    assert checks(inspect_directory(tmp_path, parent=parent))["parent_binding"] == "PASS"


def test_manifest_schema_detail_names_the_actual_stage_and_purpose():
    stage1 = fixture_package()
    stage2 = fixture_package("STAGE2", stage1)
    result = inspect_members(fixture_package("STAGE3", stage2), archive=True, parent=stage2)
    detail = next(row["detail"] for row in result["checks"] if row["check"] == "manifest_schema")
    assert "STAGE3" in detail
    assert "AUDIO_STORY_RELEASE" in detail


def test_visual_bible_summary_checks_story_and_landscape_hashes(tmp_path):
    story = b'{"title":"Story"}'
    (tmp_path / "story.json").write_bytes(story)
    landscape = tmp_path / "landscape"
    landscape.mkdir()
    references = {}
    for stem in ("cover", "greeting", "opening", "introduction", "development",
                 "climax", "falling", "ending", "farewell", "outro"):
        raw = stem.encode()
        (landscape / f"{stem}.png").write_bytes(raw)
        references[f"{stem}.png"] = {
            "path": f"landscape/{stem}.png", "file_sha256": hashlib.sha256(raw).hexdigest()
        }
    document = {
        "schema_version": "2.0", "story_sha256": hashlib.sha256(story).hexdigest(),
        "active_profile": "YOUTH_SAFE", "art_direction_id": "TEST",
        "character_identity_locks": [{"character_id": "hero"}],
        "recurring_location_locks": [{"location_id": "home"}],
        "landscape_reference_map": references, "dependency_digest": "a" * 64,
    }

    summary = visual_bible_summary(document, root=tmp_path)
    assert summary["status"] == "PASS"
    assert summary["asset_passed"] == summary["asset_checked"] == 10


def test_media_render_does_not_change_workflow_verdict(tmp_path):
    write_members(tmp_path, fixture_package())
    reports, statuses = load_story_package(tmp_path)
    before = build_overview_model(reports, statuses, {}, output_dir=tmp_path)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"rendered")
    after = build_overview_model(reports, statuses, {"video_last_output": str(video)}, output_dir=tmp_path)
    assert before["workflow"] == after["workflow"]
    assert before["verdict"] == after["verdict"]


def test_video_source_checks_fail_on_changed_source_and_escaping_reference(tmp_path):
    files = {"story.json": b"story", "story_validation.json": b"validation", "package_quality_report.json": b"quality"}
    write_members(tmp_path, files)
    plan = {"source_binding": {"story_sha256": hashlib.sha256(b"old").hexdigest()},
            "clips": [{"clip_id": "clip_0001", "reference_inputs": {"character_images": ["../escape.png"]}}]}
    result = video_source_checks(plan, root=tmp_path)
    assert result[0]["Trạng thái"] == "FAIL"
    assert result[-1]["Trạng thái"] == "FAIL"


@pytest.mark.parametrize("section", ["Gói & quy trình", "Visual Bible", "Kế hoạch video"])
def test_new_story_sections_render_without_exceptions(tmp_path, section):
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_string(
        "from studio.story_studio import render_story_studio_workspace\n"
        "render_story_studio_workspace(embedded=True, show_navigation=False)", default_timeout=15,
    )
    app.session_state["story_studio_directory"] = str(tmp_path)
    app.session_state["story_studio_section"] = section
    app.run()
    assert not app.exception
    if section == "Gói & quy trình":
        (tmp_path / "story.zip").write_bytes(archive_bytes(fixture_package()))
        app.radio[0].set_value("story.zip trong thư mục").run()
        assert not app.exception
        assert len(app.dataframe) >= 2


def test_populated_but_noncanonical_video_plan_reports_errors_and_renders_timeline():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_string('''
from studio.workflow_views import render_video_plan
plan = {"schema_version":"1.0", "generator_target":{}, "source_binding":{},
 "project":{"clip_count":1, "planned_video_duration_seconds":8, "total_story_duration_seconds":8,
 "coverage_mode":"FULL_STORY", "coverage_exclusions":[]}, "global_continuity_lock":{},
 "clips":[{"clip_id":"clip_0001", "sequence_index":1, "duration_seconds":8,
 "source_script":{"start_time_seconds":0,"end_time_seconds":8}, "prompt":"Test visual prompt"}], "validation":{}}
render_video_plan(plan)
''', default_timeout=15)
    app.run()
    assert not app.exception
    assert app.error
    assert app.metric[0].value == "1"
    assert app.dataframe[0].value.iloc[0]["Clip"] == "clip_0001"
