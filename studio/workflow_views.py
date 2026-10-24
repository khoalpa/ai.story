"""Streamlit views for read-only workflow packages and video prompt plans."""
from __future__ import annotations

import hashlib
import math
import re
import zipfile
from pathlib import Path
from typing import Any, Mapping

from studio.package_quality_report import _items, _object
from studio.project_review import (
    DIRECTORY_SOURCE,
    LOCAL_ZIP_SOURCE,
    UPLOADED_ZIP_SOURCE,
    VERIFICATION_ROOT_KEY,
    VERIFICATION_SOURCE_KEY,
    VERIFICATION_SOURCE_LABELS,
    VERIFICATION_UPLOAD_BYTES_KEY,
    inspect_selected_workflow,
)
from studio.story_images import image_metadata
from studio.workflow_package import (
    STAGES,
    active_image_basenames,
    read_archive,
    read_json,
    safe_name,
)

STAGE_LABELS = ("Truyện & nhân vật", "Landscape", "Portrait & gói audio", "Prompt video")


def workflow_stage_caption(name: str, current_stage: Any, status: str) -> str:
    """Describe package progress while reserving validation status for the current stage."""
    if name != current_stage:
        if name in STAGES and current_stage in STAGES:
            if STAGES.index(name) < STAGES.index(current_stage):
                return "Đã hoàn thành · dữ liệu có trong gói hiện tại"
            return "Chưa thực hiện"
        return "Chưa xác định tiến độ"
    return {
        "PASS": "Stage hiện tại · đạt các phép kiểm tra đã chạy",
        "FAIL": "Stage hiện tại · có lỗi",
        "NOT_VERIFIED": "Stage hiện tại · chưa xác minh đầy đủ",
    }.get(status, "Stage hiện tại · chưa xác định trạng thái")


def video_plan_error_rows(errors: list[Any], clip_count: int) -> list[dict[str, Any]]:
    """Collapse repeated validator messages into one row per affected clip plus global errors."""
    by_clip: dict[int, list[str]] = {}
    global_errors: list[str] = []
    for value in errors:
        text = str(value)
        match = re.match(r"Clip (\d+):\s*(.*)", text)
        if match:
            by_clip.setdefault(int(match.group(1)), []).append(match.group(2))
        else:
            global_errors.append(text)
    rows = [
        {
            "Clip": f"clip_{index:04d}",
            "Trạng thái": "FAIL" if index in by_clip else "PASS",
            "Lỗi": " · ".join(by_clip.get(index, [])),
        }
        for index in range(1, clip_count + 1)
    ]
    rows.extend({"Clip": "Toàn kế hoạch", "Trạng thái": "FAIL", "Lỗi": text} for text in global_errors)
    return rows


