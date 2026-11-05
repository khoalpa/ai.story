"""Friendly Streamlit viewer for the current validation_report.json."""
from __future__ import annotations

from collections import Counter
from html import escape
from pathlib import Path
from typing import Any, BinaryIO, Mapping

from studio.package_migration import (
    publish_rebuilt_checkpoint_chain,
    rebuild_v520_checkpoint_chain,
)
from studio.package_quality_report import _items, _object, _read_report, _short_digest
from studio.report_semantics import display_score, gate_is_not_applicable, gate_summary
from studio.workflow_builder import (
    rerun_deterministic_gates_atomic,
    restore_integrity_backup,
    review_model_gate_atomic,
    scaffold_missing_stage_gates_atomic,
)
from studio.workflow_package import read_archive, stage_gate_contract_diagnostics

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
    required = {"schema_version", "prompt_version", "stage", "status", "input_sources",
                "checks", "limitations", "remaining_work", "archive_validation"}
    expected = {"4.1.6": "4.1.3", "4.2.0": "4.1.3", "5.0.0": "5.0.0", "5.1.0": "5.0.0", "5.2.0": "5.0.0", "5.2.2": "5.0.0"}.get(str(report.get("prompt_version")))
    if expected is None or report.get("schema_version") != expected:
        raise ValueError("Chỉ hỗ trợ validation_report.json của prompt v5 hoặc v4 legacy.")
    missing = sorted(required.difference(report))
    extra = sorted(set(report).difference(required))
    if missing or extra:
        details = []
        if missing:
            details.append("thiếu: " + ", ".join(missing))
        if extra:
            details.append("field ngoài schema: " + ", ".join(extra))
        raise ValueError("Tệp không đúng closed schema validation_report.json v4; " + "; ".join(details))


def _all_gates_pass(report: Mapping[str, Any]) -> bool:
    return bool(gate_summary(report)["ready"])


def _status_text(value: Any) -> str:
    return {
        "PASS": "Đạt",
        "FAIL": "Không đạt",
        "NOT_APPLICABLE": "Không áp dụng",
        "NOT_VERIFIED": "Chưa xác minh",
        "ASSESSED_PASS": "Đánh giá đạt",
        "REFINEMENT_ACCEPTED": "Đã chấp nhận",
    }.get(str(value), str(value or "Không rõ").replace("_", " ").title())


def effective_validation_status(report: Mapping[str, Any], package_inspection: Mapping[str, Any] | None) -> str:
    """Prefer the local package verdict over the report's self-declared status."""
    if package_inspection is None:
        return str(report.get("status") or "UNKNOWN")
    overall = str(package_inspection.get("overall_status") or "NOT_VERIFIED")
    publish = str(package_inspection.get("publish_status") or "NOT_VERIFIED")
    if overall == "PASS" and publish == "PASS":
        return str(report.get("status") or "UNKNOWN")
    if overall == "FAIL":
        return "FAIL"
    if overall == "PARTIAL":
        return "PARTIAL"
    return "NOT_VERIFIED"


