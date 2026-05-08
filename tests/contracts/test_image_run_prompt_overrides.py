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


def _install_streamlit(session_state: SessionState | None = None) -> None:
    sys.modules["streamlit"] = types.SimpleNamespace(session_state=session_state or SessionState())
    for name in ["image.gui.service"]:
        sys.modules.pop(name, None)


def test_apply_prompt_edit_allows_blank_prompt_dict() -> None:
    original_streamlit = sys.modules.get("streamlit")
    _install_streamlit()
    try:
        service = importlib.import_module("image.gui.service")

        patched = service._apply_prompt_edit(
            {"prompt": "original", "negative_prompt": "neg"},
            {"prompt": "", "negative_prompt": "edited neg"},
        )

        assert patched["prompt"] == ""
        assert patched["negative_prompt"] == "edited neg"
    finally:
        if original_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = original_streamlit


def test_apply_prompt_edit_allows_blank_prompt_string() -> None:
    original_streamlit = sys.modules.get("streamlit")
    _install_streamlit()
    try:
        service = importlib.import_module("image.gui.service")

        patched = service._apply_prompt_edit(
            {"prompt": "original", "negative_prompt": "neg"},
            "",
        )

        assert patched["prompt"] == ""
        assert patched["negative_prompt"] == "neg"
    finally:
        if original_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = original_streamlit

