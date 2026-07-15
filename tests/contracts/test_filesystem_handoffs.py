from __future__ import annotations

import shutil
import json
from types import SimpleNamespace
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
    descriptor = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))["artifacts"]["plain_script"]
    assert descriptor["media_type"] == "text/plain"
    assert descriptor["size_bytes"] == 5
    assert len(descriptor["sha256"]) == 64
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


def test_handoff_detects_modified_artifact(tmp_path: Path) -> None:
    from audio.handoff import write_video_handoff
    from video.handoff import read_audio_handoff

    audio = tmp_path / "story.mp3"
    audio.write_bytes(b"original")
    manifest = write_video_handoff(tmp_path / "manifest.json", audio=audio)
    audio.write_bytes(b"modified")
    with pytest.raises(ValueError, match="checksum mismatch"):
        read_audio_handoff(manifest)


def test_video_cli_direct_inputs_override_manifests(tmp_path: Path) -> None:
    from audio.handoff import write_video_handoff as write_audio
    from image.handoff import write_video_handoff as write_image
    from video.app_api import request_from_args

    manifest_audio = tmp_path / "manifest.mp3"
    direct_audio = tmp_path / "direct.mp3"
    manifest_audio.touch()
    direct_audio.touch()
    scenes = tmp_path / "manifest-scenes"
    direct_scenes = tmp_path / "direct-scenes"
    scenes.mkdir()
    direct_scenes.mkdir()
    audio_handoff = write_audio(tmp_path / "audio.json", audio=manifest_audio)
    image_handoff = write_image(tmp_path / "image.json", cover=None, scenes=scenes)
    args = SimpleNamespace(
        audio=str(direct_audio), audio_handoff=str(audio_handoff),
        image_handoff=str(image_handoff), subtitle=None, cover=None,
        scenes_dir=str(direct_scenes), story_json=None, output=str(tmp_path / "out.mp4"),
        mode="slideshow", aspect="9x16", duration_per_image=10.0,
        profile_root=None, asset_profile=None, zone_aware_slideshow=False,
    )
    request, _, _ = request_from_args(args)
    assert request.audio == direct_audio
    assert request.scenes_dir == direct_scenes
