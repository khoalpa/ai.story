from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from studio.overview import build_overview_model, workflow_verdict
from studio.project_context import project_directory_has_files
from studio.story_images import EXPECTED_IMAGE_STEMS
from studio.workflow_views import workflow_stage_caption


@pytest.mark.parametrize("status,message,kind", [
    ("PASS", "Gói đạt các phép kiểm tra đã chạy", "success"),
    ("PARTIAL", "Gói đã kiểm định nhưng chưa hoàn tất", "warning"),
    ("NOT_VERIFIED", "Gói chưa được xác minh đầy đủ", "warning"),
    ("FAIL", "Gói có lỗi cần xử lý", "error"),
])
def test_workflow_status_drives_overview_banner_and_stage_caption(status, message, kind):
    assert workflow_verdict(status) == (message, kind)
    caption = workflow_stage_caption("STAGE4", "STAGE4", status)
    if status == "PASS":
        assert "đạt các phép kiểm tra đã chạy" in caption
        assert "chưa xác minh" not in caption
    elif status == "FAIL":
        assert "có lỗi" in caption
    elif status == "PARTIAL":
        assert "chưa hoàn tất" in caption
    else:
        assert "chưa xác minh đầy đủ" in caption


def test_workflow_stage_caption_distinguishes_completed_current_and_future_stages():
    assert workflow_stage_caption("STAGE1", "STAGE3", "PASS") == "Đã hoàn thành · dữ liệu có trong gói hiện tại"
    assert workflow_stage_caption("STAGE3", "STAGE3", "PASS") == "Stage hiện tại · đạt các phép kiểm tra đã chạy"
    assert workflow_stage_caption("STAGE4", "STAGE3", "PASS") == "Chưa thực hiện"


def test_overview_model_combines_story_reports_and_pipeline_outputs(tmp_path: Path) -> None:
    audio = tmp_path / "story.mp3"
    subtitle = tmp_path / "story.srt"
    audio.write_bytes(b"audio")
    subtitle.write_text("subtitle", encoding="utf-8")
    reports = {
        "story": {
            "schema_version": "4.1.3",
            "meta": {
                "title": "Chuyện thử",
                "episode": 2,
                "estimated_minutes": 8.5,
            }
            ,"outline": [{"scene_id": f"sc{i}"} for i in range(4)]
            ,"script": [{"text": "một hai ba"}]
        },
        "validation": {"prompt_version": "4.1.6", "status": "COMPLETE", "checks": [
            {"id": "SCHEMA_LINKS", "status": "PASS"}
        ], "limitations": [], "remaining_work": []},
    }
    statuses = {"story": "Có dữ liệu", "validation": "Có dữ liệu", "quality": "Thiếu", "anchor": "Thiếu"}
    state = {"last_result_summary": {"out_file": str(audio), "srt_path": str(subtitle), "audio_format": "mp3"}}

    model = build_overview_model(reports, statuses, state, output_dir=tmp_path)

    assert model["project_label"] == "Chuyện thử · Tập 2"
    assert ("Kiểm định", "1/1") in model["metrics"]
    assert ("Số cảnh", "4") in model["metrics"]
    assert model["pipeline"][1] == ("Audio", "Đã render")
    assert model["pipeline"][2] == ("Handoff", "Chưa có")
    assert model["pipeline"][3] == ("Video", "Chờ asset")
    assert any(action["workspace"] == "Video Studio" for action in model["actions"])


def test_overview_model_uses_dashes_when_project_has_no_data(tmp_path: Path) -> None:
    statuses = {key: "Thiếu" for key in ("story", "validation", "quality", "anchor")}
    model = build_overview_model({}, statuses, {}, output_dir=tmp_path)

    assert model["verdict"] == "Chưa đủ dữ liệu"
    assert model["metrics"][0][1] == "—"
    assert model["pipeline"][0] == ("Story", "Chưa có")
    assert model["pipeline"][1] == ("Audio", "Chưa render")
    assert model["pipeline"][2] == ("Handoff", "Chưa có")
    assert model["package_versions"] == [
        ("prompt_version", "—"),
        ("schema_version", "—"),
        ("image_prompt_version", "—"),
    ]


def test_overview_exposes_selected_package_versions(tmp_path: Path) -> None:
    reports = {
        "workflow": {"prompt_version": "5.2.0", "schema_version": "5.0.0"},
        "story": {"schema_version": "4.1.3"},
        "validation": {"prompt_version": "4.2.0"},
        "image_prompts": {"image_prompt_version": "1.1"},
    }

    model = build_overview_model(reports, {}, {}, output_dir=tmp_path)

    assert model["package_versions"] == [
        ("prompt_version", "5.2.0"),
        ("schema_version", "5.0.0"),
        ("image_prompt_version", "1.1"),
    ]


def test_overview_treats_directory_without_files_as_empty(tmp_path: Path) -> None:
    (tmp_path / "landscape").mkdir()

    assert not project_directory_has_files(tmp_path)

    (tmp_path / "landscape" / "cover.png").write_bytes(b"image")

    assert project_directory_has_files(tmp_path)


