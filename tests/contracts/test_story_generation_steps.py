from __future__ import annotations

import json


def test_validate_and_render_story_result_turns_draft_into_final_result() -> None:
    from story.audio_story_spec import ALLOWED_SCRIPT_ZONES, OUTLINE_KEYS
    from story.gui.service import validate_and_render_story_result

    draft = {
        "brief": {"project": {"language_primary": "VI"}},
        "mode": "trend",
        "base_mode": "trend",
        "mode_label": "Trend",
        "authoring": {
            "meta": {
                "title": "Step Story",
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
                    "text": f"CÃ¢u chuyá»‡n á»Ÿ pháº§n {idx}.",
                }
                for idx, zone in enumerate(ALLOWED_SCRIPT_ZONES, start=1)
            ],
        },
    }

    result = validate_and_render_story_result(draft=draft, settings={"mode": "trend", "base_mode": "trend"})

    assert result["authoring"] == draft["authoring"]
    assert "CÃ¢u chuyá»‡n á»Ÿ pháº§n 1." in result["plain_script"]
    assert result["mode"] == "trend"
    assert result["validated"] is True


def test_validate_and_render_story_result_can_skip_generated_output_validation() -> None:
    from story.gui.service import validate_and_render_story_result

    draft = {
        "authoring": {
            "meta": {"title": "Draft Preview"},
            "script": [
                {
                    "zone": "GIỚI THIỆU",
                    "environment": "",
                    "voice": "NARRATOR",
                    "speed": "NORMAL",
                    "lang": "VI",
                    "text": "Bản nháp vẫn có thể được render để kiểm tra.",
                }
            ],
        },
    }

    result = validate_and_render_story_result(
        draft=draft,
        settings={"mode": "trend", "base_mode": "trend", "validate_generated_output": False},
    )

    assert result["validated"] is False
    assert result["canonical_errors"] == []
    assert "Bản nháp vẫn có thể được render" in result["plain_script"]


def test_generate_story_outline_uses_sidebar_max_tokens(monkeypatch) -> None:
    from story.audio_story_spec import OUTLINE_KEYS
    from story.gui import service
    from story.paths import PROJECT_ROOT

    captured = {}

    class FakeLLMClient:
        def __init__(self, cfg):
            captured["cfg"] = cfg

        def chat(self, system: str, user: str) -> str:
            captured["system"] = system
            captured["user"] = user
            return json.dumps(
                {
                    "meta": {
                        "title": "Fast Outline",
                        "series": "",
                        "episode": "",
                        "author": "Audio Story",
                        "channel": "Audio Story",
                        "target": "Test",
                        "length_min": 3,
                        "length_max": 5,
                        "language": "vi",
                        "genre": "Drama",
                        "audience": "General",
                        "tone": "Warm",
                        "tags": ["fast"],
                    },
                    "outline": {key: f"{key} beat" for key in OUTLINE_KEYS},
                    "script": [],
                }
            )

    monkeypatch.setattr(service, "LLMClient", FakeLLMClient)
    monkeypatch.chdir(PROJECT_ROOT / "studio")

    result = service.generate_story_outline(
        brief_text="genre: Drama\naudience: General\ntheme: Speed\ntone: Warm\n",
        system_prompt="System",
        settings={
            "mode": "trend",
            "base_mode": "trend",
            "base_url": "http://localhost:1234/v1",
            "model": "auto",
            "api_key": "not-needed",
            "timeout_s": 360,
            "max_tokens": 32768,
            "temperature": 0.7,
            "retries": 3,
        },
    )

    assert captured["cfg"].max_tokens == 32768
    assert captured["cfg"].retry_attempts == service.OUTLINE_FAST_RETRY_ATTEMPTS
    assert result["settings_summary"]["outline_max_tokens"] == 32768
    assert result["settings_summary"]["output_base"] == str(PROJECT_ROOT / "output" / "story" / "story")