def _render_header(report: Mapping[str, Any]) -> None:
    import streamlit as st

    summary = _object(report.get("summary"))
    profile = escape(str(report.get("active_profile") or "—"))
    ready = _all_gates_pass(report) and int(summary.get("material_defect_remaining_count") or 0) == 0
    status_class = "sv-pass" if ready else "sv-fail"
    status_text = "Đạt theo báo cáo" if ready else "Cần xem lại trước sản xuất"
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
    result = gate_summary(report)
    passed = result["passed"]

    cols = st.columns(6)
    cols[0].metric("Chất lượng", display_score(quality.get("final_story_quality_score")))
    cols[1].metric("Cuốn hút", display_score(engagement.get("engagement_score")))
    cols[2].metric("Cổng đạt", f"{passed}/{len(gates) - result['skipped']}")
    cols[3].metric("Lỗi còn lại", int(summary.get("material_defect_remaining_count") or 0))
    cols[4].metric("Cảnh", int(summary.get("narrative_scene_count") or 0))
    cols[5].metric("Hội thoại", f"{float(dialogue.get('actual_direct_dialogue_ratio') or 0):.1%}")

    if _all_gates_pass(report):
        st.success(result["label"])
    else:
        st.error(f"Có {len(result['unresolved'])} cổng chưa đạt hoặc chưa xác minh.")

    st.subheader("Điểm theo tiêu chí")
    dimensions = _object(quality.get("dimension_scores"))
    labels = {
        "story_intent": "Ý đồ truyện", "causal_progression": "Tiến triển nhân quả",
        "character_agency": "Chủ động nhân vật", "dialogue_realization": "Thể hiện hội thoại",
        "climax_cost": "Cái giá cao trào", "consequence_persistence": "Hệ quả kéo dài",
        "audio_readability": "Khả năng đọc audio", "profile_fidelity": "Đúng hồ sơ",
    } if dimensions else QUALITY_LABELS
    values = dimensions or quality
    for key in dict.fromkeys([*labels, *dimensions]):
        value = values.get(key)
        label_col, score_col = st.columns([5, 1])
        label_col.write(labels.get(key, key))
        score_col.write("Chưa có dữ liệu" if value is None else f"{value}/2")
        if isinstance(value, (int, float)) and 0 <= value <= 2:
            st.progress(value / 2.0)
    st.caption("Điểm do báo cáo khai báo; giá trị trên 10 được quy đổi từ thang 100. Chưa chấm lại độc lập.")

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
    st.caption("Bản đồ vùng/cảnh theo báo cáo; số bản ghi không phải số ảnh sản xuất hoặc số cảnh tự tính lại.")
    st.dataframe(rows, hide_index=True, width="stretch")

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

    st.caption("Các kết quả dưới đây do báo cáo khai báo. ASSESSED_PASS/FAIL là đánh giá của mô hình; không phải xác minh độc lập. Thiếu detector/evidence không được suy thành PASS.")

    gates = _items(report.get("gates"))
    if not gates:
        st.info("Báo cáo không chứa cổng kiểm định.")
        return
    severity_counts = Counter(str(gate.get("severity") or "UNKNOWN") for gate in gates)
    cols = st.columns(max(1, len(severity_counts)))
    for col, (severity, count) in zip(cols, sorted(severity_counts.items())):
        passed = sum(gate.get("status") == "PASS" and gate.get("severity") == severity for gate in gates)
        skipped = sum(gate_is_not_applicable(gate, report) and gate.get("severity") == severity for gate in gates)
        col.metric(SEVERITY_LABELS.get(severity, severity.replace("_", " ").title()), f"{passed}/{count - skipped}")
        if skipped:
            col.caption(f"{skipped} không áp dụng")

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
            "Detector (khai báo)": gate.get("detector_class", gate.get("detector_method", "Chưa cung cấp")),
            "Evidence ID": gate.get("evidence_id", "—"),
            "Vị trí bằng chứng": len(gate.get("evidence_locators", gate.get("locators", []))),
        } for gate in visible],
        hide_index=True,
        width="stretch",
    )

    for index, gate in enumerate(visible):
        with st.expander(str(gate.get("gate_id") or "Cổng kiểm định")):
            st.write(str(gate.get("failure_reason") or _object(gate.get("metrics")).get("applicability_reason") or _status_text(gate.get("status"))))
            for locator_index, locator in enumerate(gate.get("evidence_locators", gate.get("locators", []))):
                st.code(str(locator), language=None)
                import re
                match = re.fullmatch(r"script:(\d+)(?:-(\d+))?", str(locator))
                if match:
                    def open_evidence(start: int, end: int) -> None:
                        st.session_state["story_evidence_range"] = (start, end)
                        st.session_state["story_studio_section"] = "Nội dung"
                    st.button("Mở đoạn kịch bản", key=f"gate_evidence_{index}_{locator_index}",
                              on_click=open_evidence, args=(int(match[1]), int(match[2] or match[1])))


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
    st.dataframe(rows, hide_index=True, width="stretch")
    with st.expander("Xem JSON gốc"):
        st.json(report, expanded=False)


