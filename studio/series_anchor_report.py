"""Friendly Streamlit viewer for series_anchor.json files."""
from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, BinaryIO, Mapping

from studio.package_quality_report import _items, _object, _read_report

STATUS_LABELS = {
    "active": "Đang phát triển",
    "open": "Đang mở",
    "resolved": "Đã giải quyết",
    "reached": "Đã đạt",
    "planned": "Đã lên kế hoạch",
    "confirmed": "Đã xác nhận",
    "disproved": "Đã bác bỏ",
}


def _validate_series_anchor(report: Mapping[str, Any]) -> None:
    required = {"series", "canon", "continuity", "episode_ledger", "canon_change_log"}
    missing = sorted(required.difference(report))
    if missing:
        raise ValueError(
            "Tệp không đúng định dạng series_anchor.json; thiếu: " + ", ".join(missing)
        )


def _status_text(value: Any) -> str:
    text = str(value or "Không rõ")
    return STATUS_LABELS.get(text, text.replace("_", " ").title())


def _character_names(canon: Mapping[str, Any]) -> dict[str, str]:
    characters = _items(canon.get("investigation_team")) + _items(canon.get("recurring_characters"))
    return {
        str(item.get("character_id")): str(item.get("name") or item.get("character_id"))
        for item in characters
    }


