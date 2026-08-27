"""Friendly Streamlit viewer for story_validation.json files."""
from __future__ import annotations

from collections import Counter
from html import escape
from pathlib import Path
from typing import Any, BinaryIO, Mapping

from studio.package_quality_report import _items, _object, _read_report, _short_digest

QUALITY_LABELS = {
    "causality": "Quan hệ nhân quả",
    "character_agency": "Chủ động của nhân vật",
    "conflict_escalation": "Leo thang xung đột",
    "emotional_relationship_delta": "Biến chuyển cảm xúc",
    "dialogue_naturalness": "Độ tự nhiên của hội thoại",
    "subtext_and_thematic_restraint": "Tiết chế chủ đề",
    "progression_density": "Mật độ tiến triển",
    "climax_and_payoff": "Cao trào và hồi đáp",
}

ZONE_LABELS = {
    "OPENING": "Mở đầu",
    "INTRODUCTION": "Giới thiệu",
    "DEVELOPMENT": "Phát triển",
    "CLIMAX": "Cao trào",
    "FALLING": "Hạ nhiệt",
    "ENDING": "Kết thúc",
}

SEVERITY_LABELS = {
    "PUBLISH_BLOCKER": "Chặn xuất bản",
    "QUALITY_BLOCKER": "Chặn chất lượng",
    "MATERIAL": "Quan trọng",
    "ADVISORY": "Khuyến nghị",
}


def _validate_story_report(report: Mapping[str, Any]) -> None:
    required = {"summary", "quality", "engagement", "gates", "scene_zone_map"}
    missing = sorted(required.difference(report))
    if missing:
        raise ValueError(
            "Tệp không đúng định dạng story_validation.json; thiếu: "
            + ", ".join(missing)
        )


def _all_gates_pass(report: Mapping[str, Any]) -> bool:
    gates = _items(report.get("gates"))
    return bool(gates) and all(gate.get("status") == "PASS" for gate in gates)


def _status_text(value: Any) -> str:
    return {
        "PASS": "Đạt",
        "FAIL": "Không đạt",
        "ASSESSED_PASS": "Đánh giá đạt",
        "REFINEMENT_ACCEPTED": "Đã chấp nhận",
    }.get(str(value), str(value or "Không rõ").replace("_", " ").title())