def _render_manual_gate_review(report: Mapping[str, Any], root: Path) -> None:
    import streamlit as st

    reviewable = [
        row for row in _items(report.get("checks"))
        if row.get("method") == "MODEL_REVIEW" and row.get("status") not in {"PASS", "NOT_APPLICABLE"}
    ]
    backup_key = f"manual_gate_review_backup_{root.resolve()}"
    if backup_value := st.session_state.get(backup_key):
        st.success("Lần kiểm định thủ công gần nhất đã được lưu và hậu kiểm toàn vẹn.")
        if st.button("Hoàn tác lần kiểm định gần nhất", key=f"manual_gate_undo_{root.resolve()}"):
            try:
                restore_integrity_backup(root, Path(str(backup_value)))
            except (OSError, ValueError) as exc:
                st.error(f"Hoàn tác thất bại: {exc}")
            else:
                st.session_state.pop(backup_key, None)
                st.rerun()
    if not reviewable:
        st.info("Không còn gate MODEL_REVIEW đang chờ hoặc không đạt.")
        return
    st.subheader("Kiểm định thủ công")
    st.caption("Duyệt từng gate; không áp dụng cho detector CODE. Bằng chứng được ghi vào validation_report.json và checkpoint được tạo lại.")
    identifiers = [str(row.get("id")) for row in reviewable]
    with st.form(f"manual_gate_review_{root.resolve()}"):
        selected = st.selectbox("Gate cần duyệt", identifiers)
        current = next(row for row in reviewable if str(row.get("id")) == selected)
        st.write(f"**Đối tượng:** {current.get('target', '—')}")
        st.caption(str(current.get("details") or "Chưa có mô tả."))
        decision = st.radio("Kết quả", ["PASS", "FAIL"], horizontal=True,
                            format_func=lambda value: "Đạt" if value == "PASS" else "Không đạt")
        reviewer = st.text_input("Người kiểm định", placeholder="Tên hoặc định danh người duyệt")
        evidence = st.text_area(
            "Bằng chứng và nhận xét",
            placeholder="Nêu tài sản đã xem, tiêu chí đối chiếu và kết luận cụ thể…",
            help="Bắt buộc; tối thiểu 12 ký tự. Không dùng ghi chú chung chung như ‘đã xem’.",
        )
        confirmed = st.checkbox("Tôi đã trực tiếp xem/đánh giá đối tượng nêu trên.")
        # Widgets inside st.form do not trigger a rerun until submission. Tying
        # `disabled` to this checkbox therefore leaves the button stuck in its
        # initial disabled state even after the user checks the box.
        submitted = st.form_submit_button("Lưu kết quả kiểm định", type="primary")
    if submitted:
        if not confirmed:
            st.error("Cần xác nhận đã trực tiếp xem/đánh giá đối tượng trước khi lưu.")
            return
        try:
            _inspection, backup = review_model_gate_atomic(
                root, selected, decision, evidence, reviewer=reviewer,
            )
        except (OSError, KeyError, TypeError, ValueError) as exc:
            st.error(f"Không thể lưu kiểm định: {exc}")
        else:
            st.session_state[backup_key] = str(backup)
            st.success(f"Đã lưu {selected}={decision}, cập nhật manifest/checkpoint và hậu kiểm thành công.")
            st.rerun()


def _render_deterministic_gate_rerun(report: Mapping[str, Any], root: Path) -> None:
    import streamlit as st

    pending = [
        row for row in _items(report.get("checks"))
        if row.get("method") == "CODE" and row.get("status") == "NOT_CHECKED"
    ]
    if not pending:
        return
    backup_key = f"deterministic_gate_backup_{root.resolve()}"
    if backup_value := st.session_state.get(backup_key):
        st.success("Lần hậu kiểm tự động gần nhất đã được lưu và tạo lại checkpoint.")
        if st.button("Hoàn tác hậu kiểm tự động", key=f"deterministic_gate_undo_{root.resolve()}"):
            try:
                restore_integrity_backup(root, Path(str(backup_value)))
            except (OSError, ValueError) as exc:
                st.error(f"Hoàn tác thất bại: {exc}")
            else:
                st.session_state.pop(backup_key, None)
                st.rerun()
    st.subheader("Hậu kiểm tự động sau migration")
    st.caption(
        f"Có {len(pending)} gate CODE đang chờ. Ứng dụng chỉ cập nhật gate có bằng chứng "
        "deterministic; MODEL_REVIEW và TOOL không được tự động nâng thành PASS."
    )
    parent_upload = st.file_uploader(
        "Gói cha trực tiếp (tùy chọn, cần cho INHERITED_BYTES)", type=["zip"],
        key=f"deterministic_gate_parent_{root.resolve()}",
    )
    if st.button("Chạy hậu kiểm tự động", type="primary", key=f"deterministic_gate_run_{root.resolve()}"):
        try:
            parent = read_archive(parent_upload.getvalue()) if parent_upload is not None else None
            _inspection, backup, updated = rerun_deterministic_gates_atomic(root, parent=parent)
        except (OSError, KeyError, TypeError, ValueError) as exc:
            st.error(f"Hậu kiểm tự động thất bại: {exc}")
        else:
            st.session_state[backup_key] = str(backup)
            st.success("Đã xác minh: " + ", ".join(updated))
            st.rerun()