def test_generate_story_outline_accepts_json_with_trailing_model_text(monkeypatch) -> None:
    from story.audio_story_spec import OUTLINE_KEYS
    from story.gui import service

    class ChattyLLMClient:
        def __init__(self, cfg):
            self.cfg = cfg

        def chat(self, system: str, user: str) -> str:
            payload = {
                "meta": {
                    "title": "Recovered Outline",
                    "series": "",
                    "episode": "",
                    "author": "Audio Story",
                    "channel": "Audio Story",
                    "target": "Test",
                    "length_min": 3,
                    "length_max": 5,
                    "language": "vi",
                    "genre": "Drama",
                    "audience": "General",
                    "tone": "Warm",
                    "tags": ["recover"],
                },
                "outline": {key: f"{key} beat" for key in OUTLINE_KEYS},
                "script": [],
            }
            return f"Here is the JSON:\n{json.dumps(payload)}\nDone."

    monkeypatch.setattr(service, "LLMClient", ChattyLLMClient)

    result = service.generate_story_outline(
        brief_text="genre: Drama\naudience: General\ntheme: Speed\ntone: Warm\n",
        system_prompt="System",
        settings={
            "mode": "trend",
            "base_mode": "trend",
            "base_url": "http://localhost:1234/v1",
            "model": "auto",
            "api_key": "not-needed",
            "timeout_s": 360,
            "max_tokens": 1600,
            "temperature": 0.7,
            "retries": 2,
        },
    )

    assert result["outline_payload"]["meta"]["title"] == "Recovered Outline"
    assert result["outline_payload"]["outline"]["greeting"] == "greeting beat"


def test_story_step_output_base_is_project_root_relative(monkeypatch) -> None:
    from story.gui import service
    from story.paths import PROJECT_ROOT

    monkeypatch.chdir(PROJECT_ROOT / "studio")

    run = service.build_story_run_context(
        brief_text="genre: Drama\naudience: General\ntheme: Root output\ntone: Warm\n",
        system_prompt="System",
        settings={
            "mode": "trend",
            "base_mode": "trend",
            "base_url": "http://localhost:1234/v1",
            "model": "auto",
            "api_key": "not-needed",
            "timeout_s": 360,
            "max_tokens": 32768,
            "temperature": 0.7,
            "retries": 3,
            "output_base": "output/story/story",
        },
    )

    assert run["context"].paths.output_base == PROJECT_ROOT / "output" / "story" / "story"
    assert run["settings_summary"]["output_base"] == str(PROJECT_ROOT / "output" / "story" / "story")


def test_story_step_json_saves_under_project_root_output(monkeypatch) -> None:
    from story.gui.output_paths import save_story_step_json
    from story.paths import PROJECT_ROOT

    monkeypatch.chdir(PROJECT_ROOT / "studio")
    path = PROJECT_ROOT / "output" / "story" / "codex-test-story-output-path_outline.json"
    path.unlink(missing_ok=True)
    try:
        actual = save_story_step_json(
            {"ok": True},
            output_base="output/story/codex-test-story-output-path",
            step="outline",
        )

        assert actual == path
        assert json.loads(path.read_text(encoding="utf-8")) == {"ok": True}
        assert not str(actual).startswith(str(PROJECT_ROOT / "studio" / "output"))
    finally:
        path.unlink(missing_ok=True)


def test_generate_story_outline_fails_fast_on_empty_llm_content(monkeypatch) -> None:
    import pytest

    from story.client import LLMResponseFormatError
    from story.gui import service
    from story.gui.errors import StoryLLMOutputError

    calls = {"chat": 0}

    class EmptyLLMClient:
        def __init__(self, cfg):
            self.cfg = cfg

        def chat(self, system: str, user: str) -> str:
            calls["chat"] += 1
            raise LLMResponseFormatError("LLM JSON message content must be a non-empty string")

    monkeypatch.setattr(service, "LLMClient", EmptyLLMClient)

    with pytest.raises(StoryLLMOutputError, match="empty or malformed"):
        service.generate_story_outline(
            brief_text="genre: Drama\naudience: General\ntheme: Speed\ntone: Warm\n",
            system_prompt="System",
            settings={
                "mode": "trend",
                "base_mode": "trend",
                "base_url": "http://localhost:1234/v1",
                "model": "auto",
                "api_key": "not-needed",
                "timeout_s": 360,
                "max_tokens": 1600,
                "temperature": 0.7,
                "retries": 2,
            },
        )

    assert calls["chat"] == 1


