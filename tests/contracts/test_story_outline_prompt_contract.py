from __future__ import annotations


def test_story_outline_prompt_requests_compact_short_json() -> None:
    from story.prompting import build_meta_outline_prompt

    prompt = build_meta_outline_prompt({"genre": "Drama", "theme": "Test"}, mode="trend")

    assert "Keep every outline field short" in prompt
    assert "Return compact minified JSON only" in prompt