def _render_gate_contract_repair(report: Mapping[str, Any], root: Path) -> None:
    import streamlit as st

    if str(report.get("prompt_version")) not in {"5.2.0", "5.2.2"}:
        return
    diagnostics = stage_gate_contract_diagnostics(report)
    missing = diagnostics["missing"]
    if not missing:
        return
    aliases = {
        "PORTRAIT_FILES": "IMAGE_FILES",
        "PORTRAIT_CONTENT": "IMAGE_CONTENT",
        "PAIRWISE_PARITY": "ORIENTATION_PARITY",
        "STAGE2_SOURCE": "INHERITED_BYTES (chỉ là gợi ý nguồn)",
    }
    st.subheader("Sửa báo cáo theo hợp đồng")
    st.warning(
        f"Thiếu {len(missing)} gate bắt buộc: " + ", ".join(missing) + ". "
        "Các kết quả PASS có tên cũ không được tự động dùng làm bằng chứng mới."
    )
    suggestions = [
        {"Gate hiện có": old, "Gate hợp đồng gợi ý": new, "Cách xử lý": "Tạo gate chờ và kiểm lại"}
        for old, new in aliases.items() if old in diagnostics["declared"]
    ]
    if suggestions:
        st.dataframe(suggestions, hide_index=True, width="stretch")
    backup_key = f"gate_contract_repair_backup_{root.resolve()}"
    if backup_value := st.session_state.get(backup_key):
        st.success("Lần chuẩn hóa gần nhất đã được lưu cùng bản sao lưu.")
        if st.button("Hoàn tác chuẩn hóa gate", key=f"gate_contract_repair_undo_{root.resolve()}"):
            try:
                restore_integrity_backup(root, Path(str(backup_value)))
            except (OSError, ValueError) as exc:
                st.error(f"Hoàn tác thất bại: {exc}")
            else:
                st.session_state.pop(backup_key, None)
                st.rerun()
    if st.button("Chuẩn hóa báo cáo Stage", type="primary", key=f"gate_contract_repair_{root.resolve()}"):
        try:
            _inspection, backup, added = scaffold_missing_stage_gates_atomic(root)
        except (OSError, KeyError, TypeError, ValueError) as exc:
            st.error(f"Không thể chuẩn hóa báo cáo: {exc}")
        else:
            st.session_state[backup_key] = str(backup)
            st.success("Đã thêm gate ở trạng thái chờ kiểm: " + ", ".join(added))
            st.rerun()