def test_overview_renders_empty_directory_message_before_package_loading() -> None:
    source = Path("studio/overview.py").read_text(encoding="utf-8")
    empty_state = source.index('"Thư mục dự án đang trống"')
    package_loading = source.index("load_effective_package(output_dir", empty_state)
    assert empty_state < package_loading


def test_overview_exposes_atomic_stage_completion_action() -> None:
    source = Path("studio/overview.py").read_text(encoding="utf-8")

    assert "plan_stage_completion(output_dir)" in source
    assert "complete_stage_atomic(output_dir)" in source
    assert "Xác minh và hoàn tất" in source
    assert "restore_integrity_backup(output_dir" in source


def test_overview_uses_current_production_settings_before_first_render(tmp_path: Path) -> None:
    state = {
        "audio_production_settings": {
            "tts_provider": "vieneu",
            "audio_format": "wav",
            "pacing_preset": "story",
            "loudness_profile": "youtube",
            "bgm": "cinematic",
        },
        "video_production_settings": {
            "mode": "slideshow",
            "aspect": "16x9",
            "encoding_profile": "youtube_1080p",
            "video_fps": 30,
            "show_subtitles": True,
        },
    }

    model = build_overview_model({}, {}, state, output_dir=tmp_path)

    assert model["audio"]["TTS provider"] == "vieneu"
    assert model["audio"]["Định dạng"] == "WAV"
    assert model["video"]["Chế độ"] == "slideshow"
    assert model["video"]["FPS"] == 30
    assert model["video"]["Phụ đề"] == "Bật"


def test_completed_run_overrides_current_production_settings(tmp_path: Path) -> None:
    state = {
        "audio_production_settings": {"audio_format": "wav", "tts_provider": "edge"},
        "last_result_summary": {"audio_format": "mp3", "tts_provider": "vieneu"},
        "video_production_settings": {"aspect": "16x9"},
        "video_last_summary": {"aspect": "9x16"},
    }

    model = build_overview_model({}, {}, state, output_dir=tmp_path)

    assert model["audio"]["Định dạng"] == "MP3"
    assert model["audio"]["TTS provider"] == "vieneu"
    assert model["video"]["Tỷ lệ"] == "9x16"


def test_overview_restores_production_settings_from_persisted_quality_reports(tmp_path: Path) -> None:
    reports = {
        "audio_quality": {
            "audio_file": str(tmp_path / "story.wav"),
            "target": {"integrated_lufs": -16.0, "true_peak_dbtp": -1.5},
            "pacing": {"preset": "natural"},
            "mix": {"bgm_ducking_enabled": True},
            "segments": {"measured_count": 81},
        },
        "video_deliveries": {
            "video_landscape": {
                "quality": {
                    "video_stream": {
                        "codec_name": "h264", "profile": "High", "pix_fmt": "yuv420p",
                        "display_aspect_ratio": "16:9", "avg_frame_rate": "24/1",
                    },
                    "subtitle": {"present": True},
                },
            },
        },
    }

    model = build_overview_model(reports, {}, {}, output_dir=tmp_path)

    assert model["audio"]["Định dạng"] == "WAV"
    assert model["audio"]["Pacing"] == "natural"
    assert model["audio"]["Loudness"] == "-16 LUFS · -1.5 dBTP"
    assert model["audio"]["Nhạc nền"] == "Bật"
    assert model["audio"]["Segments"] == 81
    assert model["video"]["Tỷ lệ"] == "16:9"
    assert model["video"]["Encoding"] == "H264 · High · yuv420p"
    assert model["video"]["FPS"] == 24
    assert model["video"]["Phụ đề"] == "Bật"


def test_overview_uses_current_scenes_directory_and_canonical_image_count(tmp_path: Path) -> None:
    (tmp_path / "visual_plan.json").write_text(json.dumps({"image_mode": "ZONE", "targets": {
        "landscape": {"size_policy": "MODEL_DEFAULT"}, "portrait": {"size_policy": "MODEL_DEFAULT"}},
        "assets": [{"basename": f"{stem}.png"} for stem in EXPECTED_IMAGE_STEMS]}), encoding="utf-8")
    landscape = tmp_path / "landscape"
    landscape.mkdir()
    for stem in EXPECTED_IMAGE_STEMS:
        Image.new("RGB", (8, 8)).save(landscape / f"{stem}.png")
    reports = {
        "story": {
            "meta": {
                "story_quality_commitment": {
                    "recomputable_metrics": {"narrative_scene_count": 11}
                }
            }
        }
    }
    state = {
        "video_production_settings": {"aspect": "16x9"},
        "video_input_scenes_dir": str(landscape),
    }

    model = build_overview_model(reports, {}, state, output_dir=tmp_path)

    assert model["video"]["Ảnh · Landscape"] == "10/10"
    assert not any(row[0] == "Ảnh cảnh" for row in model["resources"])
    landscape_row = next(row for row in model["resources"] if row[0] == "Ảnh · Landscape")
    assert landscape_row[1:3] == ("Đủ file", "10/10 ảnh")
    assert landscape_row[3] == str(landscape)


