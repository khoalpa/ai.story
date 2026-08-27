from __future__ import annotations

from pathlib import Path

from studio.overview import build_overview_model


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
    assert model["pipeline"][2] == ("Video", "Chờ asset")
    assert any(action["workspace"] == "Video Studio" for action in model["actions"])


def test_overview_model_uses_dashes_when_project_has_no_data(tmp_path: Path) -> None:
    statuses = {key: "Thiếu" for key in ("story", "validation", "quality", "anchor")}
    model = build_overview_model({}, statuses, {}, output_dir=tmp_path)

    assert model["verdict"] == "Chưa đủ dữ liệu"
    assert model["metrics"][0][1] == "—"
    assert model["pipeline"][0] == ("Story", "Chưa có")
    assert model["pipeline"][1] == ("Audio", "Chưa render")