def _render_header(report: Mapping[str, Any]) -> None:
    import streamlit as st

    series = _object(report.get("series"))
    title = escape(str(series.get("title") or "Series chưa đặt tên"))
    channel = escape(str(series.get("channel") or "—"))
    author = escape(str(series.get("author") or "—"))
    status = str(series.get("status") or "unknown")
    st.markdown(
        f"""
        <div class="sa-heading">
          <div><div class="sa-eyebrow">Series anchor</div><h2>{title}</h2>
          <div class="sa-muted">{channel} · {author}</div></div>
          <div class="sa-verdict">● {_status_text(status)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_overview(report: Mapping[str, Any]) -> None:
    import streamlit as st

    series = _object(report.get("series"))
    canon = _object(report.get("canon"))
    continuity = _object(report.get("continuity"))
    threads = _items(continuity.get("open_threads"))
    current_episode = int(continuity.get("latest_episode") or 0)
    planned_episodes = int(series.get("planned_arc_episodes") or 0)

    st.info(str(series.get("premise") or "Chưa có tiền đề series."))
    cols = st.columns(6)
    cols[0].metric("Tiến độ", f"{current_episode}/{planned_episodes} tập")
    cols[1].metric("Nhân vật", len(_character_names(canon)))
    cols[2].metric("Địa điểm", len(_items(canon.get("recurring_locations"))))
    cols[3].metric("Đầu mối", len(_items(continuity.get("clue_ledger"))))
    cols[4].metric("Luồng đang mở", sum(item.get("status") == "open" for item in threads))
    cols[5].metric("Hệ quả còn lại", len(_items(continuity.get("unresolved_consequences"))))
    if planned_episodes:
        st.progress(max(0.0, min(current_episode / planned_episodes, 1.0)))

    st.subheader("Luồng truyện cần theo dõi")
    st.dataframe(
        [{
            "Luồng": item.get("thread_id", "—"),
            "Nội dung": item.get("summary", "—"),
            "Trạng thái": _status_text(item.get("status")),
            "Cập nhật ở tập": item.get("last_updated_episode", "—"),
        } for item in sorted(threads, key=lambda row: row.get("status") != "open")],
        hide_index=True,
        use_container_width=True,
    )

    mystery = _object(canon.get("master_mystery"))
    milestones = _items(mystery.get("arc_milestones"))
    if milestones:
        st.subheader("Lộ trình bí ẩn trung tâm")
        st.dataframe(
            [{
                "Tập": item.get("target_episode", "—"),
                "Mốc": item.get("summary", "—"),
                "Trạng thái": _status_text(item.get("status")),
            } for item in milestones],
            hide_index=True,
            use_container_width=True,
        )


def _render_canon(report: Mapping[str, Any]) -> None:
    import streamlit as st

    canon = _object(report.get("canon"))
    characters = _items(canon.get("investigation_team")) + _items(canon.get("recurring_characters"))
    names = _character_names(canon)
    st.subheader("Nhân vật")
    if characters:
        selected_id = st.selectbox(
            "Chọn nhân vật",
            [str(item.get("character_id")) for item in characters],
            format_func=lambda item_id: names.get(item_id, item_id),
        )
        selected = next(item for item in characters if str(item.get("character_id")) == selected_id)
        cols = st.columns([1.55, 1, 1])
        role = escape(str(selected.get("role") or "—"))
        cols[0].markdown(
            f"""
            <div style="padding:.25rem 0">
              <div style="font-size:.875rem;line-height:1.25;opacity:.72;margin-bottom:.35rem">Vai trò</div>
              <div style="font-size:clamp(1.65rem,2.2vw,2.35rem);line-height:1.15;white-space:normal;overflow-wrap:anywhere;word-break:normal">{role}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        cols[1].metric("Tuổi", selected.get("age_or_range", "—"))
        cols[2].metric("Xuất hiện từ tập", selected.get("introduced_episode", "—"))
        raw_traits = selected.get("identity_traits")
        traits = raw_traits if isinstance(raw_traits, list) else []
        st.markdown("\n".join(f"- {trait}" for trait in traits))
    else:
        st.info("Canon chưa có nhân vật.")

    locations = _items(canon.get("recurring_locations"))
    if locations:
        st.subheader("Địa điểm lặp lại")
        st.dataframe(
            [{
                "Địa điểm": item.get("name", "—"),
                "Mô tả": item.get("description", "—"),
                "Dấu hiệu thị giác": item.get("visual_signature", "—"),
            } for item in locations],
            hide_index=True,
            use_container_width=True,
        )

    world_rules = _object(canon.get("world_rules"))
    if world_rules:
        st.subheader("Quy tắc thế giới")
        st.dataframe(
            [{"Quy tắc": key.replace("_", " ").title(), "Nội dung": value}
             for key, value in world_rules.items()],
            hide_index=True,
            use_container_width=True,
        )


def _render_continuity(report: Mapping[str, Any]) -> None:
    import streamlit as st

    canon = _object(report.get("canon"))
    continuity = _object(report.get("continuity"))
    names = _character_names(canon)
    clues = _items(continuity.get("clue_ledger"))
    consequences = _items(continuity.get("unresolved_consequences"))
    cols = st.columns(4)
    cols[0].metric("Revision", continuity.get("revision", "—"))
    cols[1].metric("Knowledge states", len(_items(continuity.get("knowledge_states"))))
    cols[2].metric("Quan hệ", len(_items(continuity.get("relationship_states"))))
    cols[3].metric("Tài sản lặp lại", len(_items(continuity.get("recurring_assets"))))
    st.caption(str(continuity.get("timeline_cursor") or "Chưa có mốc thời gian hiện tại."))

    st.subheader("Hệ quả chưa giải quyết")
    st.dataframe(
        [{
            "Hệ quả": item.get("summary", "—"),
            "Ảnh hưởng": ", ".join(names.get(str(value), str(value)) for value in item.get("affected_ids", [])),
            "Trạng thái": _status_text(item.get("status")),
        } for item in consequences],
        hide_index=True,
        use_container_width=True,
    )

    st.subheader("Sổ đầu mối")
    state_options = ["Tất cả"] + sorted({str(item.get("state") or "unknown") for item in clues})
    state = st.selectbox("Lọc theo trạng thái", state_options)
    visible = clues if state == "Tất cả" else [item for item in clues if item.get("state") == state]
    st.dataframe(
        [{
            "Đầu mối": item.get("clue_id", "—"),
            "Loại": str(item.get("clue_type", "—")).title(),
            "Nội dung": item.get("content", "—"),
            "Trạng thái": _status_text(item.get("state")),
        } for item in visible],
        hide_index=True,
        use_container_width=True,
    )


def _render_next_episode(report: Mapping[str, Any]) -> None:
    import streamlit as st

    contract = _object(_object(report.get("continuity")).get("next_episode_contract"))
    if not contract:
        st.info("Chưa có hợp đồng continuity cho tập tiếp theo.")
        return
    cols = st.columns(3)
    cols[0].metric("Luồng phải tiếp tục", len(contract.get("required_threads", [])))
    cols[1].metric("Nghĩa vụ phải xử lý", len(contract.get("required_obligations", [])))
    cols[2].metric("Mốc đích", contract.get("target_arc_milestone", "—"))
    for transition in _items(contract.get("required_state_transitions")):
        st.info(
            f"**{transition.get('state_id', 'State transition')}**: "
            f"{transition.get('from', '—')} → "
            f"{', '.join(str(value) for value in transition.get('allowed_to', []))}\n\n"
            f"{transition.get('reason', '')}"
        )
    st.subheader("Áp lực nhân vật")
    st.write(str(contract.get("character_pressure") or "Chưa xác định."))
    forbidden = contract.get("forbidden_reveals") if isinstance(contract.get("forbidden_reveals"), list) else []
    if forbidden:
        st.warning("**Chưa được tiết lộ:** " + ", ".join(str(item) for item in forbidden))
    warnings = contract.get("continuity_warnings") if isinstance(contract.get("continuity_warnings"), list) else []
    if warnings:
        st.subheader("Cảnh báo continuity")
        for warning in warnings:
            st.warning(str(warning))
    allowed = contract.get("allowed_new_elements") if isinstance(contract.get("allowed_new_elements"), list) else []
    if allowed:
        st.subheader("Yếu tố mới được phép")
        st.markdown("\n".join(f"- {item}" for item in allowed))


def _render_history(report: Mapping[str, Any]) -> None:
    import streamlit as st

    st.subheader("Episode ledger")
    st.dataframe(
        [{
            "Tập": item.get("episode_number", "—"),
            "Tiêu đề": item.get("title", "—"),
            "Luồng đã giải": len(item.get("resolved_threads", [])),
            "Luồng đã mở": len(item.get("opened_threads", [])),
            "Thay đổi đầu mối": len(item.get("clue_changes", [])),
            "Revision": item.get("anchor_revision", "—"),
        } for item in _items(report.get("episode_ledger"))],
        hide_index=True,
        use_container_width=True,
    )
    st.subheader("Canon change log")
    st.dataframe(
        [{
            "Revision": item.get("revision", "—"),
            "Tập": item.get("episode_number", "—"),
            "Loại": item.get("change_type", "—"),
            "Lý do": item.get("reason", "—"),
        } for item in _items(report.get("canon_change_log"))],
        hide_index=True,
        use_container_width=True,
    )


def _render_technical(report: Mapping[str, Any]) -> None:
    import streamlit as st

    series = _object(report.get("series"))
    continuity = _object(report.get("continuity"))
    st.dataframe(
        [
            {"Thuộc tính": "Schema", "Giá trị": report.get("schema_version", "—")},
            {"Thuộc tính": "Series ID", "Giá trị": series.get("series_id", "—")},
            {"Thuộc tính": "Ngôn ngữ", "Giá trị": series.get("language", "—")},
            {"Thuộc tính": "Thể loại", "Giá trị": series.get("genre", "—")},
            {"Thuộc tính": "Revision", "Giá trị": continuity.get("revision", "—")},
            {"Thuộc tính": "Tập mới nhất", "Giá trị": continuity.get("latest_episode", "—")},
        ],
        hide_index=True,
        use_container_width=True,
    )
    with st.expander("Xem JSON gốc"):
        st.json(report, expanded=False)


def render_series_anchor_report(report: Mapping[str, Any], *, include_technical: bool = True) -> None:
    import streamlit as st

    _validate_series_anchor(report)
    _render_header(report)
    labels = ["Tổng quan", "Canon", "Continuity", "Tập tiếp theo", "Lịch sử tập"]
    if include_technical:
        labels.append("Kỹ thuật")
    tabs = st.tabs(labels)
    overview, canon, continuity, next_episode, history = tabs[:5]
    with overview:
        _render_overview(report)
    with canon:
        _render_canon(report)
    with continuity:
        _render_continuity(report)
    with next_episode:
        _render_next_episode(report)
    with history:
        _render_history(report)
    if include_technical:
        with tabs[5]:
            _render_technical(report)


def render_series_anchor_workspace(*, embedded: bool = False) -> None:
    import streamlit as st

    if not embedded:
        st.set_page_config(page_title="Series Anchor", page_icon=":material/hub:", layout="wide")
    st.header("Series Anchor")
    st.caption("Đọc series_anchor.json theo hướng ưu tiên canon, continuity và yêu cầu cho tập tiếp theo.")
    st.html(
        """<style>
        .sa-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;padding:1.1rem 1.2rem;border:1px solid color-mix(in srgb,currentColor 14%,transparent);border-radius:.8rem;margin:.25rem 0 1rem}
        .sa-heading h2{margin:.1rem 0 .2rem;font-size:1.55rem}.sa-eyebrow{font-size:.75rem;opacity:.65;text-transform:uppercase;letter-spacing:.08em}.sa-muted{font-size:.85rem;opacity:.7}
        .sa-verdict{white-space:nowrap;padding:.45rem .7rem;border-radius:999px;font-weight:600;color:#1f5d9a;background:rgba(45,125,205,.12)}
        @media(max-width:640px){.sa-heading{flex-direction:column}}
        </style>"""
    )
    uploaded = st.file_uploader("Chọn series_anchor.json", type=["json"], key="series_anchor_upload")
    path_text = st.text_input(
        "Hoặc nhập đường dẫn tệp trên máy",
        placeholder=r"D:\project\ai.story\output\series_anchor.json",
        key="series_anchor_path",
    )
    source: Path | BinaryIO | None = uploaded if uploaded is not None else (Path(path_text.strip()) if path_text.strip() else None)
    if source is None:
        st.info("Chọn một tệp JSON hoặc nhập đường dẫn để xem series anchor.")
        return
    try:
        report = _read_report(source)
        _validate_series_anchor(report)
    except (OSError, ValueError) as exc:
        st.error(str(exc))
        return
    render_series_anchor_report(report)


__all__ = ["render_series_anchor_report", "render_series_anchor_workspace"]
