"""Friendly Streamlit viewer for package_quality_report.json files."""
from __future__ import annotations

import json
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, BinaryIO, Mapping

MAX_REPORT_BYTES = 5 * 1024 * 1024

DIMENSION_LABELS = {
    "STORY_CONTENT": "Nội dung truyện",
    "NARRATIVE_ENGAGEMENT": "Mức độ cuốn hút",
    "AUDIO_TTS_READABILITY": "Khả năng đọc TTS",
    "PROFILE_FIDELITY": "Đúng hồ sơ nội dung",
    "CONTINUITY": "Tính liên tục",
    "SAFETY": "An toàn",
    "LANDSCAPE_VISUALS": "Hình ảnh ngang",
    "PORTRAIT_VISUALS": "Hình ảnh dọc",
    "CROSS_ORIENTATION_PARITY": "Nhất quán ngang/dọc",
    "COVER_TYPOGRAPHY": "Typography bìa",
    "VISUAL_CONSISTENCY": "Nhất quán hình ảnh",
    "PROVENANCE_INTEGRITY": "Toàn vẹn nguồn gốc",
}

STRENGTH_LABELS = {
    "strength_story_agency": "Nhân vật có chủ động rõ ràng",
    "strength_visual_parity": "Hình ảnh ngang và dọc đồng nhất",
    "strength_cover_typography": "Typography bìa tốt",
}


