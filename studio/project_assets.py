"""Read-only asset inventory and exact-byte report binding checks."""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, UnidentifiedImageError

from studio.package_quality_report import _items, _object
from studio.prompt_contract import load_prompt_contract
from studio.story_images import (
    EXPECTED_IMAGE_STEMS,
    IMAGE_SUFFIXES,
    render_image_thumbnail,
)


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
    contract = load_prompt_contract()
    expected: dict[str, dict[str, Any]] = {}
    for group, expected_size in (("landscape", contract.landscape_size), ("portrait", contract.portrait_size)):
        for stem in EXPECTED_IMAGE_STEMS:
            expected[f"{group}/{stem}.png"] = {"dimensions": {"width": expected_size[0], "height": expected_size[1]}}
    for character in _items(_object(reports.get("story")).get("characters")):
        asset = _object(character.get("reference_asset"))
        name = str(asset.get("reference_image") or f"characters/{character.get('character_id', 'unknown')}.png")
        expected[name] = dict(asset)
    evidence = {
        str(row.get("path")): row
        for row in _items(_object(_object(reports.get("quality")).get("image_evidence")).get("asset_results"))
    }
    for name in evidence:
        expected.setdefault(name, {})
    for group in ("characters", "landscape", "portrait"):
        directory = root / group
        if directory.is_dir():
            for discovered in directory.iterdir():
                if discovered.is_file() and discovered.suffix.lower() in IMAGE_SUFFIXES:
                    expected.setdefault(f"{group}/{discovered.name}", {})
    rows = []
    for name, declared in expected.items():
        path = project_asset_path(root, name)
        issues: list[str] = []
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
        except (OSError, ValueError, UnidentifiedImageError):
            issues.append("Không đọc được ảnh")
        bindings = [declared, evidence.get(name, {})]
        hashes = [a.get("file_sha256") for a in bindings if a.get("file_sha256")]
        if digest and any(digest != h for h in hashes):
            issues.append("Hash không khớp báo cáo")
        for binding in bindings:
            target = _object(binding.get("dimensions"))
            if dimensions and target and dimensions != (target.get("width"), target.get("height")):
                issues.append("Sai kích thước")
                break
        rows.append({
            "name": name, "group": name.replace("\\", "/").split("/")[0], "path": path,
            "dimensions": dimensions, "bytes": size, "sha256": digest,
            "issues": issues, "hash_verified": bool(digest and hashes and all(digest == h for h in hashes)),
            "status": " · ".join(issues) if issues else ("Khớp báo cáo" if hashes else "Chưa có hash đối chiếu"),
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
    st.caption("Kiểm tra tại máy: tệp, kích thước và SHA-256. Không thay thế đánh giá nội dung/mỹ thuật.")
    group = st.selectbox("Nhóm tài nguyên", ["Tất cả", "characters", "landscape", "portrait"])
    only_issues = st.checkbox("Chỉ ảnh cần xem lại")
    visible = [r for r in rows if (group == "Tất cả" or r["group"] == group) and (not only_issues or r["issues"] or not r["hash_verified"])]
    st.dataframe([{
        "Tệp": r["name"], "Kích thước": "×".join(map(str, r["dimensions"])) if r["dimensions"] else "—",
        "Dung lượng (MiB)": round(r["bytes"] / 1024**2, 2), "Trạng thái": r["status"],
        "SHA-256": r["sha256"],
    } for r in visible], hide_index=True, width="stretch")
    if not visible:
        st.info("Không có ảnh trong bộ lọc này.")
        return
    selected = st.selectbox("Xem ảnh", [r["name"] for r in visible])
    row = next(r for r in visible if r["name"] == selected)
    st.caption(str(row["path"] or selected))
    left, right = st.columns(2)
    frame_ratio = (16, 9) if row["group"] in {"landscape", "portrait"} else None
    with left:
        render_image_thumbnail(row["path"], caption=selected, key="asset_selected", frame_ratio=frame_ratio)
    if row["group"] in {"landscape", "portrait"}:
        counterpart = ("portrait" if row["group"] == "landscape" else "landscape") + "/" + Path(selected).name
        other = next((r for r in rows if r["name"] == counterpart), None)
        with right:
            render_image_thumbnail(other["path"] if other else None, caption=counterpart, key="asset_counterpart", frame_ratio=frame_ratio)
