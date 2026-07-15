from __future__ import annotations

import shutil
from pathlib import Path

import pytest


def test_story_audio_handoff_survives_bundle_move(tmp_path: Path) -> None:
    from audio.handoff import read_story_handoff
    from story.handoff import write_handoff

    bundle = tmp_path / "source"
    bundle.mkdir()
    script = bundle / "story.txt"
    script.write_text("plain", encoding="utf-8")
    write_handoff(bundle / "manifest.json", kind="story.audio-handoff", artifacts={"plain_script": script})
    moved = tmp_path / "moved"
    shutil.move(str(bundle), moved)
    parsed = read_story_handoff(moved / "manifest.json")
    assert parsed.plain_script.read_text(encoding="utf-8") == "plain"


def test_story_image_handoff_survives_bundle_move(tmp_path: Path) -> None:
    from image.handoff import read_story_handoff
    from story.handoff import write_handoff

    bundle = tmp_path / "source"
    prompts = bundle / "prompts"
    prompts.mkdir(parents=True)
    write_handoff(bundle / "manifest.json", kind="story.image-handoff", artifacts={"prompt_dir": prompts})
    moved = tmp_path / "moved"
    shutil.move(str(bundle), moved)
    assert read_story_handoff(moved / "manifest.json").prompt_dir == moved / "prompts"


def test_audio_and_image_video_handoffs_are_consumed_locally(tmp_path: Path) -> None:
    from audio.handoff import write_video_handoff as write_audio
    from image.handoff import write_video_handoff as write_image
    from video.handoff import read_audio_handoff, read_image_handoff

    audio = tmp_path / "audio" / "story.mp3"
    audio.parent.mkdir()
    audio.touch()
    audio_manifest = write_audio(audio.parent / "manifest.json", audio=audio)
    assert read_audio_handoff(audio_manifest).audio == audio

    scenes = tmp_path / "images" / "scenes"
    scenes.mkdir(parents=True)
    image_manifest = write_image(scenes.parent / "manifest.json", cover=None, scenes=scenes)
    assert read_image_handoff(image_manifest).scenes == scenes


def test_handoff_rejects_wrong_kind_and_version(tmp_path: Path) -> None:
    from audio.handoff import read_story_handoff

    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"schema_version": 2, "kind": "story.image-handoff", "artifacts": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="story.audio-handoff"):
        read_story_handoff(manifest)