def test_generate_story_outline_rejects_invalid_outline_contract(monkeypatch) -> None:
    import pytest

    from story.gui import service

    class InvalidOutlineClient:
        def __init__(self, cfg):
            self.cfg = cfg

        def chat(self, system: str, user: str) -> str:
            return json.dumps(
                {
                    "meta": {
                        "title": "Invalid Outline",
                        "series": "",
                        "episode": "",
                        "author": "Audio Story",
                        "channel": "Audio Story",
                        "target": "Test",
                        "length_min": 3,
                        "length_max": 5,
                        "language": "vi",
                        "genre": "Drama",
                        "audience": "General",
                        "tone": "Warm",
                        "tags": ["invalid"],
                    },
                    "outline": {
                        "greeting": "hello",
                        "opening": "",
                    },
                    "script": [{"zone": "unexpected"}],
                }
            )

    monkeypatch.setattr(service, "LLMClient", InvalidOutlineClient)

    with pytest.raises(ValueError, match="Outline payload không đúng contract"):
        service.generate_story_outline(
            brief_text="genre: Drama\naudience: General\ntheme: Speed\ntone: Warm\n",
            system_prompt="System",
            settings={
                "mode": "trend",
                "base_mode": "trend",
                "base_url": "http://localhost:1234/v1",
                "model": "auto",
                "api_key": "not-needed",
                "timeout_s": 360,
                "max_tokens": 1600,
                "temperature": 0.7,
                "retries": 2,
            },
        )


def test_reset_story_outputs_after_outline_clears_dependent_state() -> None:
    from story.gui.tabs import reset_story_outputs_after_outline

    state = {
        "story_authoring_draft": {"authoring": {}},
        "story_last_result": {"plain_script": "old"},
        "story_last_failed_result": {"authoring": {}},
        "story_last_error_context": {"preview": "old"},
        "story_last_plain_script_path": "Plain script sáºµn sÃ ng trong Studio",
        "workspace_story_plain_script_text": "old script",
        "workspace_last_story_output": "Plain script ready to send to Audio",
        "workspace_story_image_handoff_dir": "old/image",
        "workspace_story_video_handoff_dir": "old/video",
    }

    reset_story_outputs_after_outline(state)

    assert state["story_authoring_draft"] is None
    assert state["story_last_result"] is None
    assert state["story_last_failed_result"] is None
    assert state["story_last_error_context"] is None
    assert state["story_last_plain_script_path"] == ""
    assert state["workspace_story_plain_script_text"] == ""
    assert state["workspace_last_story_output"] == ""
    assert state["workspace_story_image_handoff_dir"] == ""
    assert state["workspace_story_video_handoff_dir"] == ""


def test_outline_estimate_details_scales_with_brief_duration_history() -> None:
    from story.gui.tabs import outline_estimate_details

    details = outline_estimate_details(
        target_duration_min=10,
        history=[
            {"elapsed_s": 30, "target_duration_min": 5},
            {"elapsed_s": 90, "target_duration_min": 15},
        ],
    )

    assert "target_duration=10m" in details
    assert "estimate=1:00" in details
    assert "history_samples=2" in details


def test_draft_estimate_details_scales_with_brief_duration_history() -> None:
    from story.gui.tabs import draft_estimate_details

    details = draft_estimate_details(
        target_duration_min=12,
        history=[
            {"elapsed_s": 120, "target_duration_min": 6},
            {"elapsed_s": 360, "target_duration_min": 18},
        ],
    )

    assert "target_duration=12m" in details
    assert "draft_estimate=4:00" in details
    assert "draft_history_samples=2" in details


def test_outline_progress_shows_estimate_details(monkeypatch) -> None:
    from story.gui import tabs

    monkeypatch.setattr(tabs, "render_runtime_usage_compact", lambda: None)
    captured = {}

    class Progress:
        def progress(self, frac, text):
            captured["frac"] = frac
            captured["text"] = text

    class LogSlot:
        def code(self, text):
            captured["logs"] = text

    sink = tabs.make_progress_sink(
        Progress(),
        LogSlot(),
        [],
        mode="trend",
        outline_details=["target_duration=10m", "estimate=1:00", "history_samples=2"],
    )

    sink("outline", "Generating story outline (fast, max_tokens=32768)")

    assert captured["frac"] == 0.25
    assert "estimate=1:00" in captured["text"]
    assert "target_duration=10m" in captured["text"]
    assert "[outline] Generating story outline" in captured["logs"]


