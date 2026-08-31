"""Unified authoring, validation, quality, continuity, and tools workspace."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO, Mapping

from studio.audio_delivery_report import (
    PRODUCTION_FILES,
    load_audio_delivery,
    read_audio_delivery_override,
    render_audio_delivery,
)
from studio.package_quality_report import (
    _items,
    _object,
    _read_report,
    render_package_quality_report,
)
from studio.project_assets import inspect_report_bindings, render_project_assets
from studio.project_context import (
    STORY_DIRECTORY_KEY,
    STORY_DIRECTORY_WIDGET_KEY,
    choose_story_directory,
    prepare_story_directory_widget,
)
from studio.project_review import required_report_keys, review_package
from studio.project_tools import render_project_tools_workspace
from studio.report_semantics import display_coverage, display_score, gate_summary
from studio.series_anchor_report import (
    _validate_series_anchor,
    render_series_anchor_report,
)
from studio.story_images import render_aspect_cover_gallery
from studio.story_repetition import analyze_story_repetition
from studio.story_report import _validate_story, render_story_report
from studio.story_validation_report import (
    _validate_story_report,
    render_story_validation_report,
)
from studio.video_delivery_report import (
    apply_video_report_override,
    discover_video_report_names,
    load_video_deliveries,
    render_video_deliveries,
    video_report_identity,
)
from studio.workflow_package import WORKFLOW_FILES, read_json
from studio.workflow_views import (
    render_video_plan,
    render_visual_bible,
    render_workflow_summary,
    render_workflow_workspace,
)

REPORT_SPECS = {
    "story": ("story.json", "Nội dung", _validate_story),
    "validation": ("story_validation.json", "Kiểm định", _validate_story_report),
    "quality": ("package_quality_report.json", "Chất lượng", None),
    "anchor": ("series_anchor.json", "Series", _validate_series_anchor),
}

STORY_STUDIO_SECTIONS = (
    "Tổng quan",
    "Gói & quy trình",
    "Nội dung",
    "Kiểm định",
    "Chất lượng",
    "Tài nguyên",
    "Visual Bible",
    "Kế hoạch video",
    "Âm thanh & phụ đề",
    "Video đầu ra",
    "Series",
    "Công cụ",
)

STORY_STUDIO_SECTION_INTROS = {
    "Gói & quy trình": ("Gói truyện & quy trình", "Kiểm tra manifest, ZIP, bytes kế thừa và bằng chứng theo từng stage; không sửa gói nguồn."),
    "Visual Bible": ("Visual Bible Stage 2", "Tra cứu kế hoạch hình ảnh và khóa continuity; không thuộc gói Stage 3/4."),
    "Kế hoạch video": ("Kế hoạch video Stage 4", "Xem timeline, script span, tham chiếu và prompt; không phải video đã render."),
    "Tài nguyên": ("Tài nguyên dự án", "Duyệt ảnh nhân vật, so sánh ngang/dọc và đối chiếu kích thước, SHA-256."),
    "Tổng quan": (
        "Tổng quan Story Studio",
        "Theo dõi mức độ sẵn sàng, chỉ số chính và hành động ưu tiên của gói nội dung.",
    ),
    "Nội dung": (
        "Nội dung truyện",
        "Đọc kịch bản theo vùng truyện và tra cứu dàn ý, nhân vật, giọng đọc, môi trường.",
    ),
    "Kiểm định": (
        "Kiểm định truyện",
        "Xem cổng kiểm định, chất lượng cảnh, lỗi đã tinh chỉnh và bằng chứng kỹ thuật.",
    ),
    "Chất lượng": (
        "Chất lượng gói",
        "Đánh giá kết luận xuất bản, điểm theo tiêu chí, tài nguyên ảnh và lỗi chặn.",
    ),
    "Âm thanh & phụ đề": (
        "Âm thanh & phụ đề",
        "Nghe audio, kiểm tra loudness, đọc timeline phụ đề và xác minh gói bàn giao video.",
    ),
    "Video đầu ra": (
        "Video đầu ra",
        "Xem từng phiên bản video, kết quả kiểm định hình ảnh, phụ đề và mức độ sẵn sàng xuất bản.",
    ),
    "Series": (
        "Series & Continuity",
        "Theo dõi canon, đầu mối, hệ quả và yêu cầu bắt buộc cho tập tiếp theo.",
    ),
    "Công cụ": (
        "Công cụ dự án",
        "Kiểm tra dữ liệu kỹ thuật, JSON nguồn và các lệnh QA cấp repository.",
    ),
}


def load_story_package(directory: Path) -> tuple[dict[str, Any], dict[str, str]]:
    """Load all recognized reports from a directory and return per-file diagnostics."""
    reports: dict[str, Any] = {}
    statuses: dict[str, str] = {}
    if not directory.is_dir():
        keys = (*REPORT_SPECS, *PRODUCTION_FILES)
        return reports, {key: "Không tìm thấy thư mục" for key in keys}
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
    for key, filename in WORKFLOW_FILES.items():
        path = directory / filename
        if not path.is_file():
            statuses[key] = "Thiếu"
            continue
        try:
            if path.stat().st_size > 5 * 1024 * 1024:
                raise ValueError("JSON vượt giới hạn 5 MiB")
            reports[key] = read_json(path.read_bytes())
            statuses[key] = "Có dữ liệu"
        except (OSError, ValueError, RecursionError) as exc:
            statuses[key] = f"Không hợp lệ: {exc}"
    stage = _object(reports.get("workflow")).get("package_stage")
    for key, applicable in (("quality", stage in {"STAGE3", "STAGE4"}),
                            ("visual_bible", stage == "STAGE2"), ("video_prompts", stage == "STAGE4")):
        if stage in {"STAGE1", "STAGE2", "STAGE3", "STAGE4"} and not applicable and statuses.get(key) == "Thiếu":
            statuses[key] = "Chưa áp dụng ở stage này"
    production, production_statuses = load_audio_delivery(directory)
    reports.update(production)
    statuses.update(production_statuses)
    video_variants, video_statuses = load_video_deliveries(directory)
    if video_variants:
        reports["video_deliveries"] = video_variants
    statuses.update(video_statuses)
    return reports, statuses


def _prepare_overrides(state: Any, directory: Path) -> dict[str, bytes]:
    root = str(directory.resolve())
    if state.get("story_override_root") != root:
        for key in list(state):
            if key.startswith("story_studio_upload_") or key == "story_evidence_range":
                state.pop(key, None)
        state["story_overrides"] = {}
        state["story_override_root"] = root
    return state.setdefault("story_overrides", {})


def load_effective_package(directory: Path, state: Any) -> tuple[dict[str, Any], dict[str, str]]:
    """Re-read disk files, then apply durable project-scoped uploaded bytes."""
    reports, statuses = load_story_package(directory)
    overrides = state.get("story_overrides", {}) if state.get("story_override_root") == str(directory.resolve()) else {}
    for key, raw in overrides.items():
        try:
            source = BytesIO(raw)
            if key in REPORT_SPECS:
                reports[key] = _read_override(source, key)
            elif key in PRODUCTION_FILES:
                reports[key] = read_audio_delivery_override(source, key)
            else:
                apply_video_report_override(reports.setdefault("video_deliveries", {}), source, key)
            statuses[key] = "Có dữ liệu · tệp thay thế"
        except (OSError, UnicodeError, ValueError) as exc:
            if key in REPORT_SPECS or key in PRODUCTION_FILES:
                reports.pop(key, None)
            else:
                variant, kind = video_report_identity(key)
                reports.get("video_deliveries", {}).get(variant, {}).pop(kind, None)
            statuses[key] = f"Không hợp lệ: {exc}"
    return reports, statuses


def render_source_provenance(directory: Path, reports: Mapping[str, Any], statuses: Mapping[str, str]) -> None:
    import streamlit as st

    overrides = st.session_state.get("story_overrides", {}) if st.session_state.get("story_override_root") == str(directory.resolve()) else {}
    st.caption(f"Nguồn: {directory.resolve()}" + (f" · {len(overrides)} tệp thay thế đang dùng" if overrides else " · Từ thư mục"))
    with st.expander("Nguồn dữ liệu và độ mới báo cáo"):
        st.caption("Điểm là khai báo của báo cáo; kiểm tra tại máy chỉ đối chiếu bytes và tài nguyên, không chấm lại truyện.")
        st.dataframe([{"Thành phần": key, "Nguồn / trạng thái": value} for key, value in statuses.items()], hide_index=True, width="stretch")
        for row in inspect_report_bindings(directory, reports, story_bytes=overrides.get("story")):
            message = f"{row['report']}: {row['status']}"
            (st.warning if "đã cũ" in row["status"] else st.caption)(message)


def _read_override(source: BinaryIO, key: str) -> dict[str, Any]:
    report = _read_report(source)
    validator = REPORT_SPECS[key][2]
    if validator is not None:
        validator(report)
    return report


def _load_source_from_session() -> tuple[dict[str, Any], dict[str, str]]:
    """Load the active package without rendering the overview-only source controls."""
    import streamlit as st

    default_directory = str((Path.cwd() / "output").resolve())
    prepare_story_directory_widget(st.session_state, default_directory)
    directory_text = str(st.session_state.get(STORY_DIRECTORY_KEY) or default_directory)
    directory = Path(directory_text.strip()).expanduser()
    _prepare_overrides(st.session_state, directory)
    return load_effective_package(directory, st.session_state)


def _render_source_selector() -> tuple[dict[str, Any], dict[str, str]]:
    import streamlit as st

    default_directory = str((Path.cwd() / "output").resolve())
    prepare_story_directory_widget(st.session_state, default_directory)
    directory_col, picker_col = st.columns([6, 1])
    directory_text = directory_col.text_input(
        "Thư mục gói nội dung",
        key=STORY_DIRECTORY_WIDGET_KEY,
        disabled=True,
        help=(
            "Mặc định theo Thư mục dữ liệu dự án. Dùng nút Chọn thư mục để chọn "
            "một thư mục gói nội dung khác."
        ),
    )
    picker_col.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
    picker_col.button(
        "Chọn thư mục",
        key="story_choose_package_directory",
        width="stretch",
        on_click=choose_story_directory,
        args=(st.session_state,),
    )
    st.session_state[STORY_DIRECTORY_KEY] = directory_text
    if st.session_state.get("story_studio_directory_error"):
        st.error(st.session_state["story_studio_directory_error"])
    else:
        st.caption("Mặc định đồng bộ theo Thư mục dữ liệu dự án; lựa chọn riêng chỉ áp dụng cho Story Studio.")
    directory = Path(directory_text.strip()).expanduser()
    overrides = _prepare_overrides(st.session_state, directory)
    reports, statuses = load_effective_package(directory, st.session_state)

    with st.expander("Chọn tệp riêng để thay thế dữ liệu trong thư mục"):
        st.caption("Tệp thay thế dùng chung giữa các mục và Overview của cùng dự án. Không ghi đè tệp trên đĩa; dùng nút bên dưới để trở lại dữ liệu thư mục.")
        def clear_overrides() -> None:
            st.session_state["story_overrides"] = {}
            for key in list(st.session_state):
                if key.startswith("story_studio_upload_"):
                    st.session_state.pop(key, None)
        st.button("Bỏ tất cả tệp thay thế", on_click=clear_overrides)
        columns = st.columns(2)
        for index, (key, (filename, label, _validator)) in enumerate(REPORT_SPECS.items()):
            uploaded = columns[index % 2].file_uploader(
                f"{label} · {filename}", type=["json"], key=f"story_studio_upload_{key}"
            )
            if uploaded is None:
                continue
            overrides[key] = uploaded.getvalue()
            try:
                reports[key] = _read_override(uploaded, key)
                statuses[key] = "Có dữ liệu · tệp thay thế"
            except (OSError, ValueError) as exc:
                reports.pop(key, None)
                statuses[key] = f"Không hợp lệ: {exc}"
        production_uploads = (
            ("audio_quality", "Chất lượng audio", ["json"]),
            ("subtitle", "Phụ đề", ["srt"]),
            ("handoff", "Bàn giao video", ["json"]),
        )
        for index, (key, label, file_types) in enumerate(production_uploads, start=len(REPORT_SPECS)):
            filename = PRODUCTION_FILES[key]
            uploaded = columns[index % 2].file_uploader(
                f"{label} · {filename}",
                type=file_types,
                key=f"story_studio_upload_{key}",
            )
            if uploaded is None:
                continue
            overrides[key] = uploaded.getvalue()
            try:
                reports[key] = read_audio_delivery_override(uploaded, key)
                statuses[key] = "Có dữ liệu · tệp thay thế"
            except (OSError, UnicodeError, ValueError) as exc:
                reports.pop(key, None)
                statuses[key] = f"Không hợp lệ: {exc}"
        video_variants = reports.setdefault("video_deliveries", {})
        video_names = discover_video_report_names(directory)
        offset = len(REPORT_SPECS) + len(production_uploads)
        for index, filename in enumerate(video_names, start=offset):
            variant, kind = video_report_identity(filename)
            label = "Kết quả video" if kind == "result" else "Chất lượng video"
            uploaded = columns[index % 2].file_uploader(
                f"{label} · {filename}",
                type=["json"],
                key=f"story_studio_upload_video_{filename}",
            )
            if uploaded is None:
                continue
            overrides[filename] = uploaded.getvalue()
            try:
                apply_video_report_override(video_variants, uploaded, filename)
                statuses[filename] = "Có dữ liệu · tệp thay thế"
            except (OSError, ValueError) as exc:
                video_variants.setdefault(variant, {}).pop(kind, None)
                statuses[filename] = f"Không hợp lệ: {exc}"

    render_source_provenance(directory, reports, statuses)
    status_columns = st.columns(4)
    for column, (key, (_filename, label, _validator)) in zip(status_columns, REPORT_SPECS.items()):
        status = statuses.get(key, "Thiếu")
        icon = "✓" if status.startswith("Có dữ liệu") else ("—" if status == "Thiếu" else "!")
        column.metric(label, f"{icon} {status}")
    st.caption("ĐẦU RA SẢN XUẤT")
    production_columns = st.columns(3)
    for column, (key, label) in zip(
        production_columns,
        (("audio_quality", "Audio"), ("subtitle", "Phụ đề"), ("handoff", "Handoff")),
    ):
        status = statuses.get(key, "Thiếu")
        icon = "✓" if status.startswith("Có dữ liệu") else ("—" if status == "Thiếu" else "!")
        column.metric(label, f"{icon} {status}")
    video_variants = reports.get("video_deliveries", {})
    st.caption("ĐẦU RA VIDEO")
    if isinstance(video_variants, Mapping) and video_variants:
        video_columns = st.columns(min(4, len(video_variants)))
        for column, (variant, variant_reports) in zip(video_columns, sorted(video_variants.items())):
            result_ok = isinstance(variant_reports, Mapping) and "result" in variant_reports
            quality_ok = isinstance(variant_reports, Mapping) and "quality" in variant_reports
            column.metric(
                variant.replace("video_", "").replace("_", " ").title(),
                f"{'✓' if result_ok and quality_ok else '!'} {int(result_ok) + int(quality_ok)}/2 báo cáo",
            )
    else:
        st.info("Chưa phát hiện báo cáo video.")
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
    material_defects = int(_object(validation.get("summary")).get("material_defect_remaining_count") or 0)
    repetition = analyze_story_repetition(story) if story else {"summary": {}}
    repetition_summary = _object(repetition.get("summary"))
    repetition_pairs = int(repetition_summary.get("pair_count") or 0)
    repeated_sentences = int(repetition_summary.get("affected_sentence_count") or 0)

    image_root = Path(str(st.session_state.get(STORY_DIRECTORY_KEY) or Path.cwd() / "output")).expanduser()
    review = review_package(image_root, reports, statuses, st.session_state)
    render_workflow_summary(review["workflow"])
    publish_ready = review["package_ready"]
    production_ready = review["story_ready"]
    missing = [
        label
        for key, (_filename, label, _validator) in REPORT_SPECS.items()
        if statuses.get(key) == "Thiếu" and key in required_report_keys(reports)
    ]
    if review["workflow"]["stage"]:
        st.info("Trạng thái gói nằm trong quy trình bên trên. Audio/video render được theo dõi độc lập.")
    elif blockers or review["issues"] or (validation and not production_ready):
        verdict, message = "Cần xử lý", "Có lỗi hoặc cổng kiểm định cần xem lại trước khi tiếp tục."
        st.error(f"**{verdict}** · {message}")
    elif publish_ready and production_ready:
        st.success("**Gói nội dung đạt** · Theo báo cáo truyện và chất lượng gói; chưa phải kết luận xuất bản audio/video.")
    elif production_ready:
        st.info("**Truyện đạt theo báo cáo** · Cần hoàn tất các kiểm tra chất lượng gói và tài nguyên bên dưới.")
    else:
        st.warning("**Chưa đủ dữ liệu kết luận** · Bổ sung các báo cáo còn thiếu.")

    st.subheader("Hành động ưu tiên")
    actions: list[str] = [f"Mở **{issue['section']}**: {issue['text']}" for issue in review["issues"]]
    if review["asset_issues"]:
        actions.append(f"Mở **Tài nguyên**: {len(review['asset_issues'])} ảnh cần kiểm tra.")
    if missing:
        actions.append("Bổ sung dữ liệu: " + ", ".join(missing) + ".")
    if material_defects:
        actions.append(f"Mở **Kiểm định** và xử lý {material_defects} lỗi nội dung còn lại.")
    if blockers:
        actions.append(f"Mở **Chất lượng** và xử lý {len(blockers)} lỗi chặn xuất bản.")
    if repetition_pairs:
        actions.append(f"Mở **Nội dung → Lặp câu** để xem lại {repetition_pairs} cặp câu lặp hoặc gần trùng.")
    open_threads = sum(item.get("status") == "open" for item in _items(continuity.get("open_threads")))
    if open_threads:
        actions.append(f"Mở **Series** để theo dõi {open_threads} luồng truyện đang mở.")
    if not actions:
        actions.append("Không có hành động bắt buộc cho gói nội dung." if publish_ready else "Chưa đủ dữ liệu kết luận; kiểm tra nguồn báo cáo.")
    def open_section(section: str) -> None:
        st.session_state["story_studio_section"] = section
    for index, item in enumerate(actions):
        text_col, button_col = st.columns([4, 1])
        text_col.markdown(f"- {item}")
        section = next((name for name in STORY_STUDIO_SECTIONS if f"**{name}" in item), None)
        if section:
            button_col.button(f"Mở {section}", key=f"story_priority_{index}", on_click=open_section, args=(section,))


    st.subheader(_story_title(reports))
    columns = [*st.columns(4), *st.columns(3)]
    story_score = story_quality.get("final_story_quality_score", validation_quality.get("final_story_quality_score", "—"))
    columns[0].metric("Điểm truyện", display_score(story_score))
    columns[1].metric("Cuốn hút", display_score(engagement.get("engagement_score")))
    columns[2].metric("Chất lượng gói", f"{quality_summary.get('overall_score', '—')}/100")
    st.caption("Độ phủ chấm điểm gói: " + display_coverage(quality_summary.get("scoring_coverage_ratio")))
    result = gate_summary(validation)
    columns[3].metric("Cổng đạt", str(result["passed"]))
    st.caption(result["label"])
    columns[4].metric("Lỗi chặn", len(blockers))
    columns[5].metric("Tập mới nhất", continuity.get("latest_episode", "—"))
    columns[6].metric("Câu lặp cần xem", repeated_sentences)

    image_root = Path(str(st.session_state.get("story_studio_directory") or Path.cwd() / "output")).expanduser()
    st.subheader("Hình ảnh truyện")
    render_aspect_cover_gallery(image_root, key_prefix="story_overview_cover")



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
        if key not in REPORT_SPECS:
            continue
        filename, label, _validator = REPORT_SPECS[key]
        with st.expander(f"{label} · {filename}"):
            st.caption(f"{len(report):,} trường cấp cao")
            st.json(report, expanded=False)
    st.divider()
    render_project_tools_workspace(embedded=True)


def render_story_studio_navigation() -> str:
    """Render the shared Story Studio section selector."""
    import streamlit as st

    selected = st.segmented_control(
        "Khu vực",
        STORY_STUDIO_SECTIONS,
        default="Tổng quan" if "story_studio_section" not in st.session_state else None,
        key="story_studio_section",
    ) or "Tổng quan"
    return selected if selected in STORY_STUDIO_SECTIONS else "Tổng quan"


def render_story_studio_workspace(
    *, embedded: bool = False, show_navigation: bool = True
) -> None:
    import streamlit as st

    if not embedded:
        st.set_page_config(page_title="Story Studio", page_icon=":material/auto_stories:", layout="wide")
        st.header("Story Studio")
    if show_navigation:
        section = render_story_studio_navigation()
    else:
        section = str(st.session_state.get("story_studio_section") or "Tổng quan")
        if section not in STORY_STUDIO_SECTIONS:
            section = "Tổng quan"
    heading, caption = STORY_STUDIO_SECTION_INTROS[section]
    st.header(heading)
    st.caption(caption)
    if section == "Tổng quan":
        reports, statuses = _render_source_selector()
        _render_overview(reports, statuses)
        return

    reports, statuses = _load_source_from_session()
    directory = Path(str(st.session_state.get(STORY_DIRECTORY_KEY) or Path.cwd() / "output")).expanduser()
    render_source_provenance(directory, reports, statuses)
    if section == "Gói & quy trình":
        render_workflow_workspace(directory, reports, st.session_state)
    elif section == "Visual Bible":
        render_visual_bible(reports.get("visual_bible", {}))
    elif section == "Kế hoạch video":
        render_video_plan(reports.get("video_prompts", {}), root=directory)
    elif section == "Nội dung" and "story" in reports:
        directory = Path(str(st.session_state.get("story_studio_directory") or Path.cwd() / "output")).expanduser()
        render_story_report(reports["story"], include_technical=False, images_root=directory)
    elif section == "Kiểm định" and "validation" in reports:
        render_story_validation_report(reports["validation"], include_technical=False)
    elif section == "Chất lượng" and "quality" in reports:
        render_package_quality_report(reports["quality"], include_technical=False)
    elif section == "Tài nguyên":
        render_project_assets(directory, reports)
    elif section == "Âm thanh & phụ đề":
        directory = Path(str(st.session_state.get("story_studio_directory") or Path.cwd() / "output")).expanduser()
        render_audio_delivery(reports, directory)
    elif section == "Video đầu ra":
        directory = Path(str(st.session_state.get("story_studio_directory") or Path.cwd() / "output")).expanduser()
        variants = reports.get("video_deliveries", {})
        render_video_deliveries(variants if isinstance(variants, Mapping) else {}, directory)
    elif section == "Series" and "anchor" in reports:
        render_series_anchor_report(reports["anchor"], include_technical=False)
    elif section == "Series" and "anchor" not in required_report_keys(reports):
        st.info("Series không bắt buộc theo manifest/profile hoặc khai báo standalone hợp lệ. Metadata series/tập được giữ để tham khảo.")
    elif section == "Công cụ":
        _render_technical(reports)
    else:
        key = {"Nội dung": "story", "Kiểm định": "validation", "Chất lượng": "quality", "Series": "anchor"}[section]
        filename, label, _validator = REPORT_SPECS[key]
        _render_missing(label, filename, statuses.get(key, "Thiếu"))


__all__ = [
    "REPORT_SPECS",
    "STORY_STUDIO_SECTION_INTROS",
    "STORY_STUDIO_SECTIONS",
    "load_story_package",
    "render_story_studio_navigation",
    "render_story_studio_workspace",
]
