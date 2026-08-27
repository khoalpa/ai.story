"""Unified authoring, validation, quality, continuity, and tools workspace."""
from __future__ import annotations

from pathlib import Path
from typing import Any, BinaryIO, Mapping

from studio.package_quality_report import (
    _items,
    _object,
    _read_report,
    render_package_quality_report,
)
from studio.project_tools import render_project_tools_workspace
from studio.series_anchor_report import (
    _validate_series_anchor,
    render_series_anchor_report,
)
from studio.story_report import _validate_story, render_story_report
from studio.story_validation_report import (
    _all_gates_pass,
    _validate_story_report,
    render_story_validation_report,
)

REPORT_SPECS = {
    "story": ("story.json", "Nội dung", _validate_story),
    "validation": ("story_validation.json", "Kiểm định", _validate_story_report),
    "quality": ("package_quality_report.json", "Chất lượng", None),
    "anchor": ("series_anchor.json", "Series", _validate_series_anchor),
}


def load_story_package(directory: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Load all recognized reports from a directory and return per-file diagnostics."""
    reports: dict[str, dict[str, Any]] = {}
    statuses: dict[str, str] = {}
    if not directory.is_dir():
        return reports, {key: "Không tìm thấy thư mục" for key in REPORT_SPECS}
    for key, (filename, _label, validator) in REPORT_SPECS.items():
        path = directory / filename
        if not path.is_file():
            statuses[key] = "Thiếu"
            continue
        try:
            report = _read_report(path)
            if validator is not None:
                validator(report)
        except (OSError, ValueError) as exc:
            statuses[key] = f"Không hợp lệ: {exc}"
            continue
        reports[key] = report
        statuses[key] = "Có dữ liệu"
    return reports, statuses


def _read_override(source: BinaryIO, key: str) -> dict[str, Any]:
    report = _read_report(source)
    validator = REPORT_SPECS[key][2]
    if validator is not None:
        validator(report)
    return report


def _render_source_selector() -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    import streamlit as st

    default_directory = str((Path.cwd() / "output").resolve())
    directory_text = st.text_input(
        "Thư mục gói nội dung",
        value=st.session_state.get("story_studio_directory", default_directory),
        key="story_studio_directory",
        help="Tự phát hiện story.json, story_validation.json, package_quality_report.json và series_anchor.json.",
    )
    reports, statuses = load_story_package(Path(directory_text.strip()).expanduser())

    with st.expander("Chọn tệp riêng để thay thế dữ liệu trong thư mục"):
        columns = st.columns(2)
        for index, (key, (filename, label, _validator)) in enumerate(REPORT_SPECS.items()):
            uploaded = columns[index % 2].file_uploader(
                f"{label} · {filename}", type=["json"], key=f"story_studio_upload_{key}"
            )
            if uploaded is None:
                continue
            try:
                reports[key] = _read_override(uploaded, key)
                statuses[key] = "Có dữ liệu · tệp thay thế"
            except (OSError, ValueError) as exc:
                reports.pop(key, None)
                statuses[key] = f"Không hợp lệ: {exc}"

    status_columns = st.columns(4)
    for column, (key, (_filename, label, _validator)) in zip(status_columns, REPORT_SPECS.items()):
        status = statuses.get(key, "Thiếu")
        icon = "✓" if status.startswith("Có dữ liệu") else ("—" if status == "Thiếu" else "!")
        column.metric(label, f"{icon} {status}")
    return reports, statuses


def _story_title(reports: Mapping[str, Mapping[str, Any]]) -> str:
    story_meta = _object(_object(reports.get("story")).get("meta"))
    quality_identity = _object(_object(reports.get("quality")).get("package_identity"))
    anchor_series = _object(_object(reports.get("anchor")).get("series"))
    return str(story_meta.get("title") or quality_identity.get("title") or anchor_series.get("title") or "Gói nội dung")


def _render_overview(reports: Mapping[str, Mapping[str, Any]], statuses: Mapping[str, str]) -> None:
    import streamlit as st

    story = _object(reports.get("story"))
    validation = _object(reports.get("validation"))
    quality = _object(reports.get("quality"))
    anchor = _object(reports.get("anchor"))
    commitment = _object(_object(story.get("meta")).get("story_quality_commitment"))
    story_quality = _object(commitment.get("committed_quality_metrics"))
    validation_quality = _object(validation.get("quality"))
    engagement = _object(validation.get("engagement"))
    quality_summary = _object(quality.get("summary"))
    continuity = _object(anchor.get("continuity"))
    blockers = _items(quality.get("blockers"))
    gates = _items(validation.get("gates"))
    material_defects = int(_object(validation.get("summary")).get("material_defect_remaining_count") or 0)

    publish_ready = bool(quality) and quality_summary.get("publish_verdict") == "PASS"
    production_ready = bool(validation) and _all_gates_pass(validation) and material_defects == 0
    missing = [REPORT_SPECS[key][1] for key, value in statuses.items() if value == "Thiếu"]
    if blockers or (validation and not production_ready):
        verdict, message = "Cần xử lý", "Có lỗi hoặc cổng kiểm định cần xem lại trước khi tiếp tục."
        st.error(f"**{verdict}** · {message}")
    elif publish_ready and production_ready:
        st.success("**Sẵn sàng xuất bản** · Kiểm định truyện và chất lượng gói đều đạt.")
    elif production_ready:
        st.info("**Sẵn sàng sản xuất** · Truyện đã đạt kiểm định; cần hoàn tất báo cáo chất lượng gói.")
    else:
        st.warning("**Chưa đủ dữ liệu kết luận** · Bổ sung các báo cáo còn thiếu.")

    st.subheader(_story_title(reports))
    columns = st.columns(6)
    story_score = story_quality.get("final_story_quality_score", validation_quality.get("final_story_quality_score", "—"))
    columns[0].metric("Điểm truyện", f"{story_score}/10" if story_score != "—" else "—")
    columns[1].metric("Cuốn hút", f"{engagement.get('engagement_score', '—')}/10")
    columns[2].metric("Chất lượng gói", f"{quality_summary.get('overall_score', '—')}/100")
    columns[3].metric("Cổng đạt", f"{sum(g.get('status') == 'PASS' for g in gates)}/{len(gates)}")
    columns[4].metric("Lỗi chặn", len(blockers))
    columns[5].metric("Tập mới nhất", continuity.get("latest_episode", "—"))

    st.subheader("Hành động ưu tiên")
    actions: list[str] = []
    if missing:
        actions.append("Bổ sung dữ liệu: " + ", ".join(missing) + ".")
    if material_defects:
        actions.append(f"Mở **Kiểm định** và xử lý {material_defects} lỗi nội dung còn lại.")
    if blockers:
        actions.append(f"Mở **Chất lượng** và xử lý {len(blockers)} lỗi chặn xuất bản.")
    open_threads = sum(item.get("status") == "open" for item in _items(continuity.get("open_threads")))
    if open_threads:
        actions.append(f"Mở **Series** để theo dõi {open_threads} luồng truyện đang mở.")
    if not actions:
        actions.append("Không có hành động bắt buộc; gói nội dung đã sẵn sàng.")
    st.markdown("\n".join(f"- {item}" for item in actions))


def _render_missing(label: str, filename: str, status: str) -> None:
    import streamlit as st

    st.info(f"Chưa thể mở {label}. Hãy thêm `{filename}` vào thư mục gói hoặc chọn tệp thay thế.")
    if status not in {"Thiếu", ""}:
        st.error(status)


def _render_technical(reports: Mapping[str, Mapping[str, Any]]) -> None:
    import streamlit as st

    st.subheader("Dữ liệu kỹ thuật")
    if not reports:
        st.info("Chưa có báo cáo để kiểm tra.")
    for key, report in reports.items():
        filename, label, _validator = REPORT_SPECS[key]
        with st.expander(f"{label} · {filename}"):
            st.caption(f"{len(report):,} trường cấp cao")
            st.json(report, expanded=False)
    st.divider()
    render_project_tools_workspace(embedded=True)


def render_story_studio_workspace(*, embedded: bool = False) -> None:
    import streamlit as st

    if not embedded:
        st.set_page_config(page_title="Story Studio", page_icon=":material/auto_stories:", layout="wide")
    st.header("Story Studio")
    st.caption("Một workspace cho nội dung, kiểm định, chất lượng, canon và công cụ dự án.")
    st.html(
        """<style>
        .story-heading,.sv-heading,.pqr-heading,.sa-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;padding:1.1rem 1.2rem;border:1px solid color-mix(in srgb,currentColor 14%,transparent);border-radius:.8rem;margin:.25rem 0 1rem}
        .story-heading h2,.sv-heading h2,.pqr-heading h2,.sa-heading h2{margin:.1rem 0 .2rem;font-size:1.55rem}
        .story-eyebrow,.sv-eyebrow,.pqr-eyebrow,.sa-eyebrow{font-size:.75rem;opacity:.65;text-transform:uppercase;letter-spacing:.08em}
        .story-muted,.story-cue,.sv-muted,.pqr-muted,.sa-muted{font-size:.82rem;opacity:.68}
        .story-duration,.sv-verdict,.pqr-verdict,.sa-verdict{white-space:nowrap;padding:.45rem .7rem;border-radius:999px;font-weight:600}
        .story-duration{color:#725024;background:rgba(180,130,60,.14)}.sv-pass,.pqr-pass{color:#19733a;background:rgba(50,180,90,.12)}.sv-fail,.pqr-fail{color:#b42318;background:rgba(220,50,40,.12)}.sa-verdict{color:#1f5d9a;background:rgba(45,125,205,.12)}
        .sv-score,.pqr-score{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
        .story-line{display:grid;grid-template-columns:7rem 1fr;gap:.8rem;padding:.7rem .2rem;border-bottom:1px solid color-mix(in srgb,currentColor 10%,transparent)}
        .story-line-meta{display:flex;gap:.5rem;align-items:flex-start;font-size:.75rem;opacity:.68}.story-text{white-space:pre-wrap}.story-dialogue .story-text{padding:.65rem .8rem;border-radius:.65rem;background:rgba(180,130,60,.12)}.story-cue{margin-top:.3rem}
        @media(max-width:640px){.story-heading,.sv-heading,.pqr-heading,.sa-heading{flex-direction:column}.story-line{grid-template-columns:1fr;gap:.25rem}}
        </style>"""
    )
    reports, statuses = _render_source_selector()
    section = st.segmented_control(
        "Khu vực",
        ["Tổng quan", "Nội dung", "Kiểm định", "Chất lượng", "Series", "Công cụ"],
        default="Tổng quan",
        key="story_studio_section",
    ) or "Tổng quan"
    if section == "Tổng quan":
        _render_overview(reports, statuses)
    elif section == "Nội dung" and "story" in reports:
        render_story_report(reports["story"], include_technical=False)
    elif section == "Kiểm định" and "validation" in reports:
        render_story_validation_report(reports["validation"], include_technical=False)
    elif section == "Chất lượng" and "quality" in reports:
        render_package_quality_report(reports["quality"], include_technical=False)
    elif section == "Series" and "anchor" in reports:
        render_series_anchor_report(reports["anchor"], include_technical=False)
    elif section == "Công cụ":
        _render_technical(reports)
    else:
        key = {"Nội dung": "story", "Kiểm định": "validation", "Chất lượng": "quality", "Series": "anchor"}[section]
        filename, label, _validator = REPORT_SPECS[key]
        _render_missing(label, filename, statuses.get(key, "Thiếu"))


__all__ = ["REPORT_SPECS", "load_story_package", "render_story_studio_workspace"]
