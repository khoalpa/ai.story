"""Interactive Summary authoring, validation, projection, and packaging workspace."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any, Mapping

from studio.artifact_validation import strict_json_bytes
from studio.project_context import PROJECT_DIRECTORY_KEY
from studio.summary_capabilities import detect_summary_capabilities
from studio.summary_editing import replace_summary_rows, update_summary_meta
from studio.summary_exports import affected_artifacts, export_citations
from studio.summary_ingestion import build_summary_draft, extract_source
from studio.summary_migration import (
    migrate_summary_document,
    normalize_summary_v110_ids,
)
from studio.summary_package import (
    PROJECTION_TARGETS,
    build_summary_package_bytes,
    canonical_json_bytes,
    project_summary_artifacts,
)
from studio.summary_preview import estimate_summary_timing, preview_projection_mapping
from studio.summary_schema import validate_summary_document
from studio.summary_visual import build_summary_visual_plan, visual_density
from studio.summary_visual_schema import validate_summary_visual_plan
from studio.summary_workflow import (
    complete_summary_stage,
    plan_summary_completion,
    repair_summary_manifest,
    revalidate_summary_media,
    summary_manifest_issues,
)
from studio.ui_components import (
    render_empty_state,
    render_summary_card,
    render_workspace_header,
)

SUMMARY_EDITOR_KEY = "summary_json_editor"
SUMMARY_EDITOR_PENDING_KEY = "summary_json_editor_pending"
SUMMARY_STEPS = ("Nguồn", "Trích xuất", "Nội dung", "Lời đọc & cảnh", "Xuất bản")


def queue_summary_editor_update(state: Any, text: str) -> None:
    """Queue canonical text for the next run, before the editor widget exists."""
    state[SUMMARY_EDITOR_PENDING_KEY] = text


def apply_pending_summary_editor_update(state: Any) -> bool:
    """Apply a queued editor value before Streamlit instantiates the widget."""
    if SUMMARY_EDITOR_PENDING_KEY not in state:
        return False
    state[SUMMARY_EDITOR_KEY] = state.pop(SUMMARY_EDITOR_PENDING_KEY)
    return True


def parse_summary_text(text: str) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        document = dict(strict_json_bytes(text.encode("utf-8")))
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        return None, [f"JSON không hợp lệ: {exc}"]
    errors = validate_summary_document(document)
    return document, errors


def summary_metrics(document: Mapping[str, Any]) -> dict[str, int]:
    return {
        "Nguồn": len(document.get("sources", [])),
        "Claims": len(document.get("claims", [])),
        "Đoạn lời đọc": len(document.get("narration", [])),
        "Số liệu": len(document.get("numeric_facts", [])),
    }


def _render_overview(st: Any, document: Mapping[str, Any]) -> None:
    metrics = summary_metrics(document)
    columns = st.columns(4)
    for column, (label, value) in zip(columns, metrics.items()):
        with column:
            render_summary_card(label, value)
    meta = document["meta"]
    st.caption(
        f"{meta['output_type']} · {meta['source_genre']} · {meta['style']} · "
        f"{meta['language']} · image_mode={meta['image_mode']}"
    )
    st.markdown("#### Phạm vi nguồn")
    st.dataframe(
        [
            {
                "ID": row["source_id"],
                "Tiêu đề": row["title"],
                "Loại": row["type"],
                "Phạm vi": row["scope_read"],
                "SHA-256": row.get("sha256") or "—",
            }
            for row in document["sources"]
        ],
        hide_index=True,
        width="stretch",
    )
    with st.expander("Chỉnh metadata", expanded=False):
        meta = document["meta"]
        output_types = (
            "SUMMARY",
            "ANALYSIS",
            "SUMMARY_ANALYSIS",
            "STUDY_GUIDE",
            "EXECUTIVE_BRIEF",
            "NARRATED_SCRIPT",
            "CHAPTER_BY_CHAPTER",
            "COMPARE_SOURCES",
            "ARGUMENT_MAP",
            "TIMELINE",
            "CONCEPT_MAP",
            "CHARACTER_MAP",
            "DATA_BRIEF",
            "ACTION_ITEMS",
            "TEACHING_SCRIPT",
            "FAQ",
            "QUESTION_ANSWER",
            "CUSTOM",
        )
        styles = (
            "NEUTRAL_CLEAR",
            "ACADEMIC",
            "POPULAR",
            "STORYTELLING",
            "CRITICAL",
            "EXECUTIVE",
            "DOCUMENTARY",
            "CUSTOM",
        )
        with st.form("summary_meta_form"):
            title = st.text_input("Tiêu đề", value=str(meta["title"]))
            audience = st.text_input("Đối tượng", value=str(meta["audience"]))
            output_type = st.selectbox(
                "Loại đầu ra",
                output_types,
                index=output_types.index(meta["output_type"]),
            )
            style = st.selectbox(
                "Phong cách", styles, index=styles.index(meta["style"])
            )
            image_mode = st.selectbox(
                "Image mode",
                ("SCENE", "ZONE"),
                index=0 if meta["image_mode"] == "SCENE" else 1,
            )
            coverage = st.selectbox(
                "Coverage",
                ("FULL_SUMMARY", "KEY_SCENES"),
                index=0 if meta["coverage"] == "FULL_SUMMARY" else 1,
            )
            submitted = st.form_submit_button("Áp dụng metadata", type="primary")
        if submitted:
            try:
                updated = update_summary_meta(
                    document,
                    {
                        "title": title,
                        "audience": audience,
                        "output_type": output_type,
                        "style": style,
                        "image_mode": image_mode,
                        "coverage": coverage,
                    },
                )
            except ValueError as exc:
                st.error(str(exc))
            else:
                queue_summary_editor_update(
                    st.session_state, canonical_json_bytes(updated).decode("utf-8")
                )
                st.session_state.pop("summary_projection_files", None)
                st.session_state.pop("summary_package_bytes", None)
                st.session_state.pop("summary_visual_plan", None)
                st.rerun()


def _records(value: Any) -> list[dict[str, Any]]:
    if hasattr(value, "to_dict"):
        return [dict(row) for row in value.to_dict("records")]
    return [dict(row) for row in value]


def _render_claims(st: Any, document: Mapping[str, Any]) -> None:
    field = st.selectbox(
        "Bảng dữ liệu",
        ("claims", "claim_relations", "numeric_facts", "glossary"),
        key="summary_editor_table",
    )
    edited = st.data_editor(
        document[field],
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        key=f"summary_data_editor_{field}",
    )
    if st.button("Áp dụng thay đổi bảng", key=f"summary_apply_{field}"):
        try:
            updated = replace_summary_rows(document, field, _records(edited))
        except (TypeError, ValueError) as exc:
            st.error(str(exc))
        else:
            queue_summary_editor_update(
                st.session_state, canonical_json_bytes(updated).decode("utf-8")
            )
            st.session_state.pop("summary_projection_files", None)
            st.session_state.pop("summary_package_bytes", None)
            st.session_state.pop("summary_visual_plan", None)
            st.rerun()


def _render_narration(st: Any, document: Mapping[str, Any]) -> None:
    rate = st.number_input(
        "Tốc độ ước tính (từ/phút)",
        min_value=50,
        max_value=300,
        value=150,
        step=5,
        key="summary_narration_rate",
    )
    timing = estimate_summary_timing(document, rate_per_minute=float(rate))
    columns = st.columns(4)
    columns[0].metric("Số từ", timing["word_count"])
    columns[1].metric("Ước tính", f"{timing['estimated_minutes']:.2f} phút")
    columns[2].metric(
        "Mục tiêu",
        f"{timing['target_minutes']} phút" if timing["target_minutes"] else "—",
    )
    columns[3].metric(
        "Chênh lệch",
        f"{timing['delta_percent']}%" if timing["delta_percent"] is not None else "—",
    )

    edited = st.data_editor(
        document["narration"],
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        key="summary_narration_editor",
    )
    if st.button("Áp dụng lời đọc", type="primary"):
        try:
            updated = replace_summary_rows(document, "narration", _records(edited))
        except (TypeError, ValueError) as exc:
            st.error(str(exc))
        else:
            invalidated = affected_artifacts(["narration"])
            st.session_state["summary_invalidated_artifacts"] = invalidated
            queue_summary_editor_update(
                st.session_state, canonical_json_bytes(updated).decode("utf-8")
            )
            st.session_state.pop("summary_projection_files", None)
            st.session_state.pop("summary_package_bytes", None)
            st.session_state.pop("summary_projection_preview", None)
            st.session_state.pop("summary_visual_plan", None)
            st.rerun()
    invalidated = st.session_state.get("summary_invalidated_artifacts", ())
    if invalidated:
        st.warning("Cần dựng lại: " + ", ".join(invalidated))

    if st.button("Preview narration → zone → scene → clip"):
        try:
            st.session_state["summary_projection_preview"] = preview_projection_mapping(
                document
            )
        except ValueError as exc:
            st.error(str(exc))
    preview = st.session_state.get("summary_projection_preview", [])
    if preview:
        st.dataframe(preview, hide_index=True, width="stretch")
    narration = "\n\n".join(str(row["text"]) for row in document["narration"]) + "\n"
    st.download_button(
        "Tải summary_narration.txt",
        narration.encode("utf-8"),
        file_name="summary_narration.txt",
        mime="text/plain",
    )


def _render_visual_plan(st: Any, document: Mapping[str, Any]) -> None:
    plan = st.session_state.get("summary_visual_plan")
    if not isinstance(plan, Mapping) or validate_summary_visual_plan(plan, document):
        plan = build_summary_visual_plan(document)
        st.session_state["summary_visual_plan"] = plan

    timing = estimate_summary_timing(document)
    density = visual_density(document, plan, timing["estimated_minutes"])
    columns = st.columns(3)
    columns[0].metric("Scenes", density["scene_count"])
    columns[1].metric("Giây/scene", f"{density['seconds_per_scene']:.1f}")
    target_density = density["target_density_seconds"]
    columns[2].metric("Mục tiêu", f"{target_density} giây" if target_density else "—")
    st.caption(
        "DATA_CHART phải liên kết ít nhất một numeric_fact_id; các scene khác có thể "
        "dùng số liệu khi cần."
    )
    edited = st.data_editor(
        plan["scenes"],
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        key="summary_visual_scene_editor",
    )
    if st.button("Áp dụng Scene plan", type="primary"):
        candidate = dict(plan)
        candidate["scenes"] = _records(edited)
        errors = validate_summary_visual_plan(candidate, document)
        if errors:
            st.error(f"Scene plan chưa hợp lệ · {len(errors)} lỗi")
            for error in errors:
                st.write(f"- {error}")
        else:
            st.session_state["summary_visual_plan"] = candidate
            st.session_state["summary_invalidated_artifacts"] = affected_artifacts(
                ["scene"]
            )
            st.session_state.pop("summary_projection_files", None)
            st.session_state.pop("summary_package_bytes", None)
            st.success(
                "Đã áp dụng Scene plan; projection và package cũ đã bị vô hiệu hóa."
            )
            st.rerun()
    st.download_button(
        "Tải summary_visual_plan.json",
        canonical_json_bytes(plan),
        file_name="summary_visual_plan.json",
        mime="application/json",
    )


def _render_exports(st: Any, document: Mapping[str, Any]) -> None:
    citation_style = st.selectbox(
        "Kiểu citation",
        ("MARKDOWN", "APA", "MLA", "CHICAGO", "BIBTEX"),
        index=0,
        key="summary_citation_style",
    )
    citations = export_citations(document, citation_style)
    st.code(citations or "Không có nguồn để xuất citation.", language=None)
    st.download_button(
        "Tải citation",
        citations.encode("utf-8"),
        file_name="summary_citations.bib"
        if citation_style == "BIBTEX"
        else "summary_citations.md",
        mime="text/plain",
    )

    targets = st.multiselect(
        "Projection targets",
        PROJECTION_TARGETS,
        default=list(PROJECTION_TARGETS),
        key="summary_projection_targets",
    )
    if st.button("Tạo projection", type="primary", disabled=not targets):
        try:
            st.session_state["summary_projection_files"] = project_summary_artifacts(
                document, targets, st.session_state.get("summary_visual_plan")
            )
        except ValueError as exc:
            st.error(str(exc))
    projected = st.session_state.get("summary_projection_files", {})
    if projected:
        st.success(f"Đã tạo {len(projected)} artifact và chạy validator đích.")
        for name, raw in projected.items():
            st.download_button(
                f"Tải {name}",
                raw,
                file_name=name,
                mime="application/json",
                key=f"summary_download_{name}",
            )

    st.markdown("#### Ảnh render và kiểm định")
    landscape_uploads = st.file_uploader(
        "Ảnh landscape bắt buộc",
        type=["png"],
        accept_multiple_files=True,
        key="summary_landscape_uploads",
    )
    portrait_uploads = st.file_uploader(
        "Ảnh portrait tùy chọn",
        type=["png"],
        accept_multiple_files=True,
        key="summary_portrait_uploads",
    )
    review_upload = st.file_uploader(
        "Media review đã duyệt", type=["json"], key="summary_media_review_upload"
    )
    media = {
        f"{orientation}/{upload.name}": upload.getvalue()
        for orientation, uploads in (
            ("landscape", landscape_uploads),
            ("portrait", portrait_uploads),
        )
        for upload in uploads
    }
    media_review = None
    if review_upload is not None:
        try:
            media_review = strict_json_bytes(review_upload.getvalue())
        except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
            st.error(f"Media review không hợp lệ: {exc}")

    if st.button("Build và audit summary_package.zip", disabled=not targets):
        try:
            st.session_state["summary_package_bytes"] = build_summary_package_bytes(
                document,
                targets,
                st.session_state.get("summary_visual_plan"),
                media=media,
                media_review=media_review,
            )
        except (OSError, ValueError) as exc:
            st.error(str(exc))
    package = st.session_state.get("summary_package_bytes")
    if isinstance(package, bytes):
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            package_status = json.loads(archive.read("summary_manifest.json"))["status"]
        if package_status == "COMPLETE":
            st.success("Package COMPLETE: đủ ảnh bắt buộc, review PASS và audit đạt.")
        else:
            st.warning(
                f"Package {package_status}: audit cấu trúc đạt nhưng media chưa hoàn tất."
            )
        st.download_button(
            "Tải summary_package.zip",
            package,
            file_name="summary_package.zip",
            mime="application/zip",
        )


def _render_package_management(st: Any) -> None:
    """Inspect and safely repair/complete the Summary package in the shared project."""
    root_text = str(st.session_state.get(PROJECT_DIRECTORY_KEY) or "").strip()
    root = Path(root_text).expanduser() if root_text else None
    if root is None or not (root / "summary_manifest.json").is_file():
        return
    with st.expander("Quản lý Summary package hiện tại", expanded=True):
        st.caption(str(root.resolve()))
        try:
            plan = plan_summary_completion(root)
            manifest_issues = summary_manifest_issues(root)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            st.error(f"Không thể phân tích Summary package: {exc}")
            return
        columns = st.columns(3)
        columns[0].metric("Stage", plan.get("stage") or "—")
        columns[1].metric("Trạng thái", plan.get("status") or "—")
        columns[2].metric("Manifest", "Cần sửa" if manifest_issues else "Đồng bộ")
        if plan["blockers"]:
            st.warning(
                f"Chưa thể hoàn tất Stage · {len(plan['blockers'])} điều kiện chưa đạt"
            )
            for blocker in plan["blockers"]:
                st.markdown(f"- {blocker}")
        elif plan["status"] == "COMPLETE":
            st.success("Stage đã COMPLETE và manifest đang đồng bộ.")
        else:
            st.success("Tất cả điều kiện đã đạt; có thể hoàn tất Stage.")
        if plan.get("render_plan_sync"):
            st.caption(
                f"Khi hoàn tất, {len(plan['render_plan_sync'])} trạng thái trong render plan "
                "sẽ được đồng bộ thành VALIDATED từ media review đã đạt."
            )

        st.markdown("##### Kiểm định lại media từ thư mục hiện tại")
        approved_upload = st.file_uploader(
            "Media review đã quan sát và phê duyệt",
            type=["json"],
            key="summary_current_media_review_upload",
            help="Review phải chứa asset_id và bảy semantic checks cho toàn bộ asset Stage 3.",
        )
        if st.button(
            "Dựng lại plan, log, validation và manifest",
            disabled=approved_upload is None,
            key="summary_revalidate_current_media",
            width="stretch",
        ):
            try:
                approved = strict_json_bytes(approved_upload.getvalue())
                backup = revalidate_summary_media(root, approved)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                st.error(f"Không thể kiểm định lại media: {exc}")
            else:
                st.session_state["summary_package_feedback"] = (
                    "success",
                    f"Đã dựng lại media evidence và validation. Bản sao lưu: {backup}",
                )
                st.rerun()

        action_columns = st.columns(3)
        if action_columns[0].button(
            "Nạp summary.json", key="summary_load_project_canonical", width="stretch"
        ):
            try:
                st.session_state[SUMMARY_EDITOR_KEY] = (
                    root / "summary.json"
                ).read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                st.error(f"Không thể nạp summary.json: {exc}")
            else:
                st.rerun()
        if action_columns[1].button(
            "Sửa Summary manifest",
            disabled=not manifest_issues,
            key="summary_repair_project_manifest",
            width="stretch",
        ):
            try:
                backup = repair_summary_manifest(root)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                st.error(f"Không thể sửa Summary manifest: {exc}")
            else:
                st.session_state["summary_package_feedback"] = (
                    "success",
                    f"Đã đồng bộ manifest. Bản sao lưu: {backup}",
                )
                st.rerun()
        if action_columns[2].button(
            "Xác minh và hoàn tất Stage",
            type="primary",
            disabled=not plan["can_complete"],
            key="summary_complete_project_stage",
            width="stretch",
        ):
            try:
                backup = complete_summary_stage(root)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                st.error(f"Không thể hoàn tất Stage: {exc}")
            else:
                st.session_state["summary_package_feedback"] = (
                    "success",
                    f"Stage đã COMPLETE. Bản sao lưu: {backup}",
                )
                st.rerun()


def _render_source_step(st: Any, capabilities: Any) -> None:
    """Collect source documents without exposing extraction/runtime details up front."""
    st.subheader("Tài liệu nguồn")
    st.caption("Thêm tài liệu cần tóm tắt hoặc nạp một summary.json đã có.")
    source_types = ["txt", "md", "docx", "pdf", "srt", "vtt", "json"]
    if capabilities.image_ocr:
        source_types.extend(["png", "jpg", "jpeg", "tif", "tiff"])
    source_uploads = st.file_uploader(
        "Kéo thả tài liệu nguồn",
        type=source_types,
        accept_multiple_files=True,
        key="summary_source_uploads",
    )
    needs_ocr = any(
        Path(source.name).suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
        for source in source_uploads
    )
    with st.expander("Tùy chọn trích xuất", expanded=needs_ocr):
        if needs_ocr and not capabilities.image_ocr:
            st.warning("Cần cài Tesseract để đọc nguồn ảnh.")
        ocr_language = st.text_input(
            "Ngôn ngữ OCR",
            value="vie+eng" if capabilities.image_ocr else "",
            disabled=not capabilities.image_ocr,
            key="summary_ocr_language",
        )
        st.caption(
            "PDF text: "
            + ("Sẵn sàng" if capabilities.pdf_text else "Thiếu pypdf")
            + " · OCR ảnh: "
            + ("Sẵn sàng" if capabilities.image_ocr else "Thiếu Tesseract")
        )
    if st.button("Trích xuất tài liệu", type="primary", disabled=not source_uploads):
        extracted, diagnostics = [], []
        for source in source_uploads:
            try:
                item = extract_source(
                    source.name,
                    source.getvalue(),
                    source.type,
                    ocr_language=ocr_language.strip() or None,
                )
            except (OSError, UnicodeError, ValueError, zipfile.BadZipFile) as exc:
                diagnostics.append(
                    {"Tệp": source.name, "Trạng thái": "Cần sửa", "Chi tiết": str(exc)}
                )
            else:
                extracted.append(item)
                diagnostics.append(
                    {
                        "Tệp": source.name,
                        "Trạng thái": "Sẵn sàng",
                        "Chi tiết": f"{len(item.blocks)} khối · {item.extraction_method}",
                    }
                )
        st.session_state["summary_extracted_sources"] = extracted
        st.session_state["summary_extraction_diagnostics"] = diagnostics
        st.session_state["summary_step"] = "Trích xuất"
        st.rerun()

    st.divider()
    uploaded = st.file_uploader(
        "Hoặc nạp summary.json", type=["json"], key="summary_studio_upload"
    )
    if uploaded is not None:
        raw = uploaded.getvalue()
        digest = hashlib.sha256(raw).hexdigest()
        if st.session_state.get("summary_upload_sha256") != digest:
            st.session_state[SUMMARY_EDITOR_KEY] = raw.decode(
                "utf-8-sig", errors="replace"
            )
            st.session_state["summary_upload_sha256"] = digest
            st.session_state.pop("summary_projection_files", None)
            st.session_state.pop("summary_package_bytes", None)
            st.session_state.pop("summary_visual_plan", None)
            st.session_state["summary_step"] = "Nội dung"
            st.rerun()


def _render_extraction_step(st: Any) -> None:
    """Review extraction diagnostics before creating the canonical draft."""
    st.subheader("Kiểm tra kết quả trích xuất")
    diagnostics = st.session_state.get("summary_extraction_diagnostics", [])
    extracted = st.session_state.get("summary_extracted_sources", [])
    if not diagnostics:
        render_empty_state(
            "Chưa trích xuất tài liệu",
            "Quay lại bước Nguồn và thêm ít nhất một tài liệu.",
            icon="↥",
        )
        return
    st.dataframe(diagnostics, hide_index=True, width="stretch")
    total_blocks = sum(len(item.blocks) for item in extracted)
    st.caption(f"{len(extracted)} nguồn sẵn sàng · {total_blocks} khối nội dung")
    if st.button("Tạo bản tóm tắt", type="primary", disabled=not extracted):
        try:
            draft = build_summary_draft(extracted)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state[SUMMARY_EDITOR_KEY] = canonical_json_bytes(draft).decode(
                "utf-8"
            )
            st.session_state.pop("summary_projection_files", None)
            st.session_state.pop("summary_package_bytes", None)
            st.session_state.pop("summary_visual_plan", None)
            st.session_state["summary_step"] = "Nội dung"
            st.rerun()


def _render_advanced_json(st: Any, document: Mapping[str, Any]) -> None:
    with st.expander("Công cụ nâng cao · Canonical JSON", expanded=False):
        st.text_area("Canonical JSON", key=SUMMARY_EDITOR_KEY, height=320)
        st.json(document, expanded=False)
        st.download_button(
            "Tải summary.json",
            canonical_json_bytes(document),
            file_name="summary.json",
            mime="application/json",
        )


def render_summary_studio_workspace(*, embedded: bool = False) -> None:
    import streamlit as st

    apply_pending_summary_editor_update(st.session_state)
    if not embedded:
        st.set_page_config(
            page_title="Summary Studio", page_icon=":material/summarize:", layout="wide"
        )
    render_workspace_header(
        "Tóm tắt",
        "Chuyển tài liệu nguồn thành bản tóm tắt có dẫn chứng và sẵn sàng xuất bản.",
        eyebrow="Tài liệu → nội dung → package",
    )
    capabilities = detect_summary_capabilities()
    if feedback := st.session_state.pop("summary_package_feedback", None):
        (st.success if feedback[0] == "success" else st.error)(feedback[1])
    if st.session_state.get("summary_step") not in SUMMARY_STEPS:
        st.session_state["summary_step"] = (
            "Nội dung" if st.session_state.get(SUMMARY_EDITOR_KEY) else "Nguồn"
        )
    step = (
        st.segmented_control(
            "Quy trình tóm tắt",
            SUMMARY_STEPS,
            key="summary_step",
            width="stretch",
        )
        or "Nguồn"
    )

    if step == "Nguồn":
        _render_source_step(st, capabilities)
        return
    if step == "Trích xuất":
        _render_extraction_step(st)
        return

    text = str(st.session_state.get(SUMMARY_EDITOR_KEY) or "")
    if not text.strip():
        render_empty_state(
            "Chưa có bản tóm tắt",
            "Hoàn tất bước Nguồn và Trích xuất trước khi biên tập nội dung.",
            icon="Σ",
        )
        return
    document, errors = parse_summary_text(text)
    if document is None:
        st.error(errors[0])
        return
    if errors and document.get("schema_version") == "1.0.0":
        if st.button("Migrate bản 1.0 sang 1.1"):
            try:
                migrated = migrate_summary_document(document)
            except ValueError as exc:
                st.error(str(exc))
            else:
                queue_summary_editor_update(
                    st.session_state, canonical_json_bytes(migrated).decode("utf-8")
                )
                st.rerun()
    if errors and document.get("schema_version") == "1.1.0":
        with st.expander("Chuẩn hóa Summary 1.1 hiện tại", expanded=True):
            st.caption(
                "Đổi ID legacy sang quy ước runtime và cập nhật toàn bộ tham chiếu trên "
                "một bản sao. Canonical hiện tại chỉ được thay trong trình sửa khi hậu kiểm đạt."
            )
            citation_style = st.selectbox(
                "Citation style thay thế khi giá trị hiện tại không hợp lệ",
                ("MARKDOWN", "APA", "MLA", "CHICAGO", "BIBTEX"),
                key="summary_normalization_citation_style",
            )
            if st.button(
                "Chuẩn hóa và hậu kiểm", type="primary", key="summary_normalize_v110"
            ):
                try:
                    migrated = normalize_summary_v110_ids(
                        document, citation_style=citation_style
                    )
                except (TypeError, ValueError) as exc:
                    st.error(str(exc))
                else:
                    queue_summary_editor_update(
                        st.session_state, canonical_json_bytes(migrated).decode("utf-8")
                    )
                    st.session_state["summary_invalidated_artifacts"] = (
                        affected_artifacts(
                            ["source", "locator", "section", "claim", "narration"]
                        )
                    )
                    st.session_state.pop("summary_projection_files", None)
                    st.session_state.pop("summary_package_bytes", None)
                    st.session_state.pop("summary_projection_preview", None)
                    st.session_state.pop("summary_visual_plan", None)
                    st.session_state["summary_normalization_feedback"] = (
                        "Đã chuẩn hóa ID và liên kết; projection/package cũ đã bị vô hiệu hóa."
                    )
                    st.rerun()
    if feedback := st.session_state.pop("summary_normalization_feedback", None):
        st.success(feedback)
    if errors:
        st.error(f"Summary chưa hợp lệ · {len(errors)} lỗi")
        for error in errors:
            st.write(f"- {error}")
        with st.expander("Sửa Canonical JSON", expanded=True):
            st.text_area("Canonical JSON", key=SUMMARY_EDITOR_KEY, height=320)
        return
    st.success("Nội dung hợp lệ và sẵn sàng cho bước hiện tại.")
    if step == "Nội dung":
        overview_tab, claims_tab = st.tabs(["Bản tóm tắt", "Claims & dữ liệu"])
        with overview_tab:
            _render_overview(st, document)
        with claims_tab:
            _render_claims(st, document)
    elif step == "Lời đọc & cảnh":
        narration_tab, scene_tab = st.tabs(["Lời đọc", "Kế hoạch cảnh"])
        with narration_tab:
            _render_narration(st, document)
        with scene_tab:
            _render_visual_plan(st, document)
    else:
        _render_package_management(st)
        _render_exports(st, document)
    _render_advanced_json(st, document)


__all__ = [
    "apply_pending_summary_editor_update",
    "parse_summary_text",
    "queue_summary_editor_update",
    "render_summary_studio_workspace",
    "summary_metrics",
]
