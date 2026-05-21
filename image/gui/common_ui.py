from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import streamlit as st

from common.gui.user_messages import (
    UserMessage,
    render_user_message,
)


def _ui_error(message: str) -> None:
    render_user_message(UserMessage(level="error", title="Image", body=message))


def _ui_warning(message: str) -> None:
    render_user_message(UserMessage(level="warning", title="Image", body=message))


def _ui_success(message: str) -> None:
    render_user_message(UserMessage(level="success", title="Image", body=message))


def _ui_info(message: str) -> None:
    render_user_message(UserMessage(level="info", title="Image", body=message))


def _normalize_exc(exc: Exception) -> str:
    name = exc.__class__.__name__
    detail = _repair_mojibake(str(exc).strip() or repr(exc))
    return f"{name}: {detail}"


def _repair_mojibake(value: str) -> str:
    text = str(value or "")
    for _ in range(3):
        try:
            repaired = text.encode("cp1252").decode("utf-8")
        except UnicodeError:
            break
        if repaired == text:
            break
        text = repaired
    return text


def _open_output_folder(path_value: str) -> None:
    if not path_value:
        _ui_warning("No output path is available to open.")
        return
    target = Path(path_value)
    directory = target if target.is_dir() else target.parent
    if not directory.exists():
        _ui_warning(f"Folder not found: {directory}")
        return
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(directory))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(directory)])
        else:
            subprocess.Popen(["xdg-open", str(directory)])
        _ui_success(f"Opened folder: {directory}")
    except Exception as exc:
        _ui_warning(f"Could not open folder: {_normalize_exc(exc)}")


def _copy_path_hint(path_value: str, *, key: str) -> None:
    if st.button("Copy path", key=key, width="stretch"):
        st.session_state[f"{key}::copied"] = path_value
    copied = str(st.session_state.get(f"{key}::copied") or "").strip()
    if copied:
        st.code(copied, language=None)

