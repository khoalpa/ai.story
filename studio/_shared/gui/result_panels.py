from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import streamlit as st


@dataclass(frozen=True)
class MetricSpec:
    label: str
    value: Any
    delta: str | None = None


@dataclass(frozen=True)
class DownloadSpec:
    label: str
    data: bytes
    file_name: str
    mime: str
    key: str | None = None
    disabled: bool = False


def render_metrics_row(metrics: Sequence[MetricSpec]) -> None:
    if not metrics:
        return
    cols = st.columns(len(metrics))
    for col, metric in zip(cols, metrics):
        col.metric(metric.label, metric.value, delta=metric.delta)


def render_download_button_row(downloads: Iterable[DownloadSpec], *, column_spec: list[float] | None = None) -> None:
    download_list = list(downloads)
    if not download_list:
        return
    cols = st.columns(column_spec or [1.0] * len(download_list))
    for col, item in zip(cols, download_list):
        with col:
            st.download_button(
                item.label,
                data=item.data,
                file_name=item.file_name,
                mime=item.mime,
                width="stretch",
                key=item.key,
                disabled=item.disabled,
            )
