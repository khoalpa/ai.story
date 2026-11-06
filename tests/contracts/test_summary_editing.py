from __future__ import annotations

import pytest

from studio.summary_capabilities import detect_summary_capabilities
from studio.summary_editing import replace_summary_rows, update_summary_meta
from studio.summary_schema import validate_summary_document
from tests.contracts.test_summary_projection import summary_fixture


def test_metadata_edit_is_validated_and_does_not_mutate_source() -> None:
    source = summary_fixture()
    updated = update_summary_meta(source, {"title": "Tiêu đề mới", "image_mode": "ZONE"})

    assert updated["meta"]["title"] == "Tiêu đề mới"
    assert updated["meta"]["image_mode"] == "ZONE"
    assert source["meta"]["title"] == "Bản tóm tắt kiểm thử"
    assert validate_summary_document(updated) == []


def test_table_edit_rejects_broken_references_without_mutating_source() -> None:
    source = summary_fixture()
    broken = [dict(source["claims"][0], locator_ids=["loc_9999"])]

    with pytest.raises(ValueError, match="locator_ids"):
        replace_summary_rows(source, "claims", broken)
    assert source["claims"][0]["locator_ids"] == ["loc_0001"]


def test_narration_edit_is_validated() -> None:
    source = summary_fixture()
    rows = [dict(source["narration"][0], text="Lời đọc đã được chỉnh sửa nhưng vẫn giữ claim hợp lệ.")]
    updated = replace_summary_rows(source, "narration", rows)

    assert updated["narration"][0]["text"].startswith("Lời đọc")
    assert source["narration"][0]["text"] != updated["narration"][0]["text"]


def test_capability_detection_returns_stable_shape() -> None:
    capability = detect_summary_capabilities()

    assert isinstance(capability.pdf_text, bool)
    assert isinstance(capability.pdf_render, bool)
    assert isinstance(capability.image_ocr, bool)
    assert capability.image_ocr is (capability.tesseract_executable is not None)
    assert capability.pdf_render is (capability.pdftoppm_executable is not None)
    assert capability.scanned_pdf_ocr is (
        capability.pdf_text and capability.pdf_render and capability.image_ocr
    )
