from __future__ import annotations

import importlib
import sys
import types


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def _install_streamlit(session_state: SessionState) -> None:
    sys.modules["streamlit"] = types.SimpleNamespace(session_state=session_state)
    sys.modules.pop("image.gui.prompt_state", None)


def test_effective_prompt_edit_preserves_empty_strings() -> None:
    state = SessionState(
        {
            "image_prompt_edit_map": {
                "scene_001.json": {
                    "prompt": "",
                    "negative_prompt": "",
                }
            }
        }
    )
    original_streamlit = sys.modules.get("streamlit")
    _install_streamlit(state)
    try:
        prompt_state = importlib.import_module("image.gui.prompt_state")

        effective = prompt_state._get_effective_prompt_edit(
            "scene_001.json",
            {"prompt": "original prompt", "negative_prompt": "original negative"},
        )

        assert effective == {"prompt": "", "negative_prompt": ""}
    finally:
        if original_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = original_streamlit


def test_effective_prompt_edit_preserves_empty_legacy_override() -> None:
    state = SessionState(
        {
            "image_prompt_overrides": {
                "scene_001.json": "",
            }
        }
    )
    original_streamlit = sys.modules.get("streamlit")
    _install_streamlit(state)
    try:
        prompt_state = importlib.import_module("image.gui.prompt_state")

        effective = prompt_state._get_effective_prompt_edit(
            "scene_001.json",
            {"prompt": "original prompt", "negative_prompt": "original negative"},
        )

        assert effective == {"prompt": "", "negative_prompt": "original negative"}
    finally:
        if original_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = original_streamlit


def test_store_prompt_edit_state_updates_state_only() -> None:
    state = SessionState()
    original_streamlit = sys.modules.get("streamlit")
    _install_streamlit(state)
    try:
        prompt_state = importlib.import_module("image.gui.prompt_state")

        prompt_state._store_prompt_edit_state(
            "scene_001.json",
            prompt="edited prompt",
            negative_prompt="",
        )

        assert state["image_prompt_edit_map"]["scene_001.json"] == {
            "prompt": "edited prompt",
            "negative_prompt": "",
        }
        assert state["image_prompt_overrides"]["scene_001.json"] == "edited prompt"
        assert "image_prompt_text::scene_001.json" not in state
        assert "image_negative_text::scene_001.json" not in state
    finally:
        if original_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = original_streamlit


def test_reset_prompt_edit_state_syncs_widget_keys() -> None:
    state = SessionState()
    original_streamlit = sys.modules.get("streamlit")
    _install_streamlit(state)
    try:
        prompt_state = importlib.import_module("image.gui.prompt_state")

        prompt_state._reset_prompt_edit_state(
            "scene_001.json",
            prompt="reset prompt",
            negative_prompt="reset negative",
        )

        assert state["image_prompt_edit_map"]["scene_001.json"] == {
            "prompt": "reset prompt",
            "negative_prompt": "reset negative",
        }
        assert state["image_prompt_overrides"]["scene_001.json"] == "reset prompt"
        assert state["image_prompt_text::scene_001.json"] == "reset prompt"
        assert state["image_negative_text::scene_001.json"] == "reset negative"
    finally:
        if original_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = original_streamlit


def test_prompt_edit_state_resets_when_bundle_changes() -> None:
    state = SessionState()
    original_streamlit = sys.modules.get("streamlit")
    _install_streamlit(state)
    try:
        prompt_state = importlib.import_module("image.gui.prompt_state")
        entries = [
            {
                "rel_path": "scene_prompts/opening.json",
                "prompt_data": {"prompt": "fresh prompt", "negative_prompt": "fresh neg"},
            }
        ]

        prompt_state._ensure_prompt_edit_state(entries, "bundle-a")
        state["image_prompt_edit_map"]["scene_prompts/opening.json"]["prompt"] = "edited old prompt"
        state["image_prompt_overrides"] = {}
        state["image_prompt_overrides"]["scene_prompts/opening.json"] = "edited old prompt"

        prompt_state._ensure_prompt_edit_state(entries, "bundle-b")

        assert state["image_prompt_edit_bundle_key"] == "bundle-b"
        assert state["image_prompt_edit_map"]["scene_prompts/opening.json"]["prompt"] == "fresh prompt"
        assert state["image_prompt_overrides"] == {}
    finally:
        if original_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = original_streamlit