def render_workflow_summary(result: Mapping[str, Any]) -> None:
    import streamlit as st

    manifest = _object(result.get("manifest"))
    stage = result.get("stage")
    st.subheader("Quy trình gói truyện")
    st.caption(" · ".join(str(v) for v in (stage or "Chưa xác định stage", result.get("purpose"),
               manifest.get("active_profile"), f"Prompt {manifest.get('created_by_prompt_version', '—')}") if v))
    status = str(result.get("status", "NOT_VERIFIED"))
    image_count = sum(
        1 for row in result.get("files", [])
        if isinstance(row, Mapping) and str(row.get("path", "")).startswith("landscape/")
    )
    labels = list(STAGE_LABELS)
    if image_count:
        labels[1] = f"{image_count} landscape"
        labels[2] = f"{image_count} portrait & gói audio"
    for column, name, label in zip(st.columns(4), STAGES, labels):
        column.markdown(f"**{name} · {label}**")
        column.caption(workflow_stage_caption(name, stage, status))
    message = {"PASS": "Gói đạt các phép kiểm tra đã chạy", "FAIL": "Gói có lỗi cần xử lý",
               "NOT_VERIFIED": "Chưa đủ bằng chứng xác minh toàn bộ gói"}[status]
    (st.error if status == "FAIL" else st.success if status == "PASS" else st.warning)(message)
    if status == "FAIL":
        failures = [str(item.get("detail")) for item in result.get("checks", [])
                    if isinstance(item, Mapping) and item.get("status") == "FAIL" and item.get("detail")]
        if failures:
            st.caption("Nguyên nhân xác định: " + failures[0])
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
        names: list[Any] = []
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
    voice_strategy = _object(plan.get("voice_strategy"))
    voiced_clips = sum(bool(_object(clip).get("voice_plan")) for clip in _items(plan.get("clips")))
    left, middle, right = st.columns(3)
    left.metric("Clip", len(model["clips"]))
    middle.metric("Thời lượng video dự kiến", f"{model['duration']:.1f} s")
    right.metric("Phạm vi", project.get("coverage_mode", "—"))
    st.caption(f"Target: {target.get('preferred_model', '—')} · Kiểm tra cấu trúc hiển thị; chưa xác minh đầy đủ VIDEO_PROMPT_GATES.")
    if voice_strategy:
        st.success(
            f"Voice native: {voiced_clips}/{len(model['clips'])} clip · "
            f"{voice_strategy.get('language', '—')} · Veo/Flow tự tạo giọng đồng bộ với video."
        )
    if model["needs_confirmation"]:
        st.warning("FULL_STORY vượt 120 clip: trước khi tạo gói cần xác nhận rõ số clip/phạm vi. Viewer không tự chuyển chế độ hoặc coi việc mở file là xác nhận.")
    if model["errors"]:
        error_rows = video_plan_error_rows(model["errors"], len(model["clips"]))
        failed_clips = sum(row["Trạng thái"] == "FAIL" and row["Clip"].startswith("clip_") for row in error_rows)
        st.error(
            f"Kế hoạch video: FAIL · {failed_clips}/{len(model['clips'])} clip có lỗi · "
            f"{len(model['errors'])} vi phạm canonical · Export bị khóa."
        )
        with st.expander("Chi tiết lỗi kế hoạch video", expanded=True):
            only_errors = st.toggle("Chỉ hiện lỗi", value=True, key=f"{key_prefix}_errors_only")
            visible_rows = [row for row in error_rows if row["Trạng thái"] == "FAIL"] if only_errors else error_rows
            st.dataframe(visible_rows, hide_index=True, width="stretch")
    with st.expander("Trạng thái gate và điều kiện projection"):
        st.json(model.get("gate_statuses", {}))
        st.caption("Khi có story.srt, preflight audio-first đo lời thật và khóa export nếu thoại không vừa clip; safety/no-invented-event là tư vấn.")
    if model.get("speech_timing_rows"):
        with st.expander("Đối chiếu thời lượng thoại thật", expanded=bool(model["errors"])):
            st.caption("Container đề xuất đã gồm 0,5 giây đệm an toàn. Giá trị trống nghĩa là phải chia lời thoại.")
            st.dataframe(model["speech_timing_rows"], hide_index=True, width="stretch")
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
        st.json({k: clip.get(k) for k in ("source_script", "voice_plan", "reference_inputs", "generation_variants", "continuity_in", "continuity_out", "state_change_records", "avoid")}, expanded=False)
    with st.expander("Continuity toàn cục và kết luận do file khai báo"):
        st.json({"global_continuity_lock": plan.get("global_continuity_lock"), "validation": plan.get("validation")}, expanded=False)
    if not model["errors"]:
        from studio.prompt_contract import load_prompt_contract
        from studio.video_prompt_adapters import adapter_targets, get_adapter
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
        st.success("Kế hoạch canonical: PASS · cấu trúc, source binding và digest đã hợp lệ.")
        projection_target = st.selectbox("Target export", adapter_targets(), key=f"{key_prefix}_projection_target")
        adapter = get_adapter(projection_target)
        warnings = adapter.capability_warnings(plan)
        gate_statuses = model.get("gate_statuses", {})
        required_gates = tuple(model.get("required_export_gates", ()))
        advisory_gates = tuple(model.get("advisory_export_gates", ()))
        pending = [name for name in required_gates if gate_statuses.get(name) != "PASS"]
        gate_advisories = [name for name in advisory_gates if gate_statuses.get(name) != "PASS"]
        capability_blockers = [warning for warning in warnings if "chưa tương thích" in warning]
        capability_advisories = [warning for warning in warnings if warning not in capability_blockers]
        export_eligible = bool(model.get("export_eligible")) and not capability_blockers
        if export_eligible:
            st.success("Điều kiện export: PASS · các kiểm tra cấu trúc và source binding bắt buộc đã đạt.")
        else:
            st.warning("Điều kiện export: CHƯA ĐẠT · còn gate bắt buộc chưa PASS.")
        blockers = [
            {"Nhóm": "Capability", "Điều kiện": warning, "Trạng thái": "FAIL"}
            for warning in capability_blockers
        ]
        blockers.extend(
            {"Nhóm": "Gate", "Điều kiện": name, "Trạng thái": model["gate_statuses"][name]}
            for name in pending
        )
        if blockers:
            with st.expander(f"Điều kiện chặn export ({len(blockers)})", expanded=True):
                st.dataframe(blockers, hide_index=True, width="stretch")
        advisory_rows = [
            {"Nhóm": "Gate", "Điều kiện": name, "Trạng thái": gate_statuses.get(name), "Mức": "ADVISORY"}
            for name in gate_advisories
        ]
        advisory_rows.extend(
            {"Nhóm": "Capability", "Điều kiện": warning, "Trạng thái": "NOT_VERIFIED", "Mức": "ADVISORY"}
            for warning in capability_advisories
        )
        if advisory_rows:
            with st.expander(f"Cảnh báo tư vấn ({len(advisory_rows)})"):
                st.dataframe(advisory_rows, hide_index=True, width="stretch")
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
            key=f"{key_prefix}_{projection_target.lower()}_projection", disabled=not export_eligible,
        )
        columns[1].download_button(
            "Tải prompt text", text_payload,
            file_name=f"{stem}.{projection_target.lower()}.txt", mime="text/plain",
            key=f"{key_prefix}_{projection_target.lower()}_text", disabled=not export_eligible,
        )
        columns[2].download_button(
            "Tải gói ZIP", zip_payload, file_name=zip_name, mime="application/zip",
            key=f"{key_prefix}_{projection_target.lower()}_package", disabled=not export_eligible,
        )
    else:
        st.error("Không thể export vì video_prompts.json chưa đạt kiểm tra cấu trúc canonical.")


