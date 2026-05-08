from __future__ import annotations

import importlib
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

    handoff_utils = types.ModuleType("common.gui.handoff_utils")
    handoff_utils.HandoffAction = object
    handoff_utils.render_handoff_action_row = lambda *args, **kwargs: None
    sys.modules["common.gui.handoff_utils"] = handoff_utils

    state_mod = types.ModuleType("common.gui.state")
    state_mod.send_image_to_video = lambda *args, **kwargs: None
    state_mod.set_image_handoff = lambda *args, **kwargs: None
    sys.modules["common.gui.state"] = state_mod

    user_messages = types.ModuleType("common.gui.user_messages")
    user_messages.show_empty_result = lambda *args, **kwargs: None
    user_messages.show_preview_warning = lambda *args, **kwargs: None
    sys.modules["common.gui.user_messages"] = user_messages

    workspace_source_outputs = types.ModuleType("common.gui.workspace_source_outputs")
    workspace_source_outputs.workspace_source_outputs = lambda *args, **kwargs: types.SimpleNamespace(image_cover_output="", image_scenes_dir="")
    sys.modules["common.gui.workspace_source_outputs"] = workspace_source_outputs

    common_ui = types.ModuleType("image.gui.common_ui")
    common_ui._copy_path_hint = lambda *args, **kwargs: None
    common_ui._normalize_exc = lambda exc: exc
    common_ui._open_output_folder = lambda *args, **kwargs: None
    common_ui._ui_error = lambda *args, **kwargs: None
    common_ui._ui_info = lambda *args, **kwargs: None
    common_ui._ui_success = lambda *args, **kwargs: None
    common_ui._ui_warning = lambda *args, **kwargs: None
    sys.modules["image.gui.common_ui"] = common_ui

    prompt_state = types.ModuleType("image.gui.prompt_state")
    prompt_state._get_effective_prompt_edit = lambda *args, **kwargs: {"prompt": "", "negative_prompt": ""}
    sys.modules["image.gui.prompt_state"] = prompt_state

    workflow_routing = types.ModuleType("image.workflow_routing")
    workflow_routing.infer_prompt_kind = lambda *args, **kwargs: "scene"
    sys.modules["image.workflow_routing"] = workflow_routing

    sys.modules.pop("image.gui.result_ui", None)


