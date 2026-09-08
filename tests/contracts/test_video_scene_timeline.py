from __future__ import annotations

import json
from pathlib import Path

import pytest

from video.scene_timeline import build_scene_segments, resolve_slideshow_timeline_mode
from video.validation import collect_scene_images


def _write_fixture(root: Path, *, mode: str = "SCENE") -> tuple[Path, Path, Path, Path]:
    story = root / "story.json"
    plan = root / "visual_plan.json"
    subtitle = root / "story.srt"
    scenes = root / "landscape"
    scenes.mkdir()
    story.write_text(
        json.dumps({"script": [
            {"zone": "OPENING", "text": "First scene."},
            {"zone": "DEVELOPMENT", "text": "Second scene."},
        ]}),
        encoding="utf-8",
    )
    plan.write_text(
        json.dumps({
            "resolved_mode": mode,
            "assets": [
                {"basename": "cover.png", "role": "COVER"},
                {"basename": "scene_0001.png", "role": "SCENE", "zone": "OPENING", "script_item_start": 0, "script_item_end": 0},
                {"basename": "scene_0002.png", "role": "SCENE", "zone": "DEVELOPMENT", "script_item_start": 1, "script_item_end": 1},
            ],
        }),
        encoding="utf-8",
    )
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nFirst scene.\n\n"
        "2\n00:00:02,000 --> 00:00:05,000\nSecond scene.\n",
        encoding="utf-8",
    )
    (scenes / "scene_0001.png").write_bytes(b"scene-one")
    (scenes / "scene_0002.png").write_bytes(b"scene-two")
    return story, plan, subtitle, scenes


def test_scene_images_are_current_assets_not_removed_legacy_files(tmp_path: Path) -> None:
    _, _, _, scenes = _write_fixture(tmp_path)
    (scenes / "scene.png").write_bytes(b"legacy")

    assert [path.name for path in collect_scene_images(scenes)] == [
        "scene_0001.png",
        "scene_0002.png",
    ]


def test_build_scene_segments_uses_visual_plan_script_spans(tmp_path: Path) -> None:
    story, plan, subtitle, scenes = _write_fixture(tmp_path)

    segments = build_scene_segments(
        timeline_json=story,
        visual_plan_json=plan,
        subtitle=subtitle,
        scenes_dir=scenes,
    )

    assert [(item.image.name, item.start, item.end) for item in segments] == [
        ("scene_0001.png", 0.0, 2.0),
        ("scene_0002.png", 2.0, 5.0),
    ]


def test_scene_timeline_rejects_zone_visual_plan(tmp_path: Path) -> None:
    story, plan, subtitle, scenes = _write_fixture(tmp_path, mode="ZONE")

    with pytest.raises(ValueError, match="mode SCENE"):
        build_scene_segments(
            timeline_json=story,
            visual_plan_json=plan,
            subtitle=subtitle,
            scenes_dir=scenes,
        )


def test_auto_timeline_uses_scene_plan_and_otherwise_preserves_fixed_mode(tmp_path: Path) -> None:
    _, plan, _, _ = _write_fixture(tmp_path)

    assert resolve_slideshow_timeline_mode("auto", plan) == "scene"
    assert resolve_slideshow_timeline_mode("auto", None) == "fixed"
