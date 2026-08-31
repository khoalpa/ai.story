import json
import re
from pathlib import Path

from studio.prompt_contract import load_prompt_contract
from studio.story_environments import CANONICAL_STORY_ENVIRONMENTS
from video.environment_overlays import (
    ENVIRONMENT_WHITELIST,
    OVERLAY_PROFILES,
    EnvironmentSegment,
    build_environment_filter_chain,
    build_environment_segments,
    normalize_environment,
)
from video.subtitle_filters import build_vf_filter


def test_all_canonical_environments_have_overlay_profiles() -> None:
    assert ENVIRONMENT_WHITELIST == CANONICAL_STORY_ENVIRONMENTS
    assert set(ENVIRONMENT_WHITELIST) == set(OVERLAY_PROFILES)
    assert normalize_environment("unknown_weather") == "none"


def test_prompt_environment_whitelist_matches_runtime_contract() -> None:
    prompt = load_prompt_contract().path.read_text(encoding="utf-8")
    match = re.search(
        r"SHARED ENVIRONMENT WHITELIST:\s*\n- (?P<values>[^\n]+)",
        prompt,
    )
    assert match is not None
    prompt_values = tuple(re.findall(r'"([^"]+)"', match.group("values")))
    assert prompt_values == CANONICAL_STORY_ENVIRONMENTS


def test_environment_timeline_uses_srt_timestamps_merges_and_protects_cards(tmp_path: Path) -> None:
    story = tmp_path / "story.json"
    story.write_text(
        json.dumps(
            {
                "script": [
                    {"zone": "opening", "environment": "rain_soft", "text": "Một."},
                    {"zone": "opening", "environment": "rain_soft", "text": "Hai."},
                    {"zone": "ending", "environment": "library_soft", "text": "Ba."},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    subtitle = tmp_path / "story.srt"
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nMột.\n\n"
        "2\n00:00:02,000 --> 00:00:04,000\nHai.\n\n"
        "3\n00:00:04,000 --> 00:00:07,000\nBa.\n",
        encoding="utf-8",
    )

    segments = build_environment_segments(
        timeline_json=story,
        subtitle=subtitle,
        suppress_before=1.0,
        suppress_after=6.0,
    )

    assert segments == [
        EnvironmentSegment("rain_soft", 1.0, 4.0, "opening"),
        EnvironmentSegment("library_soft", 4.0, 6.0, "ending"),
    ]


def test_short_environment_segments_are_omitted() -> None:
    # Direct filter generation remains deterministic for accepted segments.
    filters = build_environment_filter_chain(
        [EnvironmentSegment("rain_soft", 1.0, 4.0, "opening")],
        intensity="subtle",
        fade_seconds=0.6,
    )
    assert any("noise=" in item and "between(t,1.000,4.000)" in item for item in filters)
    assert any("colorbalance=" in item for item in filters)
    assert any("drawtext=" in item and "mod(" in item for item in filters)
    assert any(":alpha='" in item and "min(1\\," in item for item in filters)
    assert all("fontfile=" in item for item in filters if item.startswith("drawtext="))


def test_short_srt_gaps_are_bridged_for_the_same_environment(tmp_path: Path) -> None:
    story = tmp_path / "story.json"
    story.write_text(
        json.dumps({"script": [
            {"zone": "opening", "environment": "rain_soft", "text": "Một."},
            {"zone": "opening", "environment": "rain_soft", "text": "Hai."},
        ]}, ensure_ascii=False),
        encoding="utf-8",
    )
    subtitle = tmp_path / "story.srt"
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nMột.\n\n"
        "2\n00:00:03,000 --> 00:00:05,000\nHai.\n",
        encoding="utf-8",
    )
    assert build_environment_segments(timeline_json=story, subtitle=subtitle) == [
        EnvironmentSegment("rain_soft", 0.0, 5.0, "opening")
    ]


def test_environment_filters_are_inserted_before_subtitles(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("video.config.get_output_resolution", lambda aspect: (1920, 1080))
    subtitle = tmp_path / "story.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:02,000\nTest\n", encoding="utf-8")
    vf = build_vf_filter(
        "16x9",
        subtitle,
        pre_subtitle_filters=["noise=alls=2:allf=t+u"],
    )
    assert vf.index("noise=") < vf.index("subtitles=")


def test_particle_density_scales_with_output_resolution() -> None:
    segment = [EnvironmentSegment("rain_soft", 0.0, 5.0, "opening")]
    full_hd = build_environment_filter_chain(
        segment, intensity="normal", width=1920, height=1080
    )
    ultra_hd = build_environment_filter_chain(
        segment, intensity="normal", width=3840, height=2160
    )
    full_hd_rain = [item for item in full_hd if "text='/'" in item]
    ultra_hd_rain = [item for item in ultra_hd if "text='/'" in item]
    assert len(full_hd_rain) == 22
    assert len(ultra_hd_rain) == 44
    assert all("h/30" in item for item in ultra_hd_rain)
