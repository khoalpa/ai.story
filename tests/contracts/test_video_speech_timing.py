import pytest

from studio.video_speech_timing import (
    parse_srt,
    required_container_duration,
    speech_timing_preflight,
)


SRT = """1
00:00:44,258 --> 00:00:50,786
Sáng ấy, đoàn tàu màu lam vừa dừng ở Ga Mây thì chiếc chuông đồng trên mái hiên tự rung ba tiếng.
"""


def clip(duration: int) -> dict:
    return {
        "clip_id": "clip_0003",
        "duration_seconds": duration,
        "voice_plan": {"segments": [{"text": "Sáng ấy, đoàn tàu màu lam vừa dừng ở Ga Mây thì chiếc chuông đồng trên mái hiên tự rung ba tiếng."}]},
    }


def test_parse_srt_preserves_measured_duration() -> None:
    cue = parse_srt(SRT)[0]
    assert cue.duration_seconds == pytest.approx(6.528)


def test_smallest_container_includes_safety_margin() -> None:
    assert required_container_duration(3.4, (4, 6, 8)) == 4
    assert required_container_duration(6.528, (4, 6, 8)) == 8
    assert required_container_duration(8.0, (4, 6, 8)) is None


def test_preflight_blocks_clip_when_measured_speech_does_not_fit() -> None:
    errors, rows = speech_timing_preflight([clip(4)], SRT, (4, 6, 8))
    assert "SPEECH_DOES_NOT_FIT_CONTAINER" in errors[0]
    assert rows[0]["recommended_duration_seconds"] == 8


def test_preflight_accepts_smallest_safe_container() -> None:
    errors, rows = speech_timing_preflight([clip(8)], SRT, (4, 6, 8))
    assert errors == []
    assert rows[0]["speech_duration_seconds"] == 6.528