def test_draft_progress_shows_estimate_details(monkeypatch) -> None:
    from story.gui import tabs

    monkeypatch.setattr(tabs, "render_runtime_usage_compact", lambda: None)
    captured = {}

    class Progress:
        def progress(self, frac, text):
            captured["frac"] = frac
            captured["text"] = text

    class LogSlot:
        def code(self, text):
            captured["logs"] = text

    sink = tabs.make_progress_sink(
        Progress(),
        LogSlot(),
        [],
        mode="trend",
        draft_details=["target_duration=12m", "draft_estimate=4:00", "draft_history_samples=2"],
    )

    sink("generate", "Generating story draft")

    assert captured["frac"] == 0.6
    assert "draft_estimate=4:00" in captured["text"]
    assert "target_duration=12m" in captured["text"]
    assert "[generate] Generating story draft" in captured["logs"]


def test_append_outline_history_records_elapsed_and_brief_duration() -> None:
    from story.gui.history import append_outline_history
    from story.gui.state import STORY_OUTLINE_HISTORY_KEY

    state = {}

    append_outline_history(
        elapsed_s=12.345,
        target_duration_min=8,
        mode="trend",
        max_tokens=32768,
        state=state,
    )

    entry = state[STORY_OUTLINE_HISTORY_KEY][0]
    assert entry["elapsed_s"] == 12.35
    assert entry["target_duration_min"] == 8
    assert entry["mode"] == "trend"
    assert entry["max_tokens"] == 32768
    assert entry["time"]


def test_append_draft_history_records_elapsed_and_brief_duration() -> None:
    from story.gui.history import append_draft_history
    from story.gui.state import STORY_DRAFT_HISTORY_KEY

    state = {}

    append_draft_history(
        elapsed_s=45.678,
        target_duration_min=12,
        mode="trend",
        max_tokens=32768,
        chunked=True,
        chunk_size=60,
        state=state,
    )

    entry = state[STORY_DRAFT_HISTORY_KEY][0]
    assert entry["elapsed_s"] == 45.68
    assert entry["target_duration_min"] == 12
    assert entry["mode"] == "trend"
    assert entry["max_tokens"] == 32768
    assert entry["chunked"] is True
    assert entry["chunk_size"] == 60
    assert entry["time"]


def test_generate_all_phase_history_records_outline_and_draft() -> None:
    from story.gui.state import STORY_DRAFT_HISTORY_KEY, STORY_OUTLINE_HISTORY_KEY
    from story.gui.tabs import append_generate_all_phase_history

    state = {}

    append_generate_all_phase_history(
        phase_elapsed_s={"outline": 3.2, "generate": 12.4},
        target_duration_min=9,
        settings={"mode": "trend", "max_tokens": 32768, "chunked": True, "chunk_size": 60},
        result={"mode": "trend", "settings_summary": {"max_tokens": 32768, "chunked": True, "chunk_size": 60}},
        state=state,
    )

    outline_entry = state[STORY_OUTLINE_HISTORY_KEY][0]
    draft_entry = state[STORY_DRAFT_HISTORY_KEY][0]
    assert outline_entry["elapsed_s"] == 3.2
    assert outline_entry["target_duration_min"] == 9
    assert outline_entry["max_tokens"] == 32768
    assert draft_entry["elapsed_s"] == 12.4
    assert draft_entry["chunked"] is True
    assert draft_entry["chunk_size"] == 60


def test_story_runtime_error_splits_friendly_and_technical_details() -> None:
    from story.client import LLMResponseFormatError
    from story.gui.errors import format_runtime_error, split_runtime_error_details

    message = format_runtime_error(LLMResponseFormatError("LLM JSON message content must be a non-empty string"))
    friendly, technical = split_runtime_error_details(message)

    assert friendly == "Model không trả nội dung trong message response. Hãy thử chạy lại, kiểm tra model local có đang sinh output, hoặc tăng nhẹ Max tokens nếu cần."
    assert technical == "LLM JSON message content must be a non-empty string"


def test_story_outline_json_error_has_specific_guidance() -> None:
    from story.gui.errors import format_runtime_error, split_runtime_error_details

    message = format_runtime_error(ValueError("Outline response is not valid JSON after retries. Details: Expecting ',' delimiter"))
    friendly, technical = split_runtime_error_details(message)

    assert friendly.startswith("Model trả về outline chưa đúng định dạng JSON.")
    assert "2048-3072" in friendly
    assert "Expecting ',' delimiter" in technical