def test_display_value_distinguishes_missing_vs_empty() -> None:
    original_modules = {name: sys.modules.get(name) for name in [
        "streamlit",
        "common.gui.handoff_utils",
        "common.gui.state",
        "common.gui.user_messages",
        "common.gui.workspace_source_outputs",
        "image.gui.common_ui",
        "image.gui.prompt_state",
        "image.workflow_routing",
        "image.gui.result_ui",
    ]}
    state = SessionState()
    _install_streamlit(state)
    try:
        result_ui = importlib.import_module("image.gui.result_ui")

        assert result_ui._display_value(None) == "missing"
        assert result_ui._display_value("") == "empty"
        assert result_ui._display_value("cover.png") == "cover.png"
        assert result_ui._prompt_card_meta_text(kind="scene", rel_path="scene_prompt.json", image_key="scene_1") == "kind=scene | rel=scene_prompt.json | key=scene_1"
        assert result_ui._expected_output_location_text(kind="cover.png", output_path=Path("output") / "images" / "cover.png", prompt_name="cover.png") == "cover.png -> output\\images\\cover.png"
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def test_latest_run_cover_preview_prefers_result_cover_over_temp_cover(tmp_path) -> None:
    original_modules = {name: sys.modules.get(name) for name in [
        "streamlit",
        "common.gui.handoff_utils",
        "common.gui.state",
        "common.gui.user_messages",
        "common.gui.workspace_source_outputs",
        "image.gui.common_ui",
        "image.gui.prompt_state",
        "image.workflow_routing",
        "image.gui.result_ui",
    ]}
    state = SessionState()
    _install_streamlit(state)
    try:
        result_ui = importlib.import_module("image.gui.result_ui")
        cover_image = tmp_path / "images" / "cover.png"
        cover_image.parent.mkdir()
        cover_image.write_bytes(b"cover")
        temp_cover = tmp_path / "temp-cover.png"
        temp_cover.write_bytes(b"temp")
        state["image_temp_cover_path"] = str(temp_cover)
        result = types.SimpleNamespace(
            cover_image=cover_image,
            output_dir=tmp_path,
            scene_images_dir=tmp_path / "images",
        )

        assert result_ui._resolve_latest_run_cover_preview(result) == cover_image
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def test_prompt_card_scene_preview_does_not_fallback_to_latest_scene_by_mtime(tmp_path) -> None:
    original_modules = {name: sys.modules.get(name) for name in [
        "streamlit",
        "common.gui.handoff_utils",
        "common.gui.state",
        "common.gui.user_messages",
        "common.gui.workspace_source_outputs",
        "image.gui.common_ui",
        "image.gui.prompt_state",
        "image.workflow_routing",
        "image.gui.result_ui",
    ]}
    state = SessionState()
    _install_streamlit(state)
    try:
        result_ui = importlib.import_module("image.gui.result_ui")
        scene_dir = tmp_path / "images"
        scene_dir.mkdir()
        wrong_scene = scene_dir / "other.png"
        wrong_scene.write_bytes(b"other")
        expected_scene = scene_dir / "desired.png"
        result = types.SimpleNamespace(
            cover_image=None,
            output_dir=tmp_path,
            scene_images_dir=scene_dir,
        )
        entry = {
            "kind": "scene",
            "path": tmp_path / "scene_prompt.json",
            "rel_path": "scene_prompt.json",
            "slot": "scene",
            "prompt_data": {"image_key": "desired"},
        }

        output_path = result_ui._resolve_result_output_for_entry(result, entry)
        status_text, _, status_path = result_ui._output_status_for_entry(result, entry)

        assert output_path == expected_scene
        assert output_path != wrong_scene
        assert status_text == "missing"
        assert status_path == expected_scene
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def test_prompt_card_scene_prefers_current_versioned_output(tmp_path) -> None:
    original_modules = {name: sys.modules.get(name) for name in [
        "streamlit",
        "common.gui.handoff_utils",
        "common.gui.state",
        "common.gui.user_messages",
        "common.gui.workspace_source_outputs",
        "image.gui.common_ui",
        "image.gui.prompt_state",
        "image.workflow_routing",
        "image.gui.result_ui",
    ]}
    state = SessionState()
    _install_streamlit(state)
    try:
        result_ui = importlib.import_module("image.gui.result_ui")
        scene_dir = tmp_path / "images"
        scene_dir.mkdir()
        wrong_scene = scene_dir / "scene.png"
        wrong_scene.write_bytes(b"scene-old")
        expected_scene = scene_dir / "scene_4.png"
        expected_scene.write_bytes(b"scene-new")
        cover_image = scene_dir / "cover_4.png"
        cover_image.write_bytes(b"cover-new")
        result = types.SimpleNamespace(
            cover_image=cover_image,
            output_dir=tmp_path,
            scene_images_dir=scene_dir,
            generated_files=[cover_image, expected_scene],
        )
        entry = {
            "kind": "scene",
            "path": tmp_path / "scene_prompt.json",
            "rel_path": "scene_prompt.json",
            "slot": "scene",
            "prompt_data": {"image_key": "scene"},
        }

        output_path = result_ui._resolve_result_output_for_entry(result, entry)
        status_text, _, status_path = result_ui._output_status_for_entry(result, entry)
        meta_text = result_ui._prompt_card_meta_text(
            kind="scene",
            rel_path="scene_prompt.json",
            image_key="scene",
            output_path=output_path,
        )

        assert output_path == expected_scene
        assert output_path != wrong_scene
        assert status_text == "generated"
        assert status_path == expected_scene
        assert meta_text == "kind=scene | rel=scene_prompt.json | key=scene | expected=scene_4.png"
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def test_prompt_card_scene_shows_actual_path_when_version_differs(tmp_path) -> None:
    original_modules = {name: sys.modules.get(name) for name in [
        "streamlit",
        "common.gui.handoff_utils",
        "common.gui.state",
        "common.gui.user_messages",
        "common.gui.workspace_source_outputs",
        "image.gui.common_ui",
        "image.gui.prompt_state",
        "image.workflow_routing",
        "image.gui.result_ui",
    ]}
    state = SessionState()
    _install_streamlit(state)
    try:
        result_ui = importlib.import_module("image.gui.result_ui")
        scene_dir = tmp_path / "images"
        scene_dir.mkdir()
        actual_scene = scene_dir / "scene.png"
        actual_scene.write_bytes(b"scene-old")
        cover_image = scene_dir / "cover_4.png"
        cover_image.write_bytes(b"cover-new")
        result = types.SimpleNamespace(
            cover_image=cover_image,
            output_dir=tmp_path,
            scene_images_dir=scene_dir,
            generated_files=[cover_image, actual_scene],
        )
        entry = {
            "kind": "scene",
            "path": tmp_path / "scene_prompt.json",
            "rel_path": "scene_prompt.json",
            "slot": "scene",
            "prompt_data": {"image_key": "scene"},
        }

        output_path = result_ui._resolve_result_output_for_entry(result, entry)
        expected_path = result_ui._versioned_expected_output_path(result, entry, fallback_path=output_path)
        meta_text = result_ui._prompt_card_meta_text(
            kind="scene",
            rel_path="scene_prompt.json",
            image_key="scene",
            output_path=expected_path,
            actual_path=output_path,
        )

        assert output_path == actual_scene
        assert expected_path == scene_dir / "scene_4.png"
        assert meta_text == "kind=scene | rel=scene_prompt.json | key=scene | expected=scene_4.png | actual=scene.png"
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def test_scene_prompt_without_image_key_uses_suggested_output_name(tmp_path) -> None:
    original_modules = {name: sys.modules.get(name) for name in [
        "streamlit",
        "common.gui.handoff_utils",
        "common.gui.state",
        "common.gui.user_messages",
        "common.gui.workspace_source_outputs",
        "image.gui.common_ui",
        "image.gui.prompt_state",
        "image.workflow_routing",
        "image.gui.result_ui",
    ]}
    state = SessionState()
    _install_streamlit(state)
    try:
        result_ui = importlib.import_module("image.gui.result_ui")
        scene_dir = tmp_path / "images"
        scene_dir.mkdir()
        expected_scene = scene_dir / "scene.png"
        result = types.SimpleNamespace(
            cover_image=None,
            output_dir=tmp_path,
            scene_images_dir=scene_dir,
        )
        entry = {
            "kind": "scene",
            "path": tmp_path / "scene_prompt.json",
            "rel_path": "scene_prompt.json",
            "slot": "scene_prompt",
            "prompt_data": {},
            "suggested_output": tmp_path / "images" / "scene.png",
        }

        output_path = result_ui._resolve_result_output_for_entry(result, entry)
        meta_text = result_ui._prompt_card_meta_text(
            kind="scene",
            rel_path="scene_prompt.json",
            image_key="scene",
            output_path=output_path,
        )

        assert output_path == expected_scene
        assert meta_text == "kind=scene | rel=scene_prompt.json | key=scene | expected=scene.png"
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def test_expected_output_path_shared_for_cover_and_scene(tmp_path) -> None:
    original_modules = {name: sys.modules.get(name) for name in [
        "streamlit",
        "common.gui.handoff_utils",
        "common.gui.state",
        "common.gui.user_messages",
        "common.gui.workspace_source_outputs",
        "image.gui.common_ui",
        "image.gui.prompt_state",
        "image.workflow_routing",
        "image.gui.result_ui",
    ]}
    state = SessionState()
    _install_streamlit(state)
    try:
        result_ui = importlib.import_module("image.gui.result_ui")

        cover_dir = tmp_path / "cover-out"
        cover_dir.mkdir()
        cover_file = cover_dir / "images" / "cover.png"
        cover_file.parent.mkdir()
        cover_file.write_bytes(b"cover")
        cover_result = types.SimpleNamespace(
            cover_image=None,
            output_dir=cover_dir,
            scene_images_dir=cover_dir / "images",
        )
        scene_dir = tmp_path / "images"
        scene_dir.mkdir()
        scene_result = types.SimpleNamespace(
            cover_image=None,
            output_dir=tmp_path,
            scene_images_dir=scene_dir,
        )
        scene_entry = {
            "kind": "scene",
            "path": tmp_path / "scene_prompt.json",
            "rel_path": "scene_prompt.json",
            "slot": "scene",
            "prompt_data": {"image_key": "desired"},
            "suggested_output": scene_dir / "desired.png",
        }

        assert result_ui._expected_output_path(cover_result, kind="cover") == cover_file
        assert result_ui._expected_output_path(
            scene_result,
            kind="scene",
            prompt_data=scene_entry["prompt_data"],
            rel_path=scene_entry["rel_path"],
            slot=scene_entry["slot"],
            suggested_output=scene_entry["suggested_output"],
        ) == scene_dir / "desired.png"
        assert result_ui._expected_output_location_text(
            kind="scene",
            output_path=scene_dir / "desired.png",
            prompt_name="scene",
        ) == f"scene -> {scene_dir / 'desired.png'}"
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def test_existing_run_preview_result_uses_previous_version_pair(tmp_path) -> None:
    original_modules = {name: sys.modules.get(name) for name in [
        "streamlit",
        "common.gui.handoff_utils",
        "common.gui.state",
        "common.gui.user_messages",
        "common.gui.workspace_source_outputs",
        "image.gui.common_ui",
        "image.gui.prompt_state",
        "image.workflow_routing",
        "image.gui.result_ui",
    ]}
    state = SessionState()
    _install_streamlit(state)
    try:
        result_ui = importlib.import_module("image.gui.result_ui")
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        for name in ["cover.png", "scene.png", "cover_1.png", "scene_1.png", "cover_2.png", "scene_2.png"]:
            (images_dir / name).write_bytes(name.encode("utf-8"))

        preview = result_ui._build_existing_run_preview_result(tmp_path)

        assert preview is not None
        assert preview.cover_image == images_dir / "cover_1.png"
        assert preview.generated_files == [images_dir / "cover_1.png", images_dir / "scene_1.png"]
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def test_next_run_version_index_increments_from_existing_pairs(tmp_path) -> None:
    service = importlib.import_module("image.gui.service")
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    assert service._next_run_version_index(images_dir) == 0

    for name in ["cover.png", "scene.png"]:
        (images_dir / name).write_bytes(name.encode("utf-8"))
    assert service._next_run_version_index(images_dir) == 1

    for name in ["cover_1.png", "scene_1.png"]:
        (images_dir / name).write_bytes(name.encode("utf-8"))
    assert service._next_run_version_index(images_dir) == 2


