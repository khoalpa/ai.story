"""Streamlit views for read-only workflow packages and video prompt plans."""
from __future__ import annotations

import hashlib
import math
import zipfile
from pathlib import Path
from typing import Any, Mapping

from studio.package_quality_report import _items, _object
from studio.workflow_package import (
    STAGES,
    inspect_directory,
    inspect_members,
    read_archive,
    read_json,
    safe_name,
)

STAGE_LABELS = ("Truyện & nhân vật", "10 landscape", "10 portrait & gói audio", "Prompt video")


def render_workflow_summary(result: Mapping[str, Any]) -> None:
    import streamlit as st

    manifest = _object(result.get("manifest"))
    stage = result.get("stage")
    st.subheader("Quy trình gói truyện")
    st.caption(" · ".join(str(v) for v in (stage or "Chưa xác định stage", result.get("purpose"),
               manifest.get("active_profile"), f"Prompt {manifest.get('created_by_prompt_version', '—')}") if v))
    for column, name, label in zip(st.columns(4), STAGES, STAGE_LABELS):
        column.markdown(f"**{name} · {label}**")
        column.caption("Đang kiểm tra" if name == stage else "Chưa kiểm tra gói này")
    status = result.get("status", "NOT_VERIFIED")
    message = {"PASS": "Gói đạt các phép kiểm tra đã chạy", "FAIL": "Gói có lỗi cần xử lý",
               "NOT_VERIFIED": "Chưa đủ bằng chứng xác minh toàn bộ gói"}[status]
    (st.error if status == "FAIL" else st.success if status == "PASS" else st.warning)(message)
    st.caption(f"Toàn vẹn & parent trực tiếp: {result.get('integrity_status', 'NOT_VERIFIED')} · "
               f"Toàn bộ gate của stage: {result.get('stage_gate_status', 'NOT_VERIFIED')} · "
               f"Đủ điều kiện publish: {result.get('publish_status', 'NOT_VERIFIED')}")
    st.caption("Chuyển stage thủ công. Stage 3/4 không yêu cầu audio/video đã render. Báo cáo tự khai PASS không thay thế detector.")
    if result.get("next_stage"):
        st.caption(f"Bước kế tiếp theo manifest: {result['next_stage']} · chỉ thực hiện khi toàn bộ gate đầu vào đạt.")
    if result.get("expected_count") is not None:
        st.caption(f"File trong phạm vi gói: {result['actual_count']}/{result['expected_count']} · không đếm file audio/video sản xuất ngoài gói.")


