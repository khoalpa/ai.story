from __future__ import annotations


def test_story_seed_is_injected_into_run_context_and_prompt() -> None:
    from story.gui.service import build_story_run_context
    from story.prompting import build_meta_outline_prompt

    run = build_story_run_context(
        brief_text="genre: mystery\ntheme: a hidden letter\n",
        system_prompt="system",
        settings={
            "mode": "trend",
            "base_mode": "trend",
            "story_seed": 424242,
            "base_url": "http://localhost:1234/v1",
            "model": "auto",
        },
    )

    assert run["story_seed"] == 424242
    assert run["context"].brief["variation"]["seed"] == 424242
    prompt = build_meta_outline_prompt(run["context"].brief, mode=run["context"].mode)
    assert "creative seed: 424242" in prompt


def test_validate_result_preserves_story_seed() -> None:
    from story.audio_story_spec import ALLOWED_SCRIPT_ZONES, OUTLINE_KEYS
    from story.gui.service import validate_and_render_story_result

    authoring = {
        "meta": {
            "title": "Seed Story",
            "series": "Series",
            "episode": "1",
            "author": "Author",
            "channel": "Channel",
            "target": "Test",
            "length_min": 1,
            "length_max": 2,
            "language": "VI",
            "genre": "Drama",
            "audience": "General",
            "tone": "Warm",
            "tags": ["test"],
        },
        "outline": {key: f"{key} beat" for key in OUTLINE_KEYS},
        "script": [
            {
                "zone": zone,
                "environment": "Studio",
                "voice": "NARRATOR",
                "speed": "NORMAL",
                "lang": "VI",
                "text": f"CÃ¢u chuyá»‡n seed á»Ÿ pháº§n {idx}.",
            }
            for idx, zone in enumerate(ALLOWED_SCRIPT_ZONES, start=1)
        ],
    }

    result = validate_and_render_story_result(
        draft={"authoring": authoring, "mode": "trend", "base_mode": "trend", "story_seed": 99},
        settings={"mode": "trend", "base_mode": "trend", "story_seed": 123},
    )

    assert result["story_seed"] == 99


def test_story_outline_retries_after_malformed_json(monkeypatch) -> None:
    from story.gui import service

    calls: list[str] = []

    class FakeClient:
        def __init__(self, cfg: object) -> None:
            self.cfg = cfg

        def chat(self, system: str, prompt: str) -> str:
            calls.append(prompt)
            if len(calls) == 1:
                return '{"meta" "broken"}'
            return """
            {
              "meta": {
                "title": "Seeded",
                "series": "",
                "episode": "1",
                "author": "Audio Story",
                "channel": "Audio Story",
                "target": "General",
                "length_min": 3,
                "length_max": 5,
                "language": "vi",
                "genre": "mystery",
                "audience": "general",
                "tone": "warm",
                "tags": ["seed"]
              },
              "outline": {
                "greeting": "hello",
                "opening": "open",
                "introduction": "intro",
                "development": "develop",
                "climax": "climax",
                "falling": "fall",
                "ending": "end",
                "farewell": "bye"
              },
              "script": []
            }
            """

    monkeypatch.setattr(service, "LLMClient", FakeClient)

    outline = service.generate_story_outline(
        brief_text="genre: mystery\n",
        system_prompt="system",
        settings={"mode": "trend", "base_mode": "trend", "story_seed": 7},
    )

    assert outline["outline_payload"]["meta"]["title"] == "Seeded"
    assert len(calls) == 2
    assert "[RETRY NOTE]" in calls[1]