def test_overview_selects_portrait_image_set_from_video_aspect(tmp_path: Path) -> None:
    (tmp_path / "visual_plan.json").write_text(json.dumps({"image_mode": "ZONE", "targets": {
        "landscape": {"size_policy": "MODEL_DEFAULT"}, "portrait": {"size_policy": "MODEL_DEFAULT"}},
        "assets": [{"basename": f"{stem}.png"} for stem in EXPECTED_IMAGE_STEMS]}), encoding="utf-8")
    portrait = tmp_path / "portrait"
    portrait.mkdir()
    for stem in EXPECTED_IMAGE_STEMS[:3]:
        Image.new("RGB", (8, 8)).save(portrait / f"{stem}.png")

    model = build_overview_model(
        {}, {},
        {
            "video_production_settings": {"aspect": "9x16"},
            "video_input_scenes_dir": str(portrait),
        },
        output_dir=tmp_path,
    )

    assert model["video"]["Ảnh · Portrait"] == "3/10"


def test_overview_ignores_missing_production_statuses_when_listing_story_reports(
    tmp_path: Path,
) -> None:
    statuses = {
        "story": "Có dữ liệu",
        "validation": "Có dữ liệu",
        "quality": "Có dữ liệu",
        "anchor": "Có dữ liệu",
        "handoff": "Thiếu",
        "audio_quality": "Thiếu",
        "subtitle": "Thiếu",
        "video_landscape.result.json": "Thiếu",
    }

    model = build_overview_model({}, statuses, {}, output_dir=tmp_path)

    assert not any("Bổ sung dữ liệu" in action["text"] for action in model["actions"])


def test_overview_surfaces_repeated_sentence_count_and_action(tmp_path: Path) -> None:
    repeated = "Minh An bước vào căn phòng tối và nhìn quanh."
    reports = {
        "story": {
            "meta": {},
            "script": [
                {"zone": "OPENING", "voice": "NARRATOR", "text": repeated},
                {"zone": "ENDING", "voice": "NARRATOR", "text": repeated},
            ],
        }
    }
    statuses = {key: "Có dữ liệu" for key in ("story", "validation", "quality", "anchor")}

    model = build_overview_model(reports, statuses, {}, output_dir=tmp_path)

    assert ("Câu lặp cần xem", "2") in model["metrics"]
    assert any("1 cặp câu lặp" in action["text"] for action in model["actions"])


def test_overview_navigation_uses_button_callback_instead_of_late_widget_mutation() -> None:
    source = Path("studio/overview.py").read_text(encoding="utf-8")
    assert "on_click=open_workspace" in source
    assert 'if button_col.button(f"Mở {action[\'workspace\']}"' not in source


def test_overview_consolidates_integrity_failures_into_one_action(tmp_path: Path, monkeypatch) -> None:
    workflow = {
        "stage": "STAGE3",
        "status": "FAIL",
        "overall_status": "FAIL",
        "integrity_status": "FAIL",
        "stage_gate_status": "FAIL",
        "publish_status": "FAIL",
        "checks": [{
            "check": "file_digest",
            "status": "FAIL",
            "detail": "Payload không khớp manifest: story.json (sai SHA-256).",
        }],
        "manifest": {"status": "COMPLETE"},
    }
    review = {
        "workflow": workflow,
        "issues": [{
            "section": "Gói & quy trình",
            "text": "file_digest: Payload không khớp manifest: story.json (sai SHA-256).",
        }],
        "assets": [],
        "asset_issues": [],
        "story_ready": False,
        "package_ready": False,
    }
    monkeypatch.setattr("studio.overview.review_package", lambda *_args, **_kwargs: review)

    model = build_overview_model({}, {}, {}, output_dir=tmp_path)

    assert len(model["actions"]) == 1
    action = model["actions"][0]
    assert action["section"] == "Gói & quy trình"
    assert "xem trước thay đổi" in action["text"]
    assert "tạo bản sao lưu" in action["text"]
    assert "story.json (sai SHA-256)" in action["text"]
    assert "Hoàn tất kiểm định STAGE3" not in action["text"]


def test_overview_explains_video_variants_that_are_not_ready(tmp_path: Path) -> None:
    reports = {
        "video_deliveries": {
            "video_landscape": {},
            "video_portrait": {},
        }
    }

    model = build_overview_model(reports, {}, {}, output_dir=tmp_path)

    video_state = next(row for row in model["progress_states"] if row["label"] == "Video")
    assert video_state == {
        "label": "Video",
        "status": "0/2 đạt",
        "tone": "warning",
        "reason": "Chưa đạt: Landscape, Portrait.",
    }
    assert [row["label"] for row in model["video_failure_details"]] == ["Landscape", "Portrait"]
    assert "Thiếu `video_landscape.result.json`." in model["video_failure_details"][0]["reasons"]


def test_overview_does_not_infer_success_from_status_text_suffix() -> None:
    source = Path("studio/overview.py").read_text(encoding="utf-8")

    assert 'status.endswith(" đạt")' not in source
    assert 'progress_icons = {"success": "✓", "warning": "!", "error": "✕", "neutral": "○"}' in source
