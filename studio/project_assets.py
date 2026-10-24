"""Read-only asset inventory and exact-byte report binding checks."""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, UnidentifiedImageError

from studio.asset_history import (
    content_fingerprint,
    load_asset_history,
    observation_status,
    record_asset_observations,
)
from studio.package_quality_report import _items, _object
from studio.story_images import (
    IMAGE_SUFFIXES,
    is_project_image,
    render_image_thumbnail,
    stage_applicable_aspects,
    visual_plan_image_stems,
)
from studio.workflow_package import read_json

USER_REPLACEABLE_COVERS = {"landscape/cover.png", "portrait/cover.png"}


def project_asset_path(root: Path, relative: str) -> Path | None:
    """Report paths may only reference files within the active project."""
    try:
        path = (root / relative).resolve()
        return path if path.is_relative_to(root.resolve()) else None
    except (OSError, ValueError):
        return None


@lru_cache(maxsize=256)
def _file_facts(path: str, modified: int, size: int, changed: int) -> tuple[str, tuple[int, int] | None]:
    del modified, size, changed
    source = Path(path)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    dimensions = None
    if source.suffix.lower() in IMAGE_SUFFIXES:
        with Image.open(source) as image:
            dimensions = image.size
            image.verify()
    return digest, dimensions


def file_facts(path: Path) -> tuple[str, tuple[int, int] | None]:
    stat = path.stat()
    return _file_facts(str(path.resolve()), stat.st_mtime_ns, stat.st_size, stat.st_ctime_ns)


def inspect_project_assets(root: Path, reports: Mapping[str, Any]) -> list[dict[str, Any]]:
    expected: dict[str, dict[str, Any]] = {}
    try:
        visual_plan = read_json((root / "visual_plan.json").read_bytes())
    except (OSError, ValueError):
        visual_plan = {}
    targets = _object(visual_plan.get("targets"))
    for group in ("landscape", "portrait"):
        stage_number = _object(reports.get("workflow")).get("stage")
        stage = f"STAGE{stage_number}" if type(stage_number) is int and stage_number in range(1, 5) else None
        if stage == "STAGE1" or (stage == "STAGE2" and group == "portrait"):
            continue
        target = _object(targets.get(group))
        declaration = ({"dimensions": {"width": target.get("width"), "height": target.get("height")}}
                       if target.get("size_policy") == "EXACT" else {})
        for stem in visual_plan_image_stems(root):
            expected[f"{group}/{stem}.png"] = declaration
    for character in _items(_object(reports.get("story")).get("characters")):
        asset = _object(character.get("reference_asset"))
        name = str(asset.get("reference_image") or f"characters/{character.get('character_id', 'unknown')}.png")
        expected[name] = dict(asset)
    evidence = {
        str(row.get("path")): row
        for row in _items(_object(_object(reports.get("quality")).get("image_evidence")).get("asset_results"))
    }
    manifest_bindings = {str(row.get("path")): row for row in _items(_object(reports.get("workflow")).get("files"))}
    for name in evidence:
        expected.setdefault(name, {})
    for group in ("characters", "landscape", "portrait"):
        directory = root / group
        if directory.is_dir():
            for discovered in directory.iterdir():
                if is_project_image(discovered):
                    expected.setdefault(f"{group}/{discovered.name}", {})
    rows = []
    for name, declared in expected.items():
        path = project_asset_path(root, name)
        issues: list[str] = []
        notices: list[str] = []
        dimensions = None
        digest = ""
        size = 0
        try:
            if path is None:
                issues.append("Đường dẫn ngoài dự án")
            elif not path.is_file():
                issues.append("Thiếu ảnh")
            else:
                digest, dimensions = file_facts(path)
                size = path.stat().st_size
        except (OSError, ValueError, SyntaxError, UnidentifiedImageError):
            issues.append("Không đọc được ảnh")
        bindings = [declared, evidence.get(name, {}), manifest_bindings.get(name, {})]
        hashes = [a.get("file_sha256") or a.get("sha256") for a in bindings
                  if a.get("file_sha256") or a.get("sha256")]
        if digest and any(digest != h for h in hashes):
            if name.replace("\\", "/").casefold() in USER_REPLACEABLE_COVERS:
                notices.append("Ảnh cover đã được người dùng thay đổi")
            else:
                issues.append("Hash không khớp báo cáo")
        for binding in bindings:
            target = _object(binding.get("dimensions"))
            if dimensions and target and dimensions != (target.get("width"), target.get("height")):
                issues.append("Sai kích thước")
                break
        rows.append({
            "name": name, "group": name.replace("\\", "/").split("/")[0], "path": path,
            "dimensions": dimensions, "bytes": size, "sha256": digest,
            "issues": issues, "notices": notices,
            "hash_verified": bool(digest and hashes and all(digest == h for h in hashes)),
            "status": " · ".join(issues or notices) if issues or notices else ("Khớp báo cáo" if hashes else "Chưa có hash đối chiếu"),
        })
    return rows


def inspect_report_bindings(root: Path, reports: Mapping[str, Any], *, story_bytes: bytes | None = None) -> list[dict[str, str]]:
    rows = []
    try:
        digest = hashlib.sha256(story_bytes).hexdigest() if story_bytes is not None else file_facts(root / "story.json")[0]
    except OSError:
        digest = ""
    for key in ("validation", "quality"):
        report = _object(reports.get(key))
        if not report:
            continue
        expected = report.get("story_sha256") if key == "validation" else _object(report.get("package_identity")).get("story_sha256")
        status = "Chưa xác minh" if not digest or not expected else ("Khớp kịch bản" if digest == expected else "Báo cáo đã cũ / khác kịch bản")
        rows.append({"report": key, "status": status})
    return rows


