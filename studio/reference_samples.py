"""Pinned reference archives shared by Studio, tests and repository CI."""
from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path
from typing import Any

from studio.prompt_contract import PROJECT_ROOT
from studio.workflow_package import MAX_PACKAGE_BYTES, inspect_members, read_archive

REFERENCE_PACKAGE_DIRECTORY = PROJECT_ROOT / "samples" / "Tiem_Sua_Nhung_Loi_Hua"
REFERENCE_PACKAGE_STAGES = {
    "story_stage1.zip": "STAGE1",
    "story_stage2.zip": "STAGE2",
    "story.zip": "STAGE3",
    "story_video_prompts.zip": "STAGE4",
}
REFERENCE_PACKAGE_NAMES = tuple(REFERENCE_PACKAGE_STAGES)
REFERENCE_CHECKSUM_FILE = "SHA256SUMS"


def reference_checksums(directory: Path = REFERENCE_PACKAGE_DIRECTORY) -> dict[str, str]:
    """Require one pinned digest for each named archive, with no duplicate entries."""
    path = directory / REFERENCE_CHECKSUM_FILE
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"Thiếu danh sách checksum mẫu: {path}. Cần lấy đủ bộ samples từ repository.") from exc
    hashes: dict[str, str] = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+\.zip)", line)
        if match is None or match[2] in hashes:
            raise ValueError(f"Danh sách checksum mẫu không hợp lệ hoặc trùng tên: {path}.")
        hashes[match[2]] = match[1]
    if set(hashes) != set(REFERENCE_PACKAGE_NAMES):
        raise ValueError(f"{path} phải khai báo đúng bốn ZIP mẫu hiện hành.")
    return hashes


def load_reference_package(
    name: str, directory: Path = REFERENCE_PACKAGE_DIRECTORY,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    """Verify exact archive bytes and the existing production contract before use."""
    if name not in REFERENCE_PACKAGE_STAGES:
        raise ValueError(f"Không có gói mẫu chuẩn mang tên {name!r}.")
    expected = reference_checksums(directory)[name]
    path = directory / name
    try:
        if path.stat().st_size > MAX_PACKAGE_BYTES:
            raise ValueError(f"ZIP mẫu vượt giới hạn dung lượng: {path}.")
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"Không đọc được ZIP mẫu: {path}. Cần lấy đủ bộ samples từ repository.") from exc
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f"Checksum ZIP mẫu không khớp: {path}. Không dùng dữ liệu đã thay đổi hoặc tải thiếu.")
    try:
        members = read_archive(raw)
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise ValueError(f"ZIP mẫu không đọc được: {path}: {exc}") from exc
    result = inspect_members(members, archive=True)
    if result.get("status") != "PASS" or result.get("stage") != REFERENCE_PACKAGE_STAGES[name]:
        details = "; ".join(str(row.get("detail") or row.get("check")) for row in result.get("checks", [])
                            if row.get("status") != "PASS")
        raise ValueError(f"ZIP mẫu {path} không đạt hợp đồng {REFERENCE_PACKAGE_STAGES[name]}: {details}")
    return members, result
