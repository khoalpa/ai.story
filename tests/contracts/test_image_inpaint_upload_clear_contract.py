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
    sys.modules['streamlit'] = types.SimpleNamespace(session_state=session_state)
    providers = types.ModuleType('image.provider_runtime')
    providers._resolve_bundle_asset_path = lambda *args, **kwargs: None
    providers.build_debug_preview_sheet = lambda *args, **kwargs: None
    providers.overlay_mask_preview = lambda *args, **kwargs: None
    providers.parse_preview_tint = lambda *args, **kwargs: (255, 255, 255)
    sys.modules['image.provider_runtime'] = providers

    common_ui = types.ModuleType('image.gui.common_ui')
    common_ui._normalize_exc = lambda exc: exc
    common_ui._ui_error = lambda *args, **kwargs: None
    common_ui._ui_info = lambda *args, **kwargs: None
    common_ui._ui_success = lambda *args, **kwargs: None
    common_ui._ui_warning = lambda *args, **kwargs: None
    sys.modules['image.gui.common_ui'] = common_ui

    result_ui = types.ModuleType('image.gui.result_ui')
    result_ui._current_temp_cover_path = lambda: None
    result_ui._find_scene_output_by_key = lambda *args, **kwargs: None
    sys.modules['image.gui.result_ui'] = result_ui

    for name in ['image.gui.inpaint_utils', 'image.gui.state']:
        sys.modules.pop(name, None)


def _restore_modules(original_modules: dict[str, object | None]) -> None:
    for name, module in original_modules.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


class _FakeUploadedPath:
    def __init__(self) -> None:
        self.unlinked_missing_ok = None

    def unlink(self, missing_ok: bool = False) -> None:
        self.unlinked_missing_ok = missing_ok


def test_clear_uploaded_inpaint_source_removes_file_and_state() -> None:
    original_modules = {name: sys.modules.get(name) for name in ['streamlit', 'image.provider_runtime', 'image.gui.common_ui', 'image.gui.result_ui', 'image.gui.inpaint_utils', 'image.gui.state']}
    state = SessionState()
    _install_streamlit(state)
    try:
        inpaint_utils = importlib.import_module('image.gui.inpaint_utils')

        selected_rel_path = 'prompts/example.json'
        uploaded_path = _FakeUploadedPath()

        uploaded_key = inpaint_utils._inpaint_uploaded_source_key(selected_rel_path)
        upload_widget_key = inpaint_utils._inpaint_source_upload_widget_key(selected_rel_path)
        manual_key = inpaint_utils._inpaint_manual_source_key(selected_rel_path)
        clear_key = inpaint_utils._inpaint_uploaded_source_clear_key(selected_rel_path)

        state[uploaded_key] = str(uploaded_path)
        state[upload_widget_key] = 'widget-state'
        state[manual_key] = 'manual-state'
        state[clear_key] = True

        inpaint_utils._current_uploaded_inpaint_source_path = lambda rel_path: uploaded_path if rel_path == selected_rel_path else None

        inpaint_utils._clear_uploaded_inpaint_source(selected_rel_path=selected_rel_path)

        assert uploaded_path.unlinked_missing_ok is True
        assert uploaded_key not in state
        assert upload_widget_key not in state
        assert manual_key not in state
        assert clear_key not in state
    finally:
        _restore_modules(original_modules)


def test_manual_inpaint_source_is_blocked_while_upload_is_active() -> None:
    original_modules = {name: sys.modules.get(name) for name in ['streamlit', 'image.provider_runtime', 'image.gui.common_ui', 'image.gui.result_ui', 'image.gui.inpaint_utils', 'image.gui.state']}
    state = SessionState()
    _install_streamlit(state)
    try:
        inpaint_utils = importlib.import_module('image.gui.inpaint_utils')

        assert inpaint_utils._can_apply_manual_inpaint_source(uploaded_source_path_value=None, uploaded_source=None) is True
        assert inpaint_utils._can_apply_manual_inpaint_source(uploaded_source_path_value=object(), uploaded_source=None) is False
        assert inpaint_utils._can_apply_manual_inpaint_source(uploaded_source_path_value=None, uploaded_source=object()) is False
    finally:
        _restore_modules(original_modules)


class _FakePreviewPath:
    def __init__(self, value: str) -> None:
        self.value = value

    def expanduser(self) -> "_FakePreviewPath":
        return self

    def is_file(self) -> bool:
        return True

    def resolve(self) -> "_FakePreviewPath":
        return self

    def __str__(self) -> str:
        return self.value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _FakePreviewPath) and self.value == other.value


def test_uploaded_preview_source_caption_tracks_active_upload() -> None:
    original_modules = {name: sys.modules.get(name) for name in ['streamlit', 'image.provider_runtime', 'image.gui.common_ui', 'image.gui.result_ui', 'image.gui.inpaint_utils', 'image.gui.state']}
    state = SessionState()
    _install_streamlit(state)
    try:
        inpaint_utils = importlib.import_module('image.gui.inpaint_utils')

        original_path_ctor = inpaint_utils.Path
        try:
            inpaint_utils.Path = lambda value: _FakePreviewPath(str(value))  # type: ignore[assignment]
            source_path = _FakePreviewPath('C:/tmp/inpaint-upload.png')
            uploaded_source_path_value = _FakePreviewPath('C:/tmp/inpaint-upload.png')

            assert inpaint_utils._is_uploaded_inpaint_preview_source(
                source_path=source_path,
                uploaded_source_path_value=uploaded_source_path_value,
            ) is True
            assert inpaint_utils._inpaint_preview_source_caption(
                source_label='Uploaded source | inpaint-upload.png',
                is_uploaded_preview=True,
            ) == 'Source image: Uploaded preview source'
            assert inpaint_utils._inpaint_preview_source_caption(
                source_label='Resolved source | cover.png',
                is_uploaded_preview=False,
            ) == 'Source image: Resolved source | cover.png'
        finally:
            inpaint_utils.Path = original_path_ctor
    finally:
        _restore_modules(original_modules)


def test_uploaded_source_active_badge_text_tracks_active_upload() -> None:
    original_modules = {name: sys.modules.get(name) for name in ['streamlit', 'image.provider_runtime', 'image.gui.common_ui', 'image.gui.result_ui', 'image.gui.inpaint_utils', 'image.gui.state']}
    state = SessionState()
    _install_streamlit(state)
    try:
        inpaint_utils = importlib.import_module('image.gui.inpaint_utils')

        assert inpaint_utils._inpaint_source_status_badge_text(uploaded_source_active=True) == 'Uploaded source active'
        assert inpaint_utils._inpaint_source_status_badge_text(uploaded_source_active=False) == 'Auto-resolved source'
    finally:
        _restore_modules(original_modules)


def test_uploaded_preview_source_badge_text_tracks_preview_source() -> None:
    original_modules = {name: sys.modules.get(name) for name in ['streamlit', 'image.provider_runtime', 'image.gui.common_ui', 'image.gui.result_ui', 'image.gui.inpaint_utils', 'image.gui.state']}
    state = SessionState()
    _install_streamlit(state)
    try:
        inpaint_utils = importlib.import_module('image.gui.inpaint_utils')

        assert inpaint_utils._inpaint_preview_source_badge_text(is_uploaded_preview=True) == 'Uploaded preview source'
        assert inpaint_utils._inpaint_preview_source_badge_text(is_uploaded_preview=False) == ''
    finally:
        _restore_modules(original_modules)