def video_plan_model(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Compatibility presentation wrapper around the canonical validator."""
    from studio.video_prompt_validation import validate_video_prompt_plan
    return validate_video_prompt_plan(plan)


def finite_number(value: Any) -> bool:
    return type(value) in {int, float} and math.isfinite(value) and value >= 0


def video_source_checks(plan: Mapping[str, Any], *, root: Path | None = None,
                        members: Mapping[str, bytes] | None = None) -> list[dict[str, str]]:
    """Check exact source bytes and existing references, without inventing frame handles."""
    checks: list[dict[str, str]] = []

    def source_bytes(name: str) -> bytes | None:
        if not safe_name(name):
            return None
        if members is not None:
            return members.get(name)
        if root is not None:
            path = root / name
            if path.resolve().is_relative_to(root.resolve()) and path.is_file() and path.stat().st_size <= 64 * 1024 * 1024:
                return path.read_bytes()
        return None

    binding = _object(plan.get("source_binding"))
    for name, key in (("story.json", "story_sha256"), ("story_validation.json", "story_validation_sha256"),
                      ("package_quality_report.json", "package_quality_report_sha256")):
        try:
            raw = source_bytes(name)
            status = "NOT_VERIFIED" if raw is None or not binding.get(key) else "PASS" if hashlib.sha256(raw).hexdigest() == binding[key] else "FAIL"
        except OSError:
            status = "NOT_VERIFIED"
        checks.append({"Kiểm tra": name, "Trạng thái": status, "Phạm vi": "Exact source SHA-256"})
    for clip in _items(plan.get("clips")):
        refs = _object(clip.get("reference_inputs"))
        names: list[Any] = [refs.get("zone_reference_frame")]
        names.extend(refs[k] for k in ("primary_frame", "target_last_frame") if refs.get(k) is not None)
        character_images = refs.get("character_images", [])
        if isinstance(character_images, list):
            names.extend(character_images)
        else:
            names.append(None)
        for name in names:
            try:
                exists = isinstance(name, str) and name.endswith(".png") and source_bytes(name) is not None
            except OSError:
                exists = False
            checks.append({"Kiểm tra": f"{clip.get('clip_id', '—')}: {name}", "Trạng thái": "PASS" if exists else "FAIL",
                           "Phạm vi": "Ảnh tham chiếu tồn tại; chưa xác minh set digest/provenance"})
    return checks


def render_video_plan(plan: Mapping[str, Any], *, key_prefix: str = "video_plan",
                      root: Path | None = None, members: Mapping[str, bytes] | None = None) -> None:
    import streamlit as st

    if not plan:
        st.info("Chưa có video_prompts.json; artifact này chỉ bắt buộc ở Stage 4.")
        return
    from studio.video_prompt_validation import validate_video_prompt_plan
    model = validate_video_prompt_plan(plan, root=root, members=members)
    project = _object(plan.get("project"))
    target = _object(plan.get("generator_target"))
    left, middle, right = st.columns(3)
    left.metric("Clip", len(model["clips"]))
    middle.metric("Thời lượng video dự kiến", f"{model['duration']:.1f} s")
    right.metric("Phạm vi", project.get("coverage_mode", "—"))
    st.caption(f"Target: {target.get('preferred_model', '—')} · Kiểm tra cấu trúc hiển thị; chưa xác minh đầy đủ VIDEO_PROMPT_GATES.")
    if model["needs_confirmation"]:
        st.warning("FULL_STORY vượt 120 clip: trước khi tạo gói cần xác nhận rõ số clip/phạm vi. Viewer không tự chuyển chế độ hoặc coi việc mở file là xác nhận.")
    for error in model["errors"]:
        st.error(error)
    with st.expander("Trạng thái gate và điều kiện projection"):
        st.json(model.get("gate_statuses", {}))
        st.caption("Chỉ khi mọi gate độc lập PASS mới bật export; PASS tự khai trong artifact không phải bằng chứng.")
    with st.expander("Capability và source binding"):
        st.caption("Chỉ OBSERVED_SUPPORTED có evidence hợp lệ mới là capability đã xác minh; TARGET_DECLARED là khai báo target.")
        st.json({"capability_profile": target.get("capability_profile"), "source_binding": plan.get("source_binding")})
        if root is not None or members is not None:
            st.dataframe(video_source_checks(plan, root=root, members=members), hide_index=True, width="stretch")
    st.dataframe(model["rows"], hide_index=True, width="stretch")
    if model["clips"]:
        index = st.selectbox("Xem clip", range(len(model["clips"])),
                             format_func=lambda i: str(model["clips"][i].get("clip_id", i + 1)), key=f"{key_prefix}_clip")
        clip = model["clips"][index]
        st.code(str(clip.get("prompt", "")), language=None)
        st.caption("Audio prompt")
        st.code(str(clip.get("audio_prompt", "")), language=None)
        st.json({k: clip.get(k) for k in ("source_script", "reference_inputs", "generation_variants", "continuity_in", "continuity_out", "state_change_records", "avoid")}, expanded=False)
    with st.expander("Continuity toàn cục và kết luận do file khai báo"):
        st.json({"global_continuity_lock": plan.get("global_continuity_lock"), "validation": plan.get("validation")}, expanded=False)
    if not model["errors"]:
        from studio.prompt_contract import load_prompt_contract
        from studio.video_prompt_adapters import get_adapter
        from studio.video_prompt_projection import (
            build_prompt_package,
            project_video_prompts,
            prompt_text,
        )
        contract = load_prompt_contract()
        canonical_raw = members.get(contract.video_prompt_file_name) if members is not None else None
        if canonical_raw is None and root is not None:
            canonical_path = root / contract.video_prompt_file_name
            if canonical_path.is_file():
                canonical_raw = canonical_path.read_bytes()
        st.caption("Tệp canonical vẫn là nguồn chuẩn. Các export là projection một chiều, nằm ngoài story.zip và không sửa artifact nguồn.")
        projection_target = st.selectbox("Target export", ("VEO", "FLOW", "GENERIC"), key=f"{key_prefix}_projection_target")
        adapter = get_adapter(projection_target)
        warnings = adapter.capability_warnings(plan)
        pending = [name for name, status in model.get("gate_statuses", {}).items() if status != "PASS"]
        for warning in warnings:
            st.warning(warning)
        if pending:
            st.warning("Export mang cảnh báo vì các gate chưa xác minh: " + ", ".join(pending))
        with st.expander(f"Xem trước payload {projection_target.title()}"):
            st.json(adapter.project_plan(plan))
        json_name, json_payload = project_video_prompts(
            plan, projection_target, source_bytes=canonical_raw, contract=contract
        )
        text_payload = prompt_text(plan, projection_target, contract=contract)
        zip_name, zip_payload = build_prompt_package(
            plan, projection_target, source_bytes=canonical_raw, contract=contract
        )
        stem = contract.video_prompt_file_name.rsplit(".", 1)[0]
        columns = st.columns(3)
        columns[0].download_button(
            "Tải JSON tổng", json_payload, file_name=json_name, mime="application/json",
            key=f"{key_prefix}_{projection_target.lower()}_projection",
        )
        columns[1].download_button(
            "Tải prompt text", text_payload,
            file_name=f"{stem}.{projection_target.lower()}.txt", mime="text/plain",
            key=f"{key_prefix}_{projection_target.lower()}_text",
        )
        columns[2].download_button(
            "Tải gói ZIP", zip_payload, file_name=zip_name, mime="application/zip",
            key=f"{key_prefix}_{projection_target.lower()}_package",
        )
    else:
        st.error("Không thể export vì video_prompts.json chưa đạt kiểm tra cấu trúc canonical.")


def render_visual_bible(document: Mapping[str, Any]) -> None:
    import streamlit as st

    if not document:
        st.info("Visual Bible chỉ thuộc checkpoint Stage 2; không yêu cầu file này trong Stage 3/4.")
        return
    st.caption("Dữ liệu nguồn chỉ đọc. Các khóa và trạng thái bên dưới là khai báo, chưa được detector độc lập xác minh.")
    for key, value in document.items():
        with st.expander(str(key), expanded=key == "schema_version"):
            st.json(value) if isinstance(value, (dict, list)) else st.write(value)


def render_workflow_workspace(root: Path, reports: Mapping[str, Any], state: Mapping[str, Any]) -> None:
    import streamlit as st

    st.caption("ZIP được đọc trong bộ nhớ, không giải nén lên gói nguồn và không sửa file. Gói upload bên dưới chỉ là bản kiểm tra riêng.")
    source = st.radio("Nguồn kiểm tra", ["Thư mục đang mở", "story.zip trong thư mục", "Upload ZIP"], horizontal=True,
                      key=f"workflow_source_{root.resolve()}")
    members = None
    parent = None
    try:
        if source != "Thư mục đang mở":
            uploaded = st.file_uploader("Gói cần kiểm tra", type=["zip"], key=f"workflow_zip_{root.resolve()}") if source == "Upload ZIP" else None
            if source == "Upload ZIP" and uploaded is None:
                st.info("Chọn story.zip CURRENT hoặc checkpoint legacy để kiểm tra khả năng tương thích.")
                return
            members = read_archive(uploaded.getvalue() if uploaded else root / "story.zip")
            parent_upload = st.file_uploader("Gói cha trực tiếp (Stage trước hoặc cùng Stage khi REPAIR)", type=["zip"], key=f"workflow_parent_{root.resolve()}")
            if parent_upload:
                parent = read_archive(parent_upload.getvalue())
            result = inspect_members(members, archive=True, parent=parent)
        else:
            overrides = state.get("story_overrides", {}) if state.get("story_override_root") == str(root.resolve()) else {}
            result = inspect_directory(root, overridden=any(key in {"story", "validation", "quality", "anchor"} for key in overrides))
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        st.error(f"Không đọc được gói: {exc}")
        return
    render_workflow_summary(result)
    st.dataframe(result["checks"], hide_index=True, width="stretch")
    st.caption("Phạm vi kiểm tra: schema manifest, allowlist, hash/size, ownership, CRC và parent trực tiếp khi được cung cấp. Không chứng nhận an toàn/nội dung/mỹ thuật chỉ từ metadata.")
    if result["compatibility"] != "NATIVE_CURRENT":
        st.warning("MIGRATION_REQUIRED: chỉ đọc để chẩn đoán. Chưa có adapter legacy được xác minh; không tự chuyển gói sang CURRENT.")
    st.dataframe(result["files"], hide_index=True, width="stretch")
    with st.expander("Manifest nguồn"):
        st.json(result["manifest"], expanded=False)
    if members:
        names = [name for name in members if name.endswith((".json", ".png"))]
        if names:
            selected = st.selectbox("Xem artifact trong ZIP", names, key=f"workflow_member_{root.resolve()}")
            raw = members[selected]
            try:
                if selected.endswith(".png"):
                    st.image(raw, caption=selected)
                    st.caption("Xem ảnh không chứng minh COMMITTED_ASSET. Cần provenance và gate evidence hợp lệ.")
                else:
                    doc = read_json(raw)
                    if selected == "video_prompts.json":
                        render_video_plan(doc, key_prefix="archive_video_plan", members=members)
                    elif selected == "visual_bible.json":
                        render_visual_bible(doc)
                    else:
                        st.json(doc, expanded=False)
            except (ValueError, OSError, RecursionError) as exc:
                st.error(f"Artifact không hợp lệ: {exc}")