def render_project_assets(root: Path, reports: Mapping[str, Any]) -> None:
    import streamlit as st

    rows = inspect_project_assets(root, reports)
    history: dict[str, Any] = {"assets": {}}
    fingerprint = ""
    history_error = ""
    try:
        history = load_asset_history(root)
        fingerprint = content_fingerprint(root, reports)
    except (OSError, ValueError) as exc:
        history_error = str(exc)
        st.warning(history_error)
    with st.expander("Lịch sử kiểm tra ảnh", expanded=False):
        st.caption("Ghi nhận phiên bản tệp và nguồn nội dung tại thời điểm kiểm tra trên máy. Không xác nhận ảnh được tạo từ nguồn đó hoặc đạt yêu cầu nội dung/mỹ thuật.")
        note = st.text_input("Ghi chú lần kiểm tra", key="story_asset_inspection_note")
        if st.button("Kiểm tra và ghi nhận ảnh hiện tại", disabled=bool(history_error) or not rows):
            try:
                rows = inspect_project_assets(root, reports)
                fingerprint = content_fingerprint(root, reports)
                history = record_asset_observations(root, rows, fingerprint, note=note)
                st.success("Đã lưu lịch sử kiểm tra cục bộ. Gói truyện và ZIP chuẩn được giữ nguyên.")
            except (OSError, ValueError) as exc:
                st.warning(f"Chưa lưu được lịch sử ảnh: {exc}")
    st.caption("Kiểm tra tại máy: tệp, kích thước và SHA-256. Không thay thế đánh giá nội dung/mỹ thuật.")
    st.caption("Đủ file không đồng nghĩa đủ COMMITTED_ASSET. GENERATION_CALL (kể cả retry) khác ASSET_TRANSACTION; thiếu evidence thì chưa xác minh số commit.")
    group = st.selectbox("Nhóm tài nguyên", ["Tất cả", "characters", "landscape", "portrait"])
    only_issues = st.checkbox("Chỉ ảnh cần xem lại")
    records = history["assets"]
    visible = [r for r in rows if (group == "Tất cả" or r["group"] == group) and (
        not only_issues or r["issues"] or r["notices"] or not r["hash_verified"]
        or observation_status(r, records.get(r["name"], {}), fingerprint) != "Khớp lần ghi nhận")]
    st.dataframe([{
        "Tệp": r["name"], "Kích thước": "×".join(map(str, r["dimensions"])) if r["dimensions"] else "—",
        "Dung lượng (MiB)": round(r["bytes"] / 1024**2, 2), "Trạng thái": r["status"],
        "SHA-256": r["sha256"],
        "Phiên bản đã ghi": records.get(r["name"], {}).get("revision", 0),
        "Đối chiếu lịch sử": observation_status(r, records.get(r["name"], {}), fingerprint),
        "Kiểm tra gần nhất (UTC)": records.get(r["name"], {}).get("last_attempt", {}).get("at", "—"),
    } for r in visible], hide_index=True, width="stretch")
    if not visible:
        st.info("Không có ảnh trong bộ lọc này.")
        return
    selected = st.selectbox("Xem ảnh", [r["name"] for r in visible])
    row = next(r for r in visible if r["name"] == selected)
    recorded = records.get(selected, {})
    if recorded:
        with st.expander("Phiên bản và lần kiểm tra gần nhất của ảnh"):
            attempt = recorded.get("last_attempt", {})
            status_label = {"verified": "Khớp kiểm tra tệp/hash", "failed": "Kiểm tra tệp chưa đạt", "needs_review": "Cần đối chiếu thêm"}
            st.write(f"Kết quả: {status_label.get(attempt.get('status'), 'Chưa xác minh')}")
            st.caption(str(attempt.get("note") or "Chưa có ghi chú."))
            st.dataframe(recorded.get("revisions", []), hide_index=True, width="stretch")
    st.caption(str(row["path"] or selected))
    left, right = st.columns(2)
    frame_ratio = (16, 9) if row["group"] in {"landscape", "portrait"} else None
    with left:
        render_image_thumbnail(row["path"], caption=selected, key="asset_selected", frame_ratio=frame_ratio)
    if row["group"] in {"landscape", "portrait"}:
        counterpart = ("portrait" if row["group"] == "landscape" else "landscape") + "/" + Path(selected).name
        other = next((r for r in rows if r["name"] == counterpart), None)
        with right:
            counterpart_group = counterpart.split("/", 1)[0]
            stage_number = _object(reports.get("workflow")).get("stage")
            stage = f"STAGE{stage_number}" if type(stage_number) is int and stage_number in range(1, 5) else ""
            if counterpart_group not in stage_applicable_aspects(stage):
                st.info(f"{counterpart_group.title()} chưa áp dụng ở stage này.")
            else:
                render_image_thumbnail(other["path"] if other else None, caption=counterpart, key="asset_counterpart", frame_ratio=frame_ratio)
    with st.expander("Metadata / provenance nguồn"):
        st.caption("Metadata là khai báo gắn với ảnh, không tự chứng minh gate PASS. Giữ nguyên dữ liệu gốc để đối chiếu transaction/evidence.")
        try:
            if row["path"] is not None and row["path"].is_file():
                with Image.open(row["path"]) as picture:
                    metadata = {str(key): value if isinstance(value, (str, int, float, bool)) else f"<{type(value).__name__}>"
                                for key, value in picture.info.items()}
                if metadata:
                    st.json(metadata, expanded=False)
                else:
                    st.info("Không có metadata provenance để xem; không suy từ tên file hoặc kích thước.")
        except (OSError, ValueError, SyntaxError, UnidentifiedImageError) as exc:
            st.warning(f"Không đọc được metadata: {exc}")