def _render_header(report: Mapping[str, Any]) -> None:
    import streamlit as st

    summary = _object(report.get("summary"))
    profile = escape(str(report.get("active_profile") or "—"))
    ready = _all_gates_pass(report) and int(summary.get("material_defect_remaining_count") or 0) == 0
    status_class = "sv-pass" if ready else "sv-fail"
    status_text = "Sẵn sàng sản xuất" if ready else "Cần xem lại trước sản xuất"
    st.markdown(
        f"""
        <div class="sv-heading">
          <div><div class="sv-eyebrow">Kiểm định truyện</div>
          <h2>Story validation</h2><div class="sv-muted">Hồ sơ {profile} ·
          {int(summary.get('total_words') or 0):,} từ · khoảng
          {float(summary.get('estimated_duration_minutes') or 0):.1f} phút</div></div>
          <div class="sv-verdict {status_class}">● {status_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_overview(report: Mapping[str, Any]) -> None:
    import streamlit as st

    summary = _object(report.get("summary"))
    quality = _object(report.get("quality"))
    engagement = _object(report.get("engagement"))
    dialogue = _object(report.get("dialogue_audio"))
    gates = _items(report.get("gates"))
    passed = sum(gate.get("status") == "PASS" for gate in gates)

    cols = st.columns(6)
    cols[0].metric("Chất lượng", f"{float(quality.get('final_story_quality_score') or 0):.2f}/10")
    cols[1].metric("Cuốn hút", f"{float(engagement.get('engagement_score') or 0):.1f}/10")
    cols[2].metric("Cổng đạt", f"{passed}/{len(gates)}")
    cols[3].metric("Lỗi còn lại", int(summary.get("material_defect_remaining_count") or 0))
    cols[4].metric("Cảnh", int(summary.get("narrative_scene_count") or 0))
    cols[5].metric("Hội thoại", f"{float(dialogue.get('actual_direct_dialogue_ratio') or 0):.1%}")

    if _all_gates_pass(report):
        st.success("Tất cả cổng kiểm định đều đạt.")
    else:
        st.error(f"Có {len(gates) - passed} cổng kiểm định chưa đạt.")

    st.subheader("Điểm theo tiêu chí")
    for key, label in QUALITY_LABELS.items():
        score = float(quality.get(key) or 0)
        label_col, score_col = st.columns([5, 1])
        label_col.write(label)
        score_col.markdown(f"<div class='sv-score'>{score:.1f}/2</div>", unsafe_allow_html=True)
        st.progress(max(0.0, min(score / 2.0, 1.0)))

    st.subheader("Chỉ báo mức độ cuốn hút")
    engagement_cols = st.columns(4)
    engagement_cols[0].metric("Tò mò mở đầu", f"{float(engagement.get('opening_curiosity_seconds') or 0):.1f} giây")
    engagement_cols[1].metric("Câu hỏi đang mở", int(engagement.get("audience_question_open_count") or 0))
    engagement_cols[2].metric("Câu hỏi quá hạn", int(engagement.get("audience_question_overdue_count") or 0))
    engagement_cols[3].metric("Cảnh phẳng", int(engagement.get("flat_scene_count") or 0))


def _render_scenes(report: Mapping[str, Any]) -> None:
    import streamlit as st

    scenes = _items(report.get("scene_zone_map"))
    if not scenes:
        st.info("Báo cáo không chứa bản đồ cảnh.")
        return
    rows = [{
        "Cảnh": scene.get("scene_id", "—"),
        "Vùng truyện": ", ".join(ZONE_LABELS.get(str(zone), str(zone)) for zone in scene.get("zones", [])),
        "Phạm vi": f"{scene.get('item_start', '—')}–{scene.get('item_end', '—')}",
        "Điểm": scene.get("scene_quality_score", "—"),
        "Thay đổi vật chất": len(scene.get("material_delta_ids", [])),
    } for scene in scenes]
    st.dataframe(rows, hide_index=True, use_container_width=True)

    scene_ids = [str(scene.get("scene_id") or "—") for scene in scenes]
    selected_id = st.selectbox("Xem chi tiết cảnh", scene_ids)
    selected = next(scene for scene in scenes if str(scene.get("scene_id") or "—") == selected_id)
    cols = st.columns(4)
    cols[0].metric("Điểm", f"{float(selected.get('scene_quality_score') or 0):.1f}/10")
    cols[1].metric("Mục bắt đầu", selected.get("item_start", "—"))
    cols[2].metric("Mục kết thúc", selected.get("item_end", "—"))
    cols[3].metric("Material delta", len(selected.get("material_delta_ids", [])))


def _render_gates(report: Mapping[str, Any]) -> None:
    import streamlit as st

    gates = _items(report.get("gates"))
    if not gates:
        st.info("Báo cáo không chứa cổng kiểm định.")
        return
    severity_counts = Counter(str(gate.get("severity") or "UNKNOWN") for gate in gates)
    cols = st.columns(max(1, len(severity_counts)))
    for col, (severity, count) in zip(cols, sorted(severity_counts.items())):
        passed = sum(gate.get("status") == "PASS" and gate.get("severity") == severity for gate in gates)
        col.metric(SEVERITY_LABELS.get(severity, severity.replace("_", " ").title()), f"{passed}/{count}")

    severity_options = ["Tất cả"] + sorted(severity_counts, key=lambda item: SEVERITY_LABELS.get(item, item))
    severity = st.selectbox(
        "Lọc theo mức độ",
        severity_options,
        format_func=lambda item: SEVERITY_LABELS.get(item, item),
    )
    visible = gates if severity == "Tất cả" else [gate for gate in gates if gate.get("severity") == severity]
    visible = sorted(visible, key=lambda gate: (gate.get("status") == "PASS", str(gate.get("gate_id"))))
    st.dataframe(
        [{
            "Cổng kiểm định": gate.get("gate_id", "—"),
            "Mức độ": SEVERITY_LABELS.get(str(gate.get("severity")), str(gate.get("severity", "—"))),
            "Kết quả": _status_text(gate.get("status")),
            "Vị trí bằng chứng": len(gate.get("locators", [])),
        } for gate in visible],
        hide_index=True,
        use_container_width=True,
    )


def _render_refinement(report: Mapping[str, Any]) -> None:
    import streamlit as st

    refinement = _object(report.get("refinement"))
    defects = _items(refinement.get("defect_map"))
    closures = {str(item.get("defect_id")): item for item in _items(refinement.get("defect_closure_records"))}
    cols = st.columns(3)
    cols[0].metric("Trạng thái", _status_text(refinement.get("refinement_status")))
    cols[1].metric("Số vòng", int(refinement.get("refinement_round_count") or 0))
    cols[2].metric("Lỗi đã đóng", f"{len(closures)}/{len(defects)}")
    if not defects:
        st.info("Không có lỗi tinh chỉnh được ghi nhận.")
        return
    for defect in defects:
        defect_id = str(defect.get("defect_id") or "—")
        closure = _object(closures.get(defect_id))
        closed = closure.get("detector_rerun_result") == "PASS"
        with st.expander(f"{'✓' if closed else '!' } {defect_id} · {defect.get('defect_class', '—')}", expanded=not closed):
            st.write(str(defect.get("evidence") or "Không có mô tả."))
            st.caption(f"Phạm vi sửa tối thiểu: {defect.get('lowest_safe_repair_level', '—')}")
            if closure:
                st.success(str(closure.get("post_evidence") or "Đã kiểm tra lại và đạt."))


def _render_technical(report: Mapping[str, Any]) -> None:
    import streamlit as st

    graph = _object(report.get("evidence_graph"))
    rows = [
        {"Thuộc tính": "Schema", "Giá trị": report.get("schema_version", "—")},
        {"Thuộc tính": "Prompt version", "Giá trị": report.get("prompt_version", "—")},
        {"Thuộc tính": "Active profile", "Giá trị": report.get("active_profile", "—")},
        {"Thuộc tính": "Evidence nodes", "Giá trị": len(_items(graph.get("nodes")))},
        {"Thuộc tính": "Dependency edges", "Giá trị": len(_items(graph.get("edges")))},
        {"Thuộc tính": "Story SHA-256", "Giá trị": _short_digest(report.get("story_sha256"))},
        {"Thuộc tính": "Commitment digest", "Giá trị": _short_digest(report.get("story_quality_commitment_digest_sha256"))},
        {"Thuộc tính": "Evidence graph digest", "Giá trị": _short_digest(graph.get("graph_digest_sha256"))},
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)
    with st.expander("Xem JSON gốc"):
        st.json(report, expanded=False)


def render_story_validation_report(report: Mapping[str, Any], *, include_technical: bool = True) -> None:
    import streamlit as st

    _validate_story_report(report)
    _render_header(report)
    labels = ["Tổng quan", "Cảnh truyện", "Cổng kiểm định", "Tinh chỉnh"]
    if include_technical:
        labels.append("Kỹ thuật")
    tabs = st.tabs(labels)
    overview, scenes, gates, refinement = tabs[:4]
    with overview:
        _render_overview(report)
    with scenes:
        _render_scenes(report)
    with gates:
        _render_gates(report)
    with refinement:
        _render_refinement(report)
    if include_technical:
        with tabs[4]:
            _render_technical(report)


def render_story_validation_workspace(*, embedded: bool = False) -> None:
    import streamlit as st

    if not embedded:
        st.set_page_config(page_title="Story Validation", page_icon=":material/rule:", layout="wide")
    st.header("Story Validation")
    st.caption("Đọc story_validation.json theo hướng ưu tiên mức độ sẵn sàng và nội dung cần sửa.")
    st.html(
        """<style>
        .sv-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;padding:1.1rem 1.2rem;border:1px solid color-mix(in srgb,currentColor 14%,transparent);border-radius:.8rem;margin:.25rem 0 1rem}
        .sv-heading h2{margin:.1rem 0 .2rem;font-size:1.55rem}.sv-eyebrow{font-size:.75rem;opacity:.65;text-transform:uppercase;letter-spacing:.08em}.sv-muted{font-size:.85rem;opacity:.7}
        .sv-verdict{white-space:nowrap;padding:.45rem .7rem;border-radius:999px;font-weight:600}.sv-pass{color:#19733a;background:rgba(50,180,90,.12)}.sv-fail{color:#b42318;background:rgba(220,50,40,.12)}.sv-score{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
        @media(max-width:640px){.sv-heading{flex-direction:column}}
        </style>"""
    )
    uploaded = st.file_uploader("Chọn story_validation.json", type=["json"], key="story_validation_upload")
    path_text = st.text_input(
        "Hoặc nhập đường dẫn tệp trên máy",
        placeholder=r"D:\project\ai.story\output\story_validation.json",
        key="story_validation_path",
    )
    source: Path | BinaryIO | None = uploaded if uploaded is not None else (Path(path_text.strip()) if path_text.strip() else None)
    if source is None:
        st.info("Chọn một tệp JSON hoặc nhập đường dẫn để xem báo cáo.")
        return
    try:
        report = _read_report(source)
        _validate_story_report(report)
    except (OSError, ValueError) as exc:
        st.error(str(exc))
        return
    render_story_validation_report(report)


__all__ = ["render_story_validation_report", "render_story_validation_workspace"]