def visual_bible_summary(document: Mapping[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    """Build deterministic, read-only Stage 2 Visual Bible checks."""
    required = {"schema_version", "image_mode", "reference_mode", "targets", "characters", "assets"}
    missing = sorted(required.difference(document))
    extra = sorted(set(document).difference(required))
    characters = _items(document.get("characters"))
    assets = _items(document.get("assets"))
    errors = [f"Thiếu trường bắt buộc: {key}" for key in missing]
    errors.extend(f"Trường ngoài schema: {key}" for key in extra)
    if document.get("schema_version") != "4.1.3":
        errors.append("schema_version phải là 4.1.3.")
    try:
        expected_names = set(active_image_basenames(document))
    except ValueError as exc:
        expected_names = set()
        errors.append(str(exc))
    reference_ready = sum(row.get("reference_status") == "READY" for row in characters)
    reference_checked = 0
    reference_passed = 0
    landscape_checked = 0
    landscape_passed = 0
    story_links = "NOT_VERIFIED"
    if root is not None:
        try:
            story = read_json((root / "story.json").read_bytes())
            character_ids = {row.get("character_id") for row in _items(story.get("characters"))}
            script_ids = {row.get("id") for row in _items(story.get("script"))}
            linked_ids = {row.get("character_id") for row in characters}
            asset_character_ids = {value for row in assets for value in row.get("character_ids", [])}
            source_ids = {value for row in assets for value in row.get("source_script_ids", [])}
            story_links = "PASS" if linked_ids <= character_ids and asset_character_ids <= character_ids and source_ids <= script_ids else "FAIL"
        except (OSError, ValueError, TypeError):
            story_links = "NOT_VERIFIED"
        for row in characters:
            path_text = row.get("reference_path")
            if row.get("reference_status") != "READY":
                continue
            reference_checked += 1
            if not isinstance(path_text, str) or not safe_name(path_text):
                continue
            try:
                path = (root / path_text).resolve()
                if path.is_relative_to(root.resolve()) and path.is_file():
                    image_metadata(path)
                    reference_passed += 1
            except (OSError, SyntaxError, ValueError):
                pass
        for name in expected_names:
            landscape_checked += 1
            try:
                path = (root / "landscape" / name).resolve()
                metadata = image_metadata(path)
                if path.is_relative_to(root.resolve()) and metadata["format"] == "PNG" and metadata["width"] > metadata["height"]:
                    landscape_passed += 1
            except (OSError, SyntaxError, ValueError):
                pass
    if story_links == "FAIL":
        errors.append("Liên kết character_id/source_script_ids không khớp story.json.")
    if reference_checked and reference_passed != reference_checked:
        errors.append(f"Chỉ {reference_passed}/{reference_checked} ảnh nhân vật READY tồn tại và giải mã được.")
    if landscape_checked and landscape_passed != landscape_checked:
        errors.append(f"Chỉ {landscape_passed}/{landscape_checked} ảnh landscape tồn tại, là PNG và đúng orientation.")
    return {
        "characters": len(characters), "reference_ready": reference_ready,
        "assets": len(assets), "expected_assets": len(expected_names),
        "story_links": story_links, "reference_passed": reference_passed,
        "reference_checked": reference_checked, "landscape_passed": landscape_passed,
        "landscape_checked": landscape_checked, "errors": errors,
        "status": "FAIL" if errors else "PASS" if root is not None and story_links == "PASS" else "NOT_VERIFIED",
    }


def render_visual_bible(document: Mapping[str, Any], *, root: Path | None = None) -> None:
    import streamlit as st

    if not document:
        st.info("Visual Bible là artifact lineage Stage 2 và bắt buộc được retain trong package Stage 2–4.")
        return
    st.caption("Dữ liệu nguồn chỉ đọc. Các khóa và trạng thái bên dưới là khai báo, chưa được detector độc lập xác minh.")
    summary = visual_bible_summary(document, root=root)
    columns = st.columns(4)
    columns[0].metric("Nhân vật", summary["characters"])
    columns[1].metric("Ảnh nhân vật READY", f"{summary['reference_passed']}/{summary['reference_ready']}")
    columns[2].metric("Ảnh landscape", f"{summary['landscape_passed']}/{summary['expected_assets']}")
    columns[3].metric("Liên kết story", summary["story_links"])
    if summary["errors"]:
        for error in summary["errors"]:
            st.error(error)
    elif summary["status"] == "PASS":
        st.success("Các kiểm tra cấu trúc và binding tại máy của Visual Bible đều đạt.")
    else:
        st.warning("Visual Bible có đủ cấu trúc nhưng chưa thể xác minh story binding tại máy.")
    st.subheader("Dữ liệu chi tiết")
    for key, value in document.items():
        with st.expander(str(key), expanded=key == "schema_version"):
            st.json(value) if isinstance(value, (dict, list)) else st.write(value)


def render_workflow_workspace(root: Path, reports: Mapping[str, Any], state: Mapping[str, Any]) -> None:
    import streamlit as st

    st.caption("ZIP được đọc trong bộ nhớ và phải đúng hợp đồng v4.1.6; gói phiên bản cũ bị từ chối.")
    resolved_root = str(root.resolve())
    if state.get(VERIFICATION_ROOT_KEY) != resolved_root:
        state[VERIFICATION_ROOT_KEY] = resolved_root
        state[VERIFICATION_SOURCE_KEY] = DIRECTORY_SOURCE
        state.pop(VERIFICATION_UPLOAD_BYTES_KEY, None)
    options = [DIRECTORY_SOURCE, LOCAL_ZIP_SOURCE, UPLOADED_ZIP_SOURCE]
    if state.get(VERIFICATION_SOURCE_KEY) not in options:
        state[VERIFICATION_SOURCE_KEY] = DIRECTORY_SOURCE
    source = st.radio(
        "Nguồn kiểm định", options, horizontal=True, key=VERIFICATION_SOURCE_KEY,
        format_func=lambda value: VERIFICATION_SOURCE_LABELS[value],
    )
    members = None
    parent = None
    try:
        parent_upload = st.file_uploader(
            "Gói cha trực tiếp (Stage trước hoặc cùng Stage khi REPAIR)",
            type=["zip"], key=f"workflow_parent_{root.resolve()}",
            help="Có thể cung cấp gói cha cả khi gói hiện tại là thư mục giải nén.",
        )
        if parent_upload:
            parent = read_archive(parent_upload.getvalue())
        if source == UPLOADED_ZIP_SOURCE:
            uploaded = st.file_uploader("Gói cần kiểm định", type=["zip"], key=f"workflow_zip_{root.resolve()}")
            if uploaded is None and not state.get(VERIFICATION_UPLOAD_BYTES_KEY):
                st.info("Chọn một ZIP v4.1.6: story_stage1.zip, story_stage2.zip, story.zip hoặc story_video_prompts.zip.")
                return
            if uploaded is not None:
                state[VERIFICATION_UPLOAD_BYTES_KEY] = uploaded.getvalue()
        overrides = state.get("story_overrides", {}) if state.get("story_override_root") == str(root.resolve()) else {}
        result = inspect_selected_workflow(
            root, state,
            overridden=any(key in {"story", "validation", "quality", "anchor"} for key in overrides),
            parent=parent,
        )
        if source != DIRECTORY_SOURCE:
            members = read_archive(root / "story.zip" if source == LOCAL_ZIP_SOURCE else state[VERIFICATION_UPLOAD_BYTES_KEY])
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        st.error(f"Không đọc được gói: {exc}")
        return
    render_workflow_summary(result)
    comparison = result.get("source_comparison")
    if comparison:
        (st.success if comparison["status"] == "PASS" else st.error)(comparison["detail"])
    st.dataframe(result["checks"], hide_index=True, width="stretch")
    st.caption("Phạm vi kiểm tra: schema manifest, allowlist, hash/size, ownership, CRC và parent trực tiếp khi được cung cấp. Không chứng nhận an toàn/nội dung/mỹ thuật chỉ từ metadata.")
    if result["compatibility"] != "NATIVE_CURRENT":
        st.error("UNSUPPORTED: gói không đúng v4.1.6 và sẽ không được mở ở chế độ tương thích.")
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
                    elif selected == "visual_plan.json":
                        render_visual_bible(doc, root=root)
                    else:
                        st.json(doc, expanded=False)
            except (ValueError, OSError, RecursionError) as exc:
                st.error(f"Artifact không hợp lệ: {exc}")
