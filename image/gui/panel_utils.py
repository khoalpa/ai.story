from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import streamlit as st


def normalize_optional_path(raw: str) -> Path | None:
    value = str(raw or "").strip()
    if not value:
        return None
    return Path(value)


def safe_rerun() -> None:
    rerun_fn = getattr(st, "rerun", None)
    if callable(rerun_fn):
        rerun_fn()


def render_json_summary_expander(label: str, payload: Any, *, expanded: bool = False) -> None:
    with st.expander(label, expanded=expanded):
        st.json(payload)


def render_download_button_from_path(
    label: str,
    path: str | Path | None,
    *,
    mime: str,
    file_name: str | None = None,
    width: str = "stretch",
) -> None:
    resolved = normalize_optional_path(str(path or ""))
    if resolved is None or not resolved.is_file():
        return
    with resolved.open("rb") as fh:
        st.download_button(
            label,
            data=fh,
            file_name=file_name or resolved.name,
            mime=mime,
            width=width,
        )


def render_session_history(
    items: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    empty_message: str,
    title_builder: Callable[[int, dict[str, Any]], str] | None = None,
) -> None:
    if not items:
        st.info(empty_message)
        return
    if title_builder is None:
        title_builder = lambda idx, item: f"#{idx}"
    for idx, item in enumerate(items, start=1):
        with st.expander(title_builder(idx, item), expanded=False):
            st.json(item)
