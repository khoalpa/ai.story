from __future__ import annotations

from pathlib import Path

from PIL import Image

from studio.overview import build_overview_model
from studio.story_images import EXPECTED_IMAGE_STEMS


def test_overview_model_combines_story_reports_and_pipeline_outputs(tmp_path: Path) -> None:
    audio = tmp_path / "story.mp3"
    subtitle = tmp_path / "story.srt"
    audio.write_bytes(b"audio")
    subtitle.write_text("subtitle", encoding="utf-8")
    reports = {
        "story": {
            "meta": {
                "title": "Chuyện thử",
                "episode": 2,
                "story_quality_commitment": {
                    "recomputable_metrics": {
                        "total_words": 1200,
                        "estimated_duration_minutes": 8.5,
                        "narrative_scene_count": 4,
                    },
                    "committed_quality_metrics": {"final_story_quality_score": 92},
                },
            }
        },
        "validation": {"summary": {"material_defect_remaining_count": 0}, "gates": []},
    }
    statuses = {"story": "Có dữ liệu", "validation": "Có dữ liệu", "quality": "Thiếu", "anchor": "Thiếu"}
    state = {"last_result_summary": {"out_file": str(audio), "srt_path": str(subtitle), "audio_format": "mp3"}}

    model = build_overview_model(reports, statuses, state, output_dir=tmp_path)

    assert model["project_label"] == "Chuyện thử · Tập 2"
    assert ("Chất lượng truyện", "9.2/10") in model["metrics"]
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


def test_overview_uses_current_scenes_directory_and_canonical_image_count(tmp_path: Path) -> None:
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
