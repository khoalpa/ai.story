from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path


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
    for name in [
        "common.gui.state",
        "image.provider_runtime",
        "image.gui.common_ui",
        "image.gui.detector_ui",
        "image.gui.result_ui",
        "image.gui.state",
        "image.gui.tabs",
    ]:
        sys.modules.pop(name, None)


def _restore_modules(original_modules: dict[str, object | None]) -> None:
    for name, module in original_modules.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def test_image_test_tab_rebuilds_bundle_from_story_handoff(tmp_path: Path) -> None:
    original_modules = {name: sys.modules.get(name) for name in ["streamlit", "common.gui.state", "image.provider_runtime", "image.gui.common_ui", "image.gui.result_ui", "image.gui.state", "image.gui.tabs"]}
    handoff_dir = tmp_path / "story_bundle"
    handoff_dir.mkdir()
    (handoff_dir / "cover_prompt.json").write_text(
        json.dumps({"kind": "cover", "slot": "cover", "prompt": "cover prompt"}, ensure_ascii=False),
        encoding="utf-8",
    )
    scene_dir = handoff_dir / "scene_prompts"
    scene_dir.mkdir()
    (scene_dir / "scene_001.json").write_text(
        json.dumps({"kind": "scene", "slot": "scene_001", "prompt": "scene prompt"}, ensure_ascii=False),
        encoding="utf-8",
    )

    state = SessionState(
        {
            "image_source_kind": "handoff",
            "image_lock_to_story_handoff": True,
            "workspace_story_image_handoff_dir": str(handoff_dir),
            "image_handoff_dir": "",
        }
    )
    _install_streamlit(state)
    try:
        tabs = importlib.import_module("image.gui.tabs")

        prompt_dir, entries, issues = tabs._resolve_test_prompt_bundle({"handoff_dir": "", "input_dir": ""})

        assert prompt_dir == handoff_dir
        assert issues == []
        assert [entry["rel_path"] for entry in entries] == ["cover_prompt.json", "scene_prompts/scene_001.json"]
        assert state["image_handoff_dir"] == str(handoff_dir)
        assert state["image_test_prompt_dir"] == str(handoff_dir)
        assert len(state["image_test_prompt_bundle"]) == 2
    finally:
        _restore_modules(original_modules)


def test_image_test_tab_reports_missing_input_directory_clearly(tmp_path: Path) -> None:
    del tmp_path
    original_modules = {name: sys.modules.get(name) for name in ["streamlit", "common.gui.state", "image.provider_runtime", "image.gui.common_ui", "image.gui.result_ui", "image.gui.state", "image.gui.tabs"]}
    state = SessionState(
        {
            "image_source_kind": "input",
            "image_input_dir": "",
        }
    )
    _install_streamlit(state)
    try:
        tabs = importlib.import_module("image.gui.tabs")

        prompt_dir, entries, issues = tabs._resolve_test_prompt_bundle({"handoff_dir": "", "input_dir": ""})

        assert prompt_dir is None
        assert entries == []
        assert issues == ["Prompt source = input but the Input directory is not configured yet."]
    finally:
        _restore_modules(original_modules)


def test_image_test_tab_falls_back_to_input_when_handoff_is_missing(tmp_path: Path) -> None:
    original_modules = {name: sys.modules.get(name) for name in ["streamlit", "common.gui.state", "image.provider_runtime", "image.gui.common_ui", "image.gui.result_ui", "image.gui.state", "image.gui.tabs"]}
    prompt_dir = tmp_path / "input_prompts"
    prompt_dir.mkdir()
    (prompt_dir / "cover_prompt.json").write_text(
        json.dumps({"kind": "cover", "slot": "cover", "prompt": "cover prompt"}, ensure_ascii=False),
        encoding="utf-8",
    )

    state = SessionState(
        {
            "image_source_kind": "handoff",
            "image_lock_to_story_handoff": True,
            "workspace_story_image_handoff_dir": "",
            "image_handoff_dir": "",
            "image_input_dir": str(prompt_dir),
        }
    )
    _install_streamlit(state)
    try:
        tabs = importlib.import_module("image.gui.tabs")

        resolved_dir, entries, issues = tabs._resolve_test_prompt_bundle({"handoff_dir": "", "input_dir": ""})

        assert resolved_dir == prompt_dir
        assert issues == []
        assert [entry["rel_path"] for entry in entries] == ["cover_prompt.json"]
        assert state["image_source_kind"] == "input"
        assert state["image_test_prompt_dir"] == str(prompt_dir)
    finally:
        _restore_modules(original_modules)


def test_image_test_tab_reports_missing_handoff_with_guidance(tmp_path: Path) -> None:
    del tmp_path
    original_modules = {name: sys.modules.get(name) for name in ["streamlit", "common.gui.state", "image.provider_runtime", "image.gui.common_ui", "image.gui.result_ui", "image.gui.state", "image.gui.tabs"]}
    state = SessionState(
        {
            "image_source_kind": "handoff",
            "image_lock_to_story_handoff": True,
            "workspace_story_image_handoff_dir": "",
            "image_handoff_dir": "",
            "image_input_dir": "",
        }
    )
    _install_streamlit(state)
    try:
        tabs = importlib.import_module("image.gui.tabs")

        prompt_dir, entries, issues = tabs._resolve_test_prompt_bundle({"handoff_dir": "", "input_dir": ""})

        assert prompt_dir is None
        assert entries == []
        assert issues == [
            "Prompt source is set to handoff, but no Story handoff directory is available. Run Story and click Send to Image, or switch Prompt source to input and choose a prompt folder."
        ]
    finally:
        _restore_modules(original_modules)


def test_image_test_tab_reports_invalid_prompt_bundle_structure(tmp_path: Path) -> None:
    original_modules = {name: sys.modules.get(name) for name in ["streamlit", "common.gui.state", "image.provider_runtime", "image.gui.common_ui", "image.gui.result_ui", "image.gui.state", "image.gui.tabs"]}
    prompt_dir = tmp_path / "input_prompts"
    prompt_dir.mkdir()
    (prompt_dir / "manifest.json").write_text(json.dumps({"ok": True}), encoding="utf-8")

    state = SessionState(
        {
            "image_source_kind": "input",
            "image_input_dir": str(prompt_dir),
        }
    )
    _install_streamlit(state)
    try:
        tabs = importlib.import_module("image.gui.tabs")

        resolved_dir, entries, issues = tabs._resolve_test_prompt_bundle(
            {"handoff_dir": "", "input_dir": str(prompt_dir)}
        )

        assert resolved_dir == prompt_dir
        assert entries == []
        assert issues == [
            "Prompt directory exists but no valid prompt file was found. Expected cover_prompt.json, scene_prompt.json, or scene_prompts/*.json."
        ]
    finally:
        _restore_modules(original_modules)