def _render_lineage_rebuild(report: Mapping[str, Any], root: Path) -> None:
    import streamlit as st

    pending = {
        str(row.get("id")) for row in _items(report.get("checks"))
        if row.get("status") in {"NOT_CHECKED", "NOT_VERIFIED"}
    }
    if pending != {"INHERITED_BYTES"} or report.get("stage") != 3:
        return
    key_prefix = f"lineage_rebuild_{root.resolve()}"
    result_key = f"{key_prefix}_result"
    st.subheader("Tái tạo chuỗi checkpoint sau migration")
    st.warning(
        "image_prompts.json đã thay đổi canonical bytes. Cần dựng lại Stage 1 → Stage 2 → "
        "Stage 3 để tạo bằng chứng kế thừa mới; chuỗi hiện tại sẽ không bị ghi đè."
    )
    if st.button("Phân tích và dựng chuỗi mới", type="primary", key=f"{key_prefix}_build"):
        try:
            st.session_state[result_key] = rebuild_v520_checkpoint_chain(root)
        except (OSError, KeyError, TypeError, ValueError) as exc:
            st.session_state.pop(result_key, None)
            st.error(f"Không thể dựng lại lineage: {exc}")
    result = st.session_state.get(result_key)
    if result is None:
        return
    with st.expander("Xem trước chuỗi checkpoint", expanded=True):
        st.dataframe([
            {
                "Checkpoint": name,
                "Kích thước": len(raw),
                "INHERITED_BYTES": "—" if stage == 1 else "PASS",
            }
            for stage, (name, raw) in enumerate(result.archives.items(), 1)
        ], hide_index=True, width="stretch")
        st.caption("Các gate chưa có bằng chứng độc lập vẫn giữ NOT_CHECKED; không kế thừa PASS giả.")
    st.markdown("#### Chọn cách xuất")
    save_column, download_column = st.columns(2, gap="large")
    with save_column:
        with st.container(border=True):
            st.markdown("##### Lưu thành thư mục mới")
            st.caption(
                "Lưu đủ ba checkpoint và báo cáo để tiếp tục làm việc trong Studio."
            )
            default_destination = root.parent / f"{root.name}_lineage_rebuilt"
            destination = Path(st.text_input(
                "Thư mục đích", value=str(default_destination),
                key=f"{key_prefix}_destination",
                help="Chỉ ghi vào thư mục mới hoặc thư mục đang trống.",
            )).expanduser()
            if st.button(
                "Lưu chuỗi checkpoint", type="primary", key=f"{key_prefix}_publish",
                use_container_width=True,
            ):
                try:
                    written = publish_rebuilt_checkpoint_chain(result, destination)
                except (OSError, ValueError) as exc:
                    st.error(f"Không thể lưu chuỗi checkpoint: {exc}")
                else:
                    st.success(f"Đã lưu ba checkpoint và báo cáo tại {written}")
    with download_column:
        with st.container(border=True):
            st.markdown("##### Tải file ZIP")
            st.caption("Tải riêng một checkpoint để gửi hoặc lưu trữ; không ghi file vào thư mục dự án.")
            archive_name = st.selectbox(
                "Checkpoint", tuple(result.archives), index=len(result.archives) - 1,
                key=f"{key_prefix}_download_name",
            )
            st.download_button(
                f"Tải {archive_name}", data=result.archives[archive_name],
                file_name=archive_name, mime="application/zip",
                key=f"{key_prefix}_download", use_container_width=True,
            )


