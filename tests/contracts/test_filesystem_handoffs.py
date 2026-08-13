from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


def test_audio_video_handoff_is_consumed_locally(tmp_path: Path) -> None:
    from audio.handoff import write_video_handoff
    from video.handoff import read_audio_handoff

    audio = tmp_path / "audio" / "narration.mp3"
    audio.parent.mkdir()
    audio.touch()
    quality = audio.with_name("narration.audio_quality.json")
    quality.write_text('{"passed": true}', encoding="utf-8")
    manifest = write_video_handoff(audio.parent / "manifest.json", audio=audio)
    bundle = read_audio_handoff(manifest)
    assert bundle.audio == audio
    assert bundle.quality_report == quality


def test_handoff_detects_modified_artifact(tmp_path: Path) -> None:
    from audio.handoff import write_video_handoff
    from video.handoff import read_audio_handoff

    audio = tmp_path / "narration.mp3"
    audio.write_bytes(b"original")
    manifest = write_video_handoff(tmp_path / "manifest.json", audio=audio)
    audio.write_bytes(b"modified")
    with pytest.raises(ValueError, match="checksum mismatch"):
        read_audio_handoff(manifest)


def test_video_cli_direct_asset_inputs_are_supported(tmp_path: Path) -> None:
    from audio.handoff import write_video_handoff
    from video.app_api import request_from_args

    manifest_audio = tmp_path / "manifest.mp3"
    direct_audio = tmp_path / "direct.mp3"
    manifest_audio.touch()
    direct_audio.touch()
    direct_scenes = tmp_path / "direct-scenes"
    direct_scenes.mkdir()
    audio_handoff = write_video_handoff(tmp_path / "audio.json", audio=manifest_audio)
    args = SimpleNamespace(
        audio=str(direct_audio), audio_handoff=str(audio_handoff), image_handoff=None,
        subtitle=None, cover=None, scenes_dir=str(direct_scenes), story_json=None,
        output=str(tmp_path / "out.mp4"), mode="slideshow", aspect="9x16",
        duration_per_image=10.0, profile_root=None, asset_profile=None,
        zone_aware_slideshow=False,
    )
    request, _, _ = request_from_args(args)
    assert request.audio == direct_audio
    assert request.scenes_dir == direct_scenes