def test_double_click_image_view_opens_new_window_at_native_size(tmp_path) -> None:
    original_modules = {name: sys.modules.get(name) for name in [
        "streamlit",
        "common.gui.handoff_utils",
        "common.gui.state",
        "common.gui.user_messages",
        "common.gui.workspace_source_outputs",
        "image.gui.common_ui",
        "image.gui.prompt_state",
        "image.workflow_routing",
        "image.gui.result_ui",
    ]}
    state = SessionState()
    _install_streamlit(state)
    try:
        result_ui = importlib.import_module("image.gui.result_ui")
        image_path = tmp_path / "images" / "cover_1.png"
        image_path.parent.mkdir()
        image_path.write_bytes(b"cover")

        html, height = result_ui._build_double_click_image_view(image_path, caption="Cover version: cover_1.png")

        assert "window.open" in html
        assert "noopener,noreferrer" in html
        assert "Open 100% view" in html
        assert "100% view" in html
        assert "max-width: none" in html
        assert height >= 380
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def test_double_click_image_view_supports_custom_gallery_tooltip(tmp_path) -> None:
    original_modules = {name: sys.modules.get(name) for name in [
        "streamlit",
        "common.gui.handoff_utils",
        "common.gui.state",
        "common.gui.user_messages",
        "common.gui.workspace_source_outputs",
        "image.gui.common_ui",
        "image.gui.prompt_state",
        "image.workflow_routing",
        "image.gui.result_ui",
    ]}
    state = SessionState()
    _install_streamlit(state)
    try:
        result_ui = importlib.import_module("image.gui.result_ui")
        image_path = tmp_path / "images" / "scene_1.png"
        image_path.parent.mkdir()
        image_path.write_bytes(b"scene")

        html, _ = result_ui._build_double_click_image_view(
            image_path,
            caption="scene_1.png",
        )

        assert 'title="Open 100% view"' in html
        assert "Open 100% view" in html
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def test_prompt_card_meta_text_shows_expected_when_missing(tmp_path) -> None:
    original_modules = {name: sys.modules.get(name) for name in [
        "streamlit",
        "common.gui.handoff_utils",
        "common.gui.state",
        "common.gui.user_messages",
        "common.gui.workspace_source_outputs",
        "image.gui.common_ui",
        "image.gui.prompt_state",
        "image.workflow_routing",
        "image.gui.result_ui",
    ]}
    state = SessionState()
    _install_streamlit(state)
    try:
        result_ui = importlib.import_module("image.gui.result_ui")
        expected_output = tmp_path / "desired.png"

        text = result_ui._prompt_card_meta_text(
            kind="scene",
            rel_path="scene_prompt.json",
            image_key="desired",
            output_path=expected_output,
        )

        assert text == "kind=scene | rel=scene_prompt.json | key=desired | expected=desired.png"
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