def render_story_validation_report(
    report: Mapping[str, Any], *, include_technical: bool = True, root: Path | None = None,
    package_inspection: Mapping[str, Any] | None = None,
) -> None:
    import streamlit as st

    _validate_story_report(report)
    if report.get("prompt_version") in {"4.1.6", "4.2.0", "5.0.0", "5.1.0", "5.2.0", "5.2.2"}:
        checks = _items(report.get("checks"))
        passed = sum(row.get("status") in {"PASS", "NOT_APPLICABLE"} for row in checks)
        failed = sum(row.get("status") == "FAIL" for row in checks)
        unchecked = sum(row.get("status") in {"NOT_CHECKED", "NOT_VERIFIED"} for row in checks)
        remaining_count = len(_items(report.get("remaining_work"))) + unchecked
        effective_status = effective_validation_status(report, package_inspection)
        contract_diagnostics = (
            stage_gate_contract_diagnostics(report)
            if str(report.get("prompt_version")) in {"5.2.0", "5.2.2"}
            else None
        )
        columns = st.columns(7 if contract_diagnostics else 6)
        columns[0].metric("Trạng thái", effective_status)
        columns[1].metric("Stage", report.get("stage", "—"))
        columns[2].metric(
            "Khai báo đạt" if contract_diagnostics else "Kiểm tra đạt",
            f"{passed}/{len(checks)}",
        )
        columns[3].metric("Không đạt", failed)
        columns[4].metric("Chưa kiểm tra", unchecked)
        columns[5].metric("Việc còn lại", remaining_count)
        if contract_diagnostics:
            columns[6].metric(
                "Gate hợp đồng",
                f"{len(contract_diagnostics['resolved_required'])}/{len(contract_diagnostics['required'])}",
            )
        package_ready = package_inspection is None or (
            package_inspection.get("overall_status") == "PASS"
            and package_inspection.get("publish_status") == "PASS"
        )
        if report.get("status") == "COMPLETE" and not failed and package_ready:
            st.success("Báo cáo hoàn tất; mọi phép kiểm bắt buộc đã đạt hoặc không áp dụng.")
        else:
            st.error("Báo cáo hoặc hậu kiểm package chưa đạt; chưa thể coi Stage là hoàn tất.")
        if package_inspection is not None and not package_ready:
            st.warning(
                "validation_report.json tự khai "
                f"{report.get('status', 'UNKNOWN')}, nhưng hậu kiểm package kết luận "
                f"{package_inspection.get('overall_status', 'NOT_VERIFIED')}."
            )
            package_failures = [
                row for row in _items(package_inspection.get("checks"))
                if row.get("status") not in {"PASS", "WARN"}
            ]
            if package_failures:
                st.dataframe([{
                    "Hậu kiểm": row.get("check", "—"),
                    "Kết quả": _status_text(row.get("status")),
                    "Chi tiết": row.get("detail", "—"),
                } for row in package_failures], hide_index=True, width="stretch")
        st.subheader("Các phép kiểm tra")
        st.dataframe([{
            "ID": row.get("id", "—"), "Kết quả": _status_text(row.get("status")),
            "Phương pháp": row.get("method", "—"), "Bắt buộc": row.get("required", "—"),
            "Đối tượng": row.get("target", "—"), "Chi tiết": row.get("details", "—"),
        } for row in checks], hide_index=True, width="stretch")
        if root is not None and (root / "manifest.json").is_file():
            _render_lineage_rebuild(report, root)
            _render_gate_contract_repair(report, root)
            _render_deterministic_gate_rerun(report, root)
            _render_manual_gate_review(report, root)
        limitations = _items(report.get("limitations"))
        if limitations:
            with st.expander(f"Giới hạn đã ghi nhận ({len(limitations)})"):
                for item in limitations:
                    st.write(f"- {item}")
        remaining = _items(report.get("remaining_work"))
        if remaining:
            with st.expander(f"Việc còn lại ({len(remaining)})", expanded=True):
                for item in remaining:
                    st.write(f"- {item}")
        if include_technical:
            with st.expander("Nguồn và JSON kỹ thuật"):
                st.write("\n".join(str(item) for item in _items(report.get("input_sources"))))
                st.json(report, expanded=False)
        return


def render_story_validation_workspace(*, embedded: bool = False) -> None:
    import streamlit as st

    if not embedded:
        st.set_page_config(page_title="Story Validation", page_icon=":material/rule:", layout="wide")
    st.header("Story Validation")
    st.caption("Đọc validation_report.json prompt v5 hoặc v4 legacy theo hướng ưu tiên mức độ sẵn sàng và nội dung cần sửa.")
    st.html(
        """<style>
        .sv-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;padding:1.1rem 1.2rem;border:1px solid color-mix(in srgb,currentColor 14%,transparent);border-radius:.8rem;margin:.25rem 0 1rem}
        .sv-heading h2{margin:.1rem 0 .2rem;font-size:1.55rem}.sv-eyebrow{font-size:.75rem;opacity:.65;text-transform:uppercase;letter-spacing:.08em}.sv-muted{font-size:.85rem;opacity:.7}
        .sv-verdict{white-space:nowrap;padding:.45rem .7rem;border-radius:999px;font-weight:600}.sv-pass{color:#19733a;background:rgba(50,180,90,.12)}.sv-fail{color:#b42318;background:rgba(220,50,40,.12)}.sv-score{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
        @media(max-width:640px){.sv-heading{flex-direction:column}}
        </style>"""
    )
    uploaded = st.file_uploader("Chọn validation_report.json", type=["json"], key="story_validation_upload")
    path_text = st.text_input(
        "Hoặc nhập đường dẫn tệp trên máy",
        placeholder=r"D:\project\ai.story\output\validation_report.json",
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
