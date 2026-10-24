from __future__ import annotations

import json

import pytest
from PIL import Image

from audio.handoff import write_video_handoff
from video import cli_entry
from video.handoff import read_audio_handoff


@pytest.fixture
def handoff_files(tmp_path):
    audio = tmp_path / "story.wav"
    audio.write_bytes(b"original")
    subtitle = tmp_path / "story.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
    manifest = write_video_handoff(tmp_path / "handoff.json", audio=audio, subtitle=subtitle)
    return audio, subtitle, manifest


@pytest.mark.parametrize("field,value,error", [
    ("schema_version", 2, "schema version"), ("kind", "wrong", "kind"),
    ("producer", "wrong", "producer"), ("created_at", None, "created_at"), ("artifacts", {}, "artifacts.audio"),
])
def test_video_rejects_wrong_handoff_contract(handoff_files, field, value, error):
    _, _, manifest = handoff_files
    data = json.loads(manifest.read_text())
    data[field] = value
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        read_audio_handoff(manifest)


@pytest.mark.parametrize("field,value,error", [
    ("media_type", "image/png", "media type mismatch"), ("size_bytes", 100, "size mismatch"),
    ("path", "missing.wav", "not found"),
])
def test_video_rejects_missing_or_mismatched_audio(handoff_files, field, value, error):
    _, _, manifest = handoff_files
    data = json.loads(manifest.read_text())
    data["artifacts"]["audio"][field] = value
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises((ValueError, FileNotFoundError), match=error):
        read_audio_handoff(manifest)


def test_video_rejects_deleted_subtitle(handoff_files):
    _, subtitle, manifest = handoff_files
    subtitle.unlink()
    with pytest.raises(FileNotFoundError, match="not found"):
        read_audio_handoff(manifest)


def test_video_cli_checks_handoff_images_without_starting_renderer(handoff_files, tmp_path, monkeypatch, capsys):
    _, subtitle, manifest = handoff_files
    cover = tmp_path / "cover.png"
    Image.new("RGB", (32, 18)).save(cover)
    output = tmp_path / "video.mp4"
    args = cli_entry.parse_args(["--audio-handoff", str(manifest), "--output", str(output),
                                "--mode", "static", "--aspect", "16x9", "--cover", str(cover), "--check-images"])

    def unexpected(*args, **kwargs):
        pytest.fail("Image preflight must not start rendering or require FFmpeg")

    monkeypatch.setattr(cli_entry, "ensure_tools", unexpected)
    monkeypatch.setattr(cli_entry, "execute_render_request", unexpected)
    assert cli_entry.run_from_args(args) == output
    assert not output.exists()
    assert read_audio_handoff(manifest).subtitle == subtitle
    assert "Image readiness: READY" in capsys.readouterr().out
    cover.write_bytes(b"broken image")
    with pytest.raises(ValueError, match="Images are not ready"):
        cli_entry.run_from_args(args)


def test_cli_reports_invalid_handoff_as_user_error(handoff_files, tmp_path, monkeypatch, capsys):
    audio, _, manifest = handoff_files
    audio.unlink()
    monkeypatch.setattr(cli_entry, "setup_stdio", lambda: None)
    with pytest.raises(SystemExit) as exc:
        cli_entry.main(["--audio-handoff", str(manifest), "--output", str(tmp_path / "video.mp4"), "--mode", "static"])
    assert exc.value.code == 2
    assert "Handoff artifact not found" in capsys.readouterr().err


def test_cli_forwards_verified_inputs_and_reports_render_outputs(handoff_files, tmp_path, monkeypatch, capsys):
    audio, subtitle, manifest = handoff_files
    cover = tmp_path / "cover.png"
    Image.new("RGB", (32, 18)).save(cover)
    story = tmp_path / "story.json"
    story.write_text('{"script":[]}', encoding="utf-8")
    output = tmp_path / "video.mp4"
    result_manifest = tmp_path / "video.result.json"
    quality = tmp_path / "video.video_quality.json"
    args = cli_entry.parse_args(["--audio-handoff", str(manifest), "--output", str(output),
                                "--mode", "static", "--cover", str(cover), "--scenes-dir", str(tmp_path),
                                "--story-json", str(story)])
    requests = []

    def render(request):
        requests.append(request)
        output.write_bytes(b"rendered fixture")
        result_manifest.write_text('{}', encoding="utf-8")
        quality.write_text('{"passed":true}', encoding="utf-8")
        return {"result_manifest_path": str(result_manifest), "quality_report_path": str(quality)}

    monkeypatch.setattr(cli_entry, "ensure_tools", lambda: None)
    monkeypatch.setattr(cli_entry, "execute_render_request", render)
    assert cli_entry.run_from_args(args) == output
    assert len(requests) == 1
    assert (requests[0].audio, requests[0].subtitle, requests[0].story_json) == (audio, subtitle, story)
    assert output.read_bytes() == b"rendered fixture"
    assert str(quality) in capsys.readouterr().out
    for flag, name in (("subtitle", "missing.srt"), ("story_json", "missing.json")):
        previous = getattr(args, flag)
        setattr(args, flag, str(tmp_path / name))
        with pytest.raises(FileNotFoundError, match="not found"):
            cli_entry.run_from_args(args)
        setattr(args, flag, previous)
    assert len(requests) == 1


def test_handoff_rejects_nonobject_root_and_non_audio_artifact(tmp_path):
    manifest = tmp_path / "handoff.json"
    manifest.write_text('[]', encoding="utf-8")
    with pytest.raises(ValueError, match="root must be an object"):
        read_audio_handoff(manifest)
    image = tmp_path / "cover.png"
    Image.new("RGB", (16, 9)).save(image)
    write_video_handoff(manifest, audio=image)
    with pytest.raises(ValueError, match="Unsupported audio"):
        read_audio_handoff(manifest)
