from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import streamlit as st

from .panel_utils import render_json_summary_expander


@dataclass(frozen=True)
class DiagnosticsSection:
    label: str
    payload: Any
    message: str = ""
    level: str = "caption"
    expanded: bool = False


def render_runtime_diagnostics_block(
    payload: Any,
    *,
    label: str = "Runtime diagnostics",
    caption: str = "This information helps verify the current runtime environment before deeper debugging.",
    expanded: bool = False,
    serializer: callable | None = None,
) -> None:
    if serializer is not None:
        payload = serializer(payload)
    with st.expander(label, expanded=expanded):
        st.caption(caption)
        st.json(payload)


def render_diagnostics_sections(sections: Iterable[DiagnosticsSection]) -> None:
    for section in sections:
        if section.message:
            level = section.level if section.level in {"success", "info", "warning", "error"} else "caption"
            getattr(st, level)(section.message)
        render_json_summary_expander(section.label, section.payload, expanded=section.expanded)