def _object(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _items(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _read_report(source: Path | BinaryIO) -> dict[str, Any]:
    if isinstance(source, Path):
        if not source.is_file():
            raise ValueError("Không tìm thấy tệp báo cáo.")
        if source.stat().st_size > MAX_REPORT_BYTES:
            raise ValueError("Tệp báo cáo lớn hơn giới hạn 5 MB.")
        raw = source.read_bytes()
    else:
        source.seek(0)
        raw = source.read(MAX_REPORT_BYTES + 1)
        if len(raw) > MAX_REPORT_BYTES:
            raise ValueError("Tệp báo cáo lớn hơn giới hạn 5 MB.")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"JSON không hợp lệ: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Nội dung báo cáo phải là một JSON object.")
    return data


def _short_digest(value: Any) -> str:
    text = str(value or "")
    return f"{text[:8]}…{text[-7:]}" if len(text) > 18 else (text or "—")


def _format_generated_at(value: Any) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return str(value or "Không rõ")


def _status_text(value: Any) -> str:
    return {
        "PASS": "Đạt",
        "FAIL": "Không đạt",
        "EXCELLENT": "Xuất sắc",
        "GOOD": "Tốt",
    }.get(str(value), str(value or "Không rõ"))


def _render_header(report: Mapping[str, Any]) -> None:
    import streamlit as st

    identity = _object(report.get("package_identity"))
    summary = _object(report.get("summary"))
    title = escape(str(identity.get("title") or "Gói nội dung chưa đặt tên"))
    profile = escape(str(identity.get("active_profile") or "—"))
    verdict = str(summary.get("publish_verdict") or "UNKNOWN")
    verdict_class = "pqr-pass" if verdict == "PASS" else "pqr-fail"
    verdict_text = "Sẵn sàng xuất bản" if verdict == "PASS" else "Chưa sẵn sàng xuất bản"
    st.markdown(
        f"""
        <div class="pqr-heading">
          <div><div class="pqr-eyebrow">Báo cáo chất lượng gói nội dung</div>
          <h2>{title}</h2><div class="pqr-muted">Hồ sơ {profile} ·
          Tạo lúc {_format_generated_at(report.get('generated_at_utc'))}</div></div>
          <div class="pqr-verdict {verdict_class}">● {verdict_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_overview(report: Mapping[str, Any]) -> None:
    import streamlit as st

    summary = _object(report.get("summary"))
    dimensions = _items(report.get("dimensions"))
    gates = _items(_object(report.get("story_evidence")).get("gate_results"))
    assets = _items(_object(report.get("image_evidence")).get("asset_results"))
    blockers = _items(report.get("blockers"))

    columns = st.columns(6)
    columns[0].metric("Điểm tổng thể", f"{summary.get('overall_score', '—')}/100")
    columns[1].metric("Xếp loại", _status_text(summary.get("quality_rating")))
    columns[2].metric("Độ phủ", f"{float(summary.get('scoring_coverage_ratio', 0)):.0%}")
    columns[3].metric("Cổng đạt", f"{sum(g.get('status') == 'PASS' for g in gates)}/{len(gates)}")
    columns[4].metric("Ảnh đạt", f"{sum(a.get('gate_status') == 'PASS' for a in assets)}/{len(assets)}")
    columns[5].metric("Lỗi chặn", len(blockers))

    if blockers:
        st.error(f"Có {len(blockers)} lỗi đang chặn xuất bản.")
    elif summary.get("publish_verdict") == "PASS":
        st.success("Tất cả điều kiện bắt buộc đều đạt; gói nội dung có thể xuất bản.")

    st.subheader("Điểm theo tiêu chí")
    for dimension in dimensions:
        dimension_id = str(dimension.get("dimension_id") or "Không rõ")
        score = int(dimension.get("score") or 0)
        label, value = st.columns([4, 1])
        label.write(DIMENSION_LABELS.get(dimension_id, dimension_id.replace("_", " ").title()))
        value.markdown(f"<div class='pqr-score'>{score}/100</div>", unsafe_allow_html=True)
        st.progress(max(0, min(score, 100)) / 100)

    strengths = summary.get("strengths") if isinstance(summary.get("strengths"), list) else []
    if strengths:
        st.subheader("Điểm mạnh được ghi nhận")
        st.markdown(" ".join(f"`✓ {STRENGTH_LABELS.get(str(item), str(item))}`" for item in strengths))


def _render_gates(report: Mapping[str, Any]) -> None:
    import streamlit as st

    gates = _items(_object(report.get("story_evidence")).get("gate_results"))
    if not gates:
        st.info("Báo cáo không chứa kết quả cổng kiểm định.")
        return
    rows = sorted(gates, key=lambda row: row.get("status") == "PASS")
    st.dataframe(
        [{
            "Cổng kiểm định": row.get("gate_id", "—"),
            "Mức độ": str(row.get("severity", "—")).replace("_", " ").title(),
            "Kết quả": _status_text(row.get("status")),
            "Phương pháp": row.get("detector_method", "—"),
        } for row in rows],
        hide_index=True,
        use_container_width=True,
    )


def _render_assets(report: Mapping[str, Any]) -> None:
    import streamlit as st

    evidence = _object(report.get("image_evidence"))
    assets = _items(evidence.get("asset_results"))
    sets = _items(evidence.get("set_results"))
    if sets:
        cols = st.columns(len(sets))
        for col, result in zip(cols, sets):
            group = str(result.get("set") or result.get("orientation") or "—").upper()
            count = result.get("count")
            if count is None and isinstance(evidence.get("asset_results"), list):
                count = sum(_asset_group(asset) == group for asset in assets)
            col.metric(group.title(), f"{count} ảnh" if count is not None else "Chưa có số liệu", _status_text(result.get("status")))
        st.caption("Số ảnh theo báo cáo chất lượng; xem mục Tài nguyên để kiểm tra tệp thực tế và SHA-256.")
    if not assets:
        st.info("Báo cáo không chứa kết quả kiểm tra ảnh.")
        return
    st.dataframe(
        [{
            "Tệp": row.get("path", "—"),
            "Hướng": str(row.get("orientation", "—")).title(),
            "Kích thước": row.get("dimensions", "—"),
            "Điểm": row.get("quality_score", "—"),
            "Kết quả": _status_text(row.get("gate_status")),
        } for row in sorted(assets, key=lambda row: (str(row.get("orientation")), str(row.get("path"))))],
        hide_index=True,
        use_container_width=True,
    )


def _asset_group(asset: Mapping[str, Any]) -> str:
    """Directory identity takes precedence over aspect, especially for characters."""
    path = str(asset.get("path") or "").replace("\\", "/")
    parts = [part for part in path.split("/") if part not in {"", "."}]
    for part in parts[:-1]:
        if part.casefold() in {"landscape", "portrait", "characters"}:
            return part.upper()
    return str(asset.get("orientation") or "").upper()


def _render_story(report: Mapping[str, Any]) -> None:
    import streamlit as st

    evidence = _object(report.get("story_evidence"))
    metrics = _object(evidence.get("recomputable_metrics"))
    cols = st.columns(4)
    cols[0].metric("Số từ", f"{int(metrics.get('total_words', 0)):,}")
    cols[1].metric("Thời lượng ước tính", f"{float(metrics.get('estimated_duration_minutes', 0)):.1f} phút")
    cols[2].metric("Cảnh kể chuyện", metrics.get("narrative_scene_count", "—"))
    cols[3].metric("Tỷ lệ hội thoại", f"{float(metrics.get('direct_dialogue_ratio', 0)):.1%}")
    st.subheader("Chỉ số nội dung")
    st.json(metrics, expanded=True)


def _render_technical(report: Mapping[str, Any]) -> None:
    import streamlit as st

    validation = _object(report.get("validation"))
    identity = _object(report.get("package_identity"))
    st.dataframe(
        [
            {"Thuộc tính": "Report ID", "Giá trị": report.get("report_id", "—")},
            {"Thuộc tính": "Schema", "Giá trị": report.get("schema_version", "—")},
            {"Thuộc tính": "Kiểm tra schema", "Giá trị": _status_text(validation.get("schema_status"))},
            {"Thuộc tính": "Liên kết artifact", "Giá trị": _status_text(validation.get("artifact_binding_status"))},
            {"Thuộc tính": "Tính lại điểm", "Giá trị": _status_text(validation.get("score_recompute_status"))},
            {"Thuộc tính": "Story digest", "Giá trị": _short_digest(identity.get("story_sha256"))},
            {"Thuộc tính": "Report digest", "Giá trị": _short_digest(validation.get("report_digest_sha256"))},
        ],
        hide_index=True,
        use_container_width=True,
    )
    with st.expander("Xem JSON gốc"):
        st.json(report, expanded=False)


def render_package_quality_report(report: Mapping[str, Any], *, include_technical: bool = True) -> None:
    import streamlit as st

    _render_header(report)
    labels = ["Tổng quan", "Cổng kiểm định", "Nội dung truyện", "Tài nguyên ảnh"]
    if include_technical:
        labels.append("Kỹ thuật")
    tabs = st.tabs(labels)
    overview, gates, story, assets = tabs[:4]
    with overview:
        _render_overview(report)
    with gates:
        _render_gates(report)
    with story:
        _render_story(report)
    with assets:
        _render_assets(report)
    if include_technical:
        with tabs[4]:
            _render_technical(report)


def render_package_quality_workspace(*, embedded: bool = False) -> None:
    import streamlit as st

    if not embedded:
        st.set_page_config(page_title="Quality Report", page_icon=":material/fact_check:", layout="wide")
    st.header("Quality Report")
    st.caption("Đọc báo cáo package_quality_report.json theo hướng ưu tiên quyết định và vấn đề cần xử lý.")
    st.html(
        """<style>
        .pqr-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;padding:1.1rem 1.2rem;border:1px solid color-mix(in srgb,currentColor 14%,transparent);border-radius:.8rem;margin:.25rem 0 1rem}
        .pqr-heading h2{margin:.1rem 0 .2rem;font-size:1.55rem}.pqr-eyebrow{font-size:.75rem;opacity:.65;text-transform:uppercase;letter-spacing:.08em}.pqr-muted{font-size:.85rem;opacity:.7}
        .pqr-verdict{white-space:nowrap;padding:.45rem .7rem;border-radius:999px;font-weight:600}.pqr-pass{color:#19733a;background:rgba(50,180,90,.12)}.pqr-fail{color:#b42318;background:rgba(220,50,40,.12)}.pqr-score{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
        @media(max-width:640px){.pqr-heading{flex-direction:column}}
        </style>"""
    )

    uploaded = st.file_uploader("Chọn package_quality_report.json", type=["json"])
    path_text = st.text_input("Hoặc nhập đường dẫn tệp trên máy", placeholder=r"D:\project\ai.story\output\package_quality_report.json")
    source: Path | BinaryIO | None = uploaded if uploaded is not None else (Path(path_text.strip()) if path_text.strip() else None)
    if source is None:
        st.info("Chọn một tệp JSON hoặc nhập đường dẫn để xem báo cáo.")
        return
    try:
        report = _read_report(source)
    except (OSError, ValueError) as exc:
        st.error(str(exc))
        return
    render_package_quality_report(report)


__all__ = ["render_package_quality_report", "render_package_quality_workspace"]
