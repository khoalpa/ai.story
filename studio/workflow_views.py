"""Streamlit views for read-only workflow packages and video prompt plans."""
from __future__ import annotations

import hashlib
import math
import re
import zipfile
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from studio.package_migration import (
    SUPPORTED_SOURCE_VERSIONS,
    TARGET_VERSION,
    migrate_extracted_package,
    publish_migrated_package,
)
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
from studio.workflow_builder import (
    complete_stage_atomic,
    plan_directory_integrity_repair,
    plan_stage_completion,
    repair_directory_integrity,
    resolve_remaining_work_atomic,
    restore_integrity_backup,
)
from studio.workflow_package import (
    STAGES,
    active_image_basenames,
    read_archive,
    read_json,
    safe_name,
)

STAGE_LABELS = ("Truyện & nhân vật", "Landscape", "Portrait & gói audio", "Prompt video")


def image_prompt_schema_repair_candidate(result: Mapping[str, Any]) -> bool:
    """Return whether the package has only the guarded image-prompts failure."""
    failed = {
        str(row.get("check")) for row in result.get("checks", [])
        if isinstance(row, Mapping) and row.get("status") == "FAIL"
    }
    return not result.get("archive") and failed == {"image_prompts"}


def _image_prompt_change_rows(root: Path, migrated: Mapping[str, bytes]) -> list[dict[str, str]]:
    before = read_json((root / "image_prompts.json").read_bytes())
    after = read_json(migrated["image_prompts.json"])
    keys = sorted(set(before) | set(after))
    rows: list[dict[str, str]] = []
    for key in keys:
        if key not in before:
            change = "Thêm"
        elif key not in after:
            change = "Xóa trường ngoài schema"
        elif before[key] != after[key]:
            change = "Chuẩn hóa"
        else:
            continue
        rows.append({"trường": key, "thay đổi": change})
    return rows


def render_image_prompt_schema_repair(
    root: Path, result: Mapping[str, Any], state: MutableMapping[str, Any],
) -> None:
    """Offer an immutable v5.2 repair next to an image-prompts-only failure."""
    if not image_prompt_schema_repair_candidate(result):
        return
    import streamlit as st

    key_prefix = f"image_prompt_schema_repair_{root.resolve()}"
    result_key = f"{key_prefix}_result"
    st.subheader("Sửa schema image_prompts")
    st.warning(
        "Có thể tạo một gói REPAIR an toàn: chuẩn hóa image_prompts.json sang v5.2.2 "
        "mà không sửa story hoặc ảnh. Gói nguồn sẽ không bị ghi đè."
    )
    if st.button("Phân tích phương án sửa", type="primary", key=f"{key_prefix}_build"):
        try:
            state[result_key] = migrate_extracted_package(root)
        except (OSError, ValueError, KeyError) as exc:
            state.pop(result_key, None)
            st.error(f"Không thể tạo phương án sửa: {exc}")
    migration = state.get(result_key)
    if migration is None:
        return
    try:
        changes = _image_prompt_change_rows(root, migration.members)
    except (OSError, ValueError, KeyError) as exc:
        st.error(f"Không thể tạo bản xem trước: {exc}")
        return
    with st.expander("Xem trước thay đổi", expanded=True):
        st.dataframe(changes, hide_index=True, width="stretch")
        st.caption(
            "Phiên bản đích: image_prompt_version 1.1 · prompt_version 5.2.2 · "
            "prompt_encoding T5-512 · source_story SHA-256 được đồng bộ."
        )
        st.warning(
            "Snapshot sau sửa có trạng thái PARTIAL; các gate v5.2.2 chuyển thành "
            "NOT_CHECKED và phải được kiểm định lại trước khi publish."
        )
    st.download_button(
        "Tải ZIP REPAIR", data=migration.archive_bytes,
        file_name=migration.archive_name, mime="application/zip",
        key=f"{key_prefix}_download",
    )
    default_destination = root.parent / f"{root.name}_image_prompts_repaired"
    destination = Path(st.text_input(
        "Thư mục đích mới", value=str(default_destination),
        key=f"{key_prefix}_destination",
        help="Chỉ ghi vào thư mục mới hoặc thư mục đang trống; không ghi đè nguồn.",
    )).expanduser()
    if st.button("Ghi gói REPAIR vào thư mục mới", key=f"{key_prefix}_publish"):
        try:
            written = publish_migrated_package(migration, destination)
        except (OSError, ValueError) as exc:
            st.error(f"Không thể ghi gói REPAIR: {exc}")
        else:
            st.success(f"Đã ghi gói, ZIP và migration_report.json tại {written}")


