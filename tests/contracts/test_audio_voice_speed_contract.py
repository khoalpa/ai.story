from __future__ import annotations

import importlib
from pathlib import Path


def test_all_voice_speed_defaults_are_zero() -> None:
    state = importlib.import_module("audio.gui.state")
    profile_config = importlib.import_module("audio.profile_config")
    render_audio_app = importlib.import_module("audio.render_audio_app")
    render_runtime = importlib.import_module("audio.services.render_runtime")
    flow_state = importlib.import_module("audio.pipeline.flow_state")

    assert set(state.VOICE_SPEED_DEFAULTS.values()) == {0}
    assert set(flow_state.DEFAULT_VOICE_RATE_MAP.values()) == {"0%"}
    for key in state.VOICE_SPEED_DEFAULTS:
        assert profile_config.PROFILE_CONFIG_DEFAULTS[key] == 0
        assert getattr(profile_config.ProfileConfig, key) == 0
        assert render_audio_app.REQUEST_DEFAULTS[key] == 0
        assert getattr(render_audio_app.RenderAudioAppRequest, key) == 0

    assert set(render_runtime.build_voice_rate_map(object()).values()) == {"0%"}


def test_voice_speed_defaults_reset_when_voice_changes() -> None:
    pipeline = importlib.import_module("audio.pipeline.script_pipeline")

    segments = pipeline.plan_segments_from_plain_script(
        "\n".join(
            [
                "SCRIPT:",
                "[NARRATOR] One line.",
                "[FEMALE] Another line.",
            ]
        ),
        voice_rate_map={
            "vi_narrator": "+20%",
            "vi_female": "+5%",
            "vi_male": "+1%",
            "en_narrator": "+8%",
            "en_female": "+9%",
            "en_male": "+10%",
        },
    )

    assert [seg.rate for seg in segments] == ["+20%", "+5%"]


def test_voice_speed_defaults_follow_language_specific_defaults() -> None:
    pipeline = importlib.import_module("audio.pipeline.script_pipeline")

    segments = pipeline.plan_segments_from_plain_script(
        "\n".join(
            [
                "SCRIPT:",
                "[VI][NARRATOR] Xin chao.",
                "[EN][NARRATOR] Hello.",
                "[EN][MALE] Hi.",
            ]
        ),
        voice_rate_map={
            "vi_narrator": "+18%",
            "vi_female": "+14%",
            "vi_male": "+10%",
            "en_narrator": "+7%",
            "en_female": "+9%",
            "en_male": "+11%",
        },
    )

    assert [seg.rate for seg in segments] == ["+18%", "+7%", "+11%"]


def test_speed_tags_adjust_voice_default_instead_of_replacing_it() -> None:
    pipeline = importlib.import_module("audio.pipeline.script_pipeline")

    segments = pipeline.plan_segments_from_plain_script(
        "\n".join(
            [
                "[NARRATOR][SLOW][VI] Slow line.",
                "[NARRATOR][NORMAL][VI] Normal line.",
                "[NARRATOR][FAST][VI] Fast line.",
            ]
        ),
        voice_rate_map={"vi_narrator": "+100%"},
    )

    assert [seg.rate for seg in segments] == ["+98%", "+100%", "+102%"]


def test_speed_tag_uses_language_default_regardless_of_tag_order() -> None:
    pipeline = importlib.import_module("audio.pipeline.script_pipeline")

    segments = pipeline.plan_segments_from_plain_script(
        "[NARRATOR][FAST][EN] Fast English line.",
        voice_rate_map={"vi_narrator": "+10%", "en_narrator": "+30%"},
    )

    assert [seg.rate for seg in segments] == ["+32%"]


def test_speed_tag_adjusts_inherited_voice_default() -> None:
    pipeline = importlib.import_module("audio.pipeline.script_pipeline")

    segments = pipeline.plan_segments_from_plain_script(
        "\n".join(
            [
                "[FEMALE][NORMAL][VI] Establish female voice.",
                "[SLOW] Continue with inherited female voice.",
            ]
        ),
        voice_rate_map={"vi_narrator": "+10%", "vi_female": "+40%"},
    )

    assert [seg.rate for seg in segments] == ["+40%", "+38%"]


def test_vieneu_atempo_filter_supports_rates_above_two_x() -> None:
    tts_core = importlib.import_module("audio.adapters.tts_core")

    assert tts_core._build_atempo_filter("+102%") == "atempo=2,atempo=1.01"


def test_vieneu_time_stretch_replaces_wav_with_ffmpeg_output(monkeypatch, tmp_path) -> None:
    tts_core = importlib.import_module("audio.adapters.tts_core")
    wav_path = tmp_path / "segment.wav"
    wav_path.write_bytes(b"original")
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):  # noqa: ANN001
        captured["command"] = command
        Path(command[-1]).write_bytes(b"stretched")

    monkeypatch.setattr(tts_core.subprocess, "run", fake_run)

    tts_core.apply_vieneu_time_stretch(wav_path, rate="+100%", ffmpeg_exe="custom-ffmpeg")

    assert wav_path.read_bytes() == b"stretched"
    assert captured["command"][0] == "custom-ffmpeg"
    assert "atempo=2" in captured["command"]

