from __future__ import annotations

import pytest

from audio.audio_story_spec import _looks_like_single_sentence as audio_single_sentence


@pytest.mark.parametrize("validator", [audio_single_sentence])
@pytest.mark.parametrize(
    "text",
    [
        "“Một câu thoại hợp lệ.”",
        "'Một câu thoại hợp lệ.'",
        "(Một câu hoàn chỉnh.)",
    ],
)
def test_single_sentence_accepts_trailing_closing_punctuation(validator, text: str) -> None:
    assert validator(text) is True


@pytest.mark.parametrize("validator", [audio_single_sentence])
def test_single_sentence_still_rejects_two_quoted_sentences(validator) -> None:
    assert validator("“Câu thứ nhất. Câu thứ hai.”") is False
