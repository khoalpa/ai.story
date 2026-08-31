from __future__ import annotations

import json

from studio.story_repetition import (
    analyze_story_repetition,
    extract_story_sentences,
    normalize_sentence,
    repetition_report_json,
    split_sentences,
)


def _story(*texts: str) -> dict:
    return {
        "script": [
            {"zone": "OPENING" if index == 0 else "ENDING", "voice": "NARRATOR", "text": text}
            for index, text in enumerate(texts)
        ]
    }


def test_sentence_splitter_retains_story_locations() -> None:
    story = _story("Câu thứ nhất có đầy đủ nội dung. Câu thứ hai cũng đủ dài!")
    sentences = extract_story_sentences(story)
    assert len(sentences) == 2
    assert sentences[1]["block_number"] == 1
    assert sentences[1]["sentence_in_block"] == 2
    assert split_sentences("Một câu hỏi hợp lệ? Một câu trả lời hợp lệ.") == [
        "Một câu hỏi hợp lệ?", "Một câu trả lời hợp lệ."
    ]


def test_normalization_ignores_case_spacing_and_punctuation_but_keeps_vietnamese() -> None:
    assert normalize_sentence("  Minh AN, trở lại! ") == "minh an trở lại"
    assert normalize_sentence("ma") != normalize_sentence("má")


def test_exact_and_near_repetitions_are_classified() -> None:
    report = analyze_story_repetition(_story(
        "Minh An bước vào căn phòng tối và nhìn quanh.",
        "Minh An bước vào căn phòng tối và nhìn quanh! "
        "Minh An chậm rãi bước vào căn phòng tối rồi nhìn quanh.",
    ))
    summary = report["summary"]
    assert summary["exact_pair_count"] == 1
    assert summary["near_pair_count"] >= 1
    assert {item["type"] for item in report["pairs"]} == {"exact", "near"}
    assert report["pairs"][0]["left"]["zone"] == "OPENING"


def test_short_repeated_phrases_are_ignored() -> None:
    report = analyze_story_repetition(_story("Tôi biết.", "Tôi biết!"))
    assert report["summary"]["pair_count"] == 0


def test_report_is_utf8_json_serializable() -> None:
    report = analyze_story_repetition(_story("Không có câu lặp đủ dài trong đoạn này."))
    decoded = json.loads(repetition_report_json(report).decode("utf-8"))
    assert decoded["kind"] == "story.repetition-report"