def render_package_migration(root: Path, state: MutableMapping[str, Any]) -> None:
    """Render a guided, immutable migration flow for an extracted package."""
    import streamlit as st

    key_prefix = f"package_migration_{root.resolve()}"
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        st.info(
            "Không tìm thấy manifest.json. Hãy chọn thư mục của một gói đã giải nén "
            "để kiểm tra khả năng nâng cấp."
        )
        return

    try:
        manifest = read_json(manifest_path.read_bytes())
        source_version = manifest.get("prompt_version")
        source_stage = manifest.get("stage")
    except (OSError, ValueError) as exc:
        st.error(f"Không thể đọc manifest.json: {exc}")
        return

    # A healthy current package needs no migration. Contextual v5.2 schema repair is
    # offered later, next to its verification failure.
    if source_version == TARGET_VERSION:
        return

    st.subheader(f"Nâng cấp gói lên v{TARGET_VERSION}")
    st.caption("Gói gốc sẽ không bị thay đổi. Bản nâng cấp được tạo thành một gói mới.")
    supported = source_version in SUPPORTED_SOURCE_VERSIONS
    stage_supported = (
        source_stage == 4 if isinstance(source_version, str) and source_version.startswith("4.")
        else type(source_stage) is int and source_stage in {1, 2, 3}
    )
    target_stage = 3 if isinstance(source_version, str) and source_version.startswith("4.") else source_stage
    summary_columns = st.columns(4)
    summary_columns[0].metric("Phiên bản nguồn", f"v{source_version}" if source_version else "Không rõ")
    summary_columns[1].metric("Phiên bản đích", f"v{TARGET_VERSION}")
    summary_columns[2].metric("Stage", f"{source_stage} → {target_stage}" if source_stage else "Không rõ")
    summary_columns[3].metric(
        "Khả năng nâng cấp", "Sẵn sàng" if supported and stage_supported else "Không hỗ trợ",
    )
    st.markdown("**1. Kiểm tra nguồn  →  2. Xem thay đổi  →  3. Xuất gói**")

    if not supported or not stage_supported:
        versions = ", ".join(f"v{version}" for version in SUPPORTED_SOURCE_VERSIONS if version != TARGET_VERSION)
        st.error(
            f"Gói này chưa thể nâng cấp trực tiếp. Phiên bản được hỗ trợ: {versions}; "
            "gói v4 phải là Stage 4 đầy đủ."
        )
        return

    result_key = f"{key_prefix}_result"
    error_key = f"{key_prefix}_error"
    if st.button(
        "Kiểm tra và xem thay đổi", type="primary", key=f"{key_prefix}_build",
        help="Kiểm tra tính toàn vẹn rồi tạo bản nâng cấp trong bộ nhớ.",
    ):
        state.pop(error_key, None)
        try:
            with st.spinner("Đang kiểm tra và tạo bản nâng cấp…"):
                state[result_key] = migrate_extracted_package(root)
        except (OSError, ValueError, KeyError) as exc:
            state.pop(result_key, None)
            state[error_key] = str(exc)

    if state.get(error_key):
        message = str(state[error_key])
        if message.startswith("SOURCE_INVALID:"):
            message = "Gói nguồn không vượt qua kiểm tra tính toàn vẹn. " + message.removeprefix("SOURCE_INVALID:").strip()
        st.error(message)
        st.caption("Hãy khôi phục các file gốc theo manifest rồi kiểm tra lại.")

    result = state.get(result_key)
    if result is None:
        return

    transformed = list(result.report.get("transformed_files", []))
    preserved = list(result.report.get("preserved_files", []))
    st.success(
        f"Đã kiểm tra và tạo bản nâng cấp v{result.source_version} → "
        f"v{result.target_version}. Gói gốc được giữ nguyên."
    )
    st.markdown("#### 2. Xem thay đổi")
    st.dataframe([
        {"Nội dung": "Phiên bản", "Kết quả": f"v{result.source_version} → v{result.target_version}"},
        {"Nội dung": "Stage", "Kết quả": f"Stage {result.report.get('source_stage')} → Stage {result.report.get('target_stage')}"},
        {"Nội dung": "File được cập nhật", "Kết quả": len(transformed)},
        {"Nội dung": "File được giữ nguyên", "Kết quả": len(preserved)},
        {"Nội dung": "Trạng thái kiểm định", "Kết quả": "Cần chạy lại các kiểm định bắt buộc"},
        {"Nội dung": "Gói nguồn", "Kết quả": "Không thay đổi"},
    ], hide_index=True, width="stretch")
    if transformed:
        st.markdown("**Đã thực hiện:** " + ", ".join(f"`{name}`" for name in transformed))
    st.warning("Việc cần làm tiếp: chạy lại toàn bộ kiểm định bắt buộc của v5.2.2.")
    with st.expander("Chi tiết kỹ thuật", expanded=False):
        st.json(result.report)

    st.markdown("#### 3. Xuất gói")
    export_mode = st.radio(
        "Cách xuất", ("Lưu thành thư mục mới", "Tải file ZIP"), horizontal=True,
        key=f"{key_prefix}_export_mode",
        help="Lưu thành thư mục để tiếp tục làm việc trong Studio; tải ZIP để gửi hoặc lưu trữ.",
    )
    if export_mode == "Tải file ZIP":
        st.download_button(
            f"Tải gói v{TARGET_VERSION}", data=result.archive_bytes,
            file_name=result.archive_name, mime="application/zip", type="primary",
            key=f"{key_prefix}_download",
        )
        return

    default_destination = root.parent / f"{root.name}_v{TARGET_VERSION.replace('.', '_')}"
    destination = Path(st.text_input(
        "Thư mục đích mới", value=str(default_destination),
        key=f"{key_prefix}_destination",
        help="Chỉ ghi vào thư mục mới hoặc thư mục đang trống.",
    )).expanduser()
    if st.button(f"Lưu gói v{TARGET_VERSION}", type="primary", key=f"{key_prefix}_publish"):
        try:
            written = publish_migrated_package(result, destination)
            state[f"{key_prefix}_written"] = str(written)
        except (OSError, ValueError) as exc:
            st.error(f"Không thể lưu gói: {exc}")
    if state.get(f"{key_prefix}_written"):
        st.success(f"Đã lưu gói và migration_report.json tại {state[f'{key_prefix}_written']}")


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
        "PARTIAL": "Stage hiện tại · kiểm định đạt, chưa hoàn tất",
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
    integrity_status = str(result.get("integrity_status") or "NOT_VERIFIED")
    gate_status = str(result.get("stage_gate_status") or "NOT_VERIFIED")
    publish_status = str(result.get("publish_status") or "NOT_VERIFIED")
    completion_status = str(
        result.get("package_completion_status")
        or manifest.get("status")
        or "UNKNOWN"
    )
    status = str(result.get("overall_status") or (
        "FAIL" if integrity_status == "FAIL" or gate_status == "FAIL"
        else "PASS" if integrity_status == gate_status == publish_status == "PASS"
        else "NOT_VERIFIED"
    ))
    image_count = sum(
        1 for row in result.get("files", [])
        if isinstance(row, Mapping) and str(row.get("path", "")).startswith("landscape/")
    )
    is_v5 = manifest.get("prompt_version") in {"5.0.0", "5.1.0", "5.2.0", "5.2.2"}
    active_stages = STAGES[:3] if is_v5 else STAGES
    labels = list(STAGE_LABELS[:3] if is_v5 else STAGE_LABELS)
    if image_count:
        labels[1] = f"{image_count} landscape"
        labels[2] = f"{image_count} portrait & gói audio"
    for column, name, label in zip(st.columns(len(active_stages)), active_stages, labels):
        column.markdown(f"**{name} · {label}**")
        column.caption(workflow_stage_caption(name, stage, status))
    if status == "PASS" and publish_status == "PASS":
        message = "Gói đã được xác minh và đủ điều kiện publish"
    elif status == "FAIL":
        message = "Gói có lỗi cần xử lý"
    elif integrity_status == "PASS" and completion_status != "COMPLETE":
        message = f"Gói hợp lệ về cấu trúc nhưng đang ở trạng thái {completion_status}; chưa đủ điều kiện publish"
    elif integrity_status == "PASS":
        message = "Gói hợp lệ về cấu trúc nhưng chưa đủ bằng chứng xác minh; chưa đủ điều kiện publish"
    else:
        message = "Chưa đủ bằng chứng xác minh toàn bộ gói"
    (st.error if status == "FAIL" else st.success if status == "PASS" else st.warning)(message)
    if status == "FAIL":
        failures = [str(item.get("detail")) for item in result.get("checks", [])
                    if isinstance(item, Mapping) and item.get("status") == "FAIL" and item.get("detail")]
        if failures:
            st.caption("Nguyên nhân xác định: " + failures[0])
    blockers = []
    if integrity_status != "PASS":
        blockers.append("toàn vẹn gói chưa đạt")
    if completion_status != "COMPLETE":
        blockers.append(f"manifest đang là {completion_status}")
    if gate_status != "PASS":
        blockers.append(f"gate của stage là {gate_status}")
    if publish_status != "PASS" and blockers:
        st.caption("Nguyên nhân chưa thể publish: " + "; ".join(blockers) + ".")
    st.caption(f"Toàn vẹn & parent trực tiếp: {integrity_status} · Trạng thái manifest: {completion_status} · "
               f"Toàn bộ gate của stage: {gate_status} · Đủ điều kiện publish: {publish_status}")
    st.caption("Chuyển stage thủ công. V5 kết thúc ở Stage 3; audio/video render nằm ngoài package stage. Báo cáo tự khai PASS không thay detector.")
    if result.get("next_stage"):
        st.caption(f"Bước kế tiếp theo manifest: {result['next_stage']} · chỉ thực hiện khi toàn bộ gate đầu vào đạt.")
    if result.get("expected_count") is not None:
        st.caption(f"File trong phạm vi gói: {result['actual_count']}/{result['expected_count']} · không đếm file audio/video sản xuất ngoài gói.")


def render_manifest_repair(root: Path, result: Mapping[str, Any]) -> None:
    """Preview and apply guarded integrity repairs for a directory package."""
    import streamlit as st

    failed_checks = {
        str(row.get("check")) for row in result.get("checks", [])
        if isinstance(row, Mapping) and row.get("status") == "FAIL"
    }
    backup_key = f"workflow_repair_backup_{root.resolve()}"
    backup_value = st.session_state.get(backup_key)
    if backup_value:
        st.success("Lần sửa gần nhất đã đạt kiểm định. Bản sao lưu vẫn được giữ để hoàn tác.")
        if st.button("Hoàn tác lần sửa gần nhất", key=f"workflow_repair_undo_{root.resolve()}"):
            try:
                restore_integrity_backup(root, Path(backup_value))
            except (OSError, ValueError) as exc:
                st.error(f"Hoàn tác thất bại: {exc}")
            else:
                st.session_state.pop(backup_key, None)
                st.success("Đã khôi phục các tệp từ bản sao lưu.")
                st.rerun()
    if result.get("integrity_status") == "PASS" and result.get("package_completion_status") != "COMPLETE":
        completion = plan_stage_completion(root)
        with st.expander("Hoàn tất Stage", expanded=bool(completion["can_complete"])):
            if completion["blockers"]:
                for blocker in completion["blockers"]:
                    st.warning(blocker)
                remaining_work = completion.get("remaining_work", [])
                if remaining_work:
                    st.caption("Chỉ đóng những đầu việc đã được kiểm tra thực tế; thao tác sẽ lưu bằng chứng và cập nhật hash/checkpoint.")
                    with st.form(f"workflow_resolve_work_{root.resolve()}"):
                        selected_work = st.multiselect(
                            "Đầu việc đã giải quyết", remaining_work,
                            placeholder="Chọn một hoặc nhiều đầu việc…",
                        )
                        resolver = st.text_input("Người xác nhận", placeholder="Tên hoặc định danh")
                        resolution_evidence = st.text_area(
                            "Bằng chứng đóng đầu việc",
                            placeholder="Nêu tài sản đã kiểm tra, tiêu chí và kết luận…",
                            help="Bắt buộc; tối thiểu 12 ký tự.",
                        )
                        resolve_submitted = st.form_submit_button("Lưu và đóng đầu việc", type="primary")
                    if resolve_submitted:
                        try:
                            _inspection, backup = resolve_remaining_work_atomic(
                                root, selected_work, resolution_evidence, reviewer=resolver,
                            )
                        except (OSError, KeyError, TypeError, ValueError) as exc:
                            st.error(f"Không thể đóng đầu việc: {exc}")
                        else:
                            st.session_state[backup_key] = str(backup)
                            st.success("Đã đóng đầu việc được chọn và đồng bộ report/manifest/checkpoint.")
                            st.rerun()
            else:
                st.caption(" · ".join(completion["changes"]))
                if st.button("Xác minh và hoàn tất Stage", key=f"workflow_complete_{root.resolve()}"):
                    try:
                        _inspection, backup = complete_stage_atomic(root)
                    except (OSError, ValueError) as exc:
                        st.error(f"Không thể hoàn tất Stage: {exc}")
                    else:
                        st.session_state[backup_key] = str(backup)
                        st.success("Stage đã COMPLETE; manifest/hash đã đồng bộ và post-write validation đạt.")
                        st.rerun()
    # image_files can be a downstream failure of an invalid visual basename;
    # the repair planner still has to prove that an extension-only fix is safe.
    repairable_checks = {"manifest_files", "file_set", "file_digest", "image_files", "image_prompts"}
    if result.get("archive") or not failed_checks or not failed_checks.issubset(repairable_checks):
        return
    try:
        plan = plan_directory_integrity_repair(root)
    except (OSError, ValueError, KeyError) as exc:
        st.error(f"Không thể phân tích phương án sửa: {exc}")
        return
    if not plan["actions"] and not plan["blockers"]:
        return
    st.subheader("Sửa tính toàn vẹn gói")
    decisions = plan.get("decision_requests", [])
    if decisions:
        st.warning(f"Phát hiện lỗi; cần giải quyết {len(decisions)} lựa chọn trước khi sửa.")
    else:
        st.warning(f"Phát hiện {len(failed_checks)} lỗi kiểm định có thể sửa an toàn tại máy.")
    resolutions: dict[str, Any] = {"exclude_paths": [], "asset_source_ids": {}}
    if decisions:
        st.markdown("**Lựa chọn của người dùng**")
        for decision in decisions:
            if decision["kind"] == "EXTRA_FILE":
                path = str(decision["path"])
                choice = st.radio(
                    f"Tệp ngoài contract: {path}",
                    ["Chưa quyết định", "Giữ trên đĩa, loại khỏi gói"],
                    key=f"workflow_extra_{root.resolve()}_{path}", horizontal=True,
                    help="Tệp không bị xóa; chỉ bị loại khỏi manifest và ZIP checkpoint.",
                )
                if choice == "Giữ trên đĩa, loại khỏi gói":
                    resolutions["exclude_paths"].append(path)
            elif decision["kind"] == "ASSET_SOURCE_IDS":
                index = int(decision["index"])
                role = decision.get("role") or "—"
                st.caption(
                    f"assets[{index}] · {decision.get('asset_id') or '—'} · {role} · "
                    f"{decision.get('brief') or 'Không có brief'}"
                )
                scripts = decision.get("scripts", [])
                options = [str(row["id"]) for row in scripts]
                text_by_id = {str(row["id"]): str(row.get("text") or "") for row in scripts}
                selected = st.multiselect(
                    f"Story ID cho assets[{index}]",
                    options,
                    key=f"workflow_asset_sources_{root.resolve()}_{index}",
                    format_func=lambda value, texts=text_by_id: f"{value} — {texts.get(value, '')[:100]}",
                    placeholder="Chọn một hoặc nhiều đoạn truyện…",
                )
                if selected:
                    resolutions["asset_source_ids"][str(index)] = selected
        try:
            resolved_plan = plan_directory_integrity_repair(root, resolutions=resolutions)
        except (OSError, ValueError, KeyError) as exc:
            st.error(f"Không thể kiểm tra lựa chọn: {exc}")
        else:
            plan = resolved_plan
    with st.expander("Xem trước thay đổi", expanded=True):
        for action in plan["actions"]:
            st.markdown(f"- {action['detail']}")
            paths = action.get("paths") or [row["path"] for row in action.get("links", [])]
            if paths:
                st.caption(" · ".join(paths))
            changes = action.get("changes", [])
            if changes:
                labels = []
                for row in changes:
                    location = f"assets[{row['index']}].{row['field']}: " if "index" in row else ""
                    labels.append(f"{location}{row.get('from', '—')} → {row.get('to', 'loại bản trùng')}")
                st.caption(" · ".join(labels))
        for blocker in plan["blockers"]:
            st.error(blocker)
    st.caption("Ứng dụng tạo bản sao lưu, sửa trên ứng viên, kiểm định toàn bộ rồi mới ghi manifest và ZIP checkpoint.")
    if st.button("Xem trước đã xác nhận · tạo bản sao lưu và sửa", type="primary", disabled=not plan["can_repair"], key=f"workflow_repair_integrity_{root.resolve()}"):
        try:
            repaired, backup = repair_directory_integrity(root, resolutions=resolutions)
        except (OSError, ValueError, KeyError) as exc:
            st.error(f"Sửa tính toàn vẹn thất bại: {exc}")
        else:
            if repaired.get("integrity_status") == "PASS":
                st.session_state[backup_key] = str(backup)
                st.success("Đã sửa tính toàn vẹn, tạo lại ZIP checkpoint và hậu kiểm thành công.")
                st.rerun()


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
        st.info("Chưa có video_prompts.json; v5 yêu cầu từ Stage 1, v4 legacy chỉ bắt buộc ở Stage 4.")
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


def render_workflow_workspace(root: Path, reports: Mapping[str, Any], state: MutableMapping[str, Any]) -> None:
    import streamlit as st

    st.caption("ZIP được đọc trong bộ nhớ và phải đúng prompt v5 hoặc v4 legacy được hỗ trợ.")
    render_package_migration(root, state)
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
                st.info("Chọn ZIP v5 Stage 1–3 hoặc ZIP legacy v4 Stage 1–4.")
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
    if source == DIRECTORY_SOURCE:
        render_image_prompt_schema_repair(root, result, state)
        render_manifest_repair(root, result)
    st.caption("Phạm vi kiểm tra: schema manifest, allowlist, hash/size, ownership, CRC và parent trực tiếp khi được cung cấp. Không chứng nhận an toàn/nội dung/mỹ thuật chỉ từ metadata.")
    if result["compatibility"] != "NATIVE_CURRENT":
        st.error("UNSUPPORTED: gói không đúng prompt v5 hoặc v4 legacy được hỗ trợ.")
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
