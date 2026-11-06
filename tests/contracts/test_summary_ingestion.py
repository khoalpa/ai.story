from __future__ import annotations

import json
import zipfile
from io import BytesIO
from types import SimpleNamespace

from pypdf import PdfWriter

from studio.summary_capabilities import SummaryCapabilities
from studio.summary_ingestion import build_summary_draft, extract_source
from studio.summary_schema import validate_summary_document


def _docx_bytes() -> bytes:
    payload = BytesIO()
    xml = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body><w:p><w:r><w:t>Doan van thu nhat.</w:t></w:r></w:p>
      <w:p><w:r><w:t>Doan van thu hai co them du lieu.</w:t></w:r></w:p></w:body>
    </w:document>'''
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return payload.getvalue()


def test_extract_text_docx_subtitles_and_transcript_json() -> None:
    text = extract_source("book.txt", b"Doan mot co noi dung.\n\nDoan hai co bang chung.")
    docx = extract_source("report.docx", _docx_bytes())
    srt = extract_source("talk.srt", b"1\n00:00:01,000 --> 00:00:03,500\nXin chao moi nguoi.\n")
    transcript = extract_source(
        "talk.json",
        json.dumps({"segments": [{"start": 0.0, "end": 1.25, "text": "Mo dau."}]}).encode(),
    )

    assert text.extraction_method == "DIRECT_TEXT" and text.blocks
    assert docx.extraction_method == "DOCX_XML" and docx.blocks
    assert srt.blocks[0].timestamp_start_ms == 1000
    assert srt.blocks[0].timestamp_end_ms == 3500
    assert transcript.blocks[0].timestamp_end_ms == 1250


def test_build_summary_draft_is_valid_and_traceable() -> None:
    source = extract_source(
        "source.md",
        "Tài liệu xác định vấn đề và thu thập bằng chứng.\n\nSau đó tài liệu kiểm tra giả định và đánh giá kết quả.".encode("utf-8"),
    )
    draft = build_summary_draft([source])

    assert validate_summary_document(draft) == []
    assert draft["sources"][0]["sha256"] == source.sha256
    assert draft["claims"][0]["locator_ids"] == ["loc_0001"]
    assert draft["limitations"]


def test_extract_source_rejects_unsupported_or_empty_input() -> None:
    for name, raw in (("empty.txt", b""), ("archive.bin", b"not empty")):
        try:
            extract_source(name, raw)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{name} phải bị từ chối")


def test_scanned_pdf_uses_page_render_and_tesseract(monkeypatch) -> None:
    payload = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(payload)
    capability = SummaryCapabilities(
        pdf_text=True, pdf_render=True, image_ocr=True, scanned_pdf_ocr=True,
        pdftoppm_executable="pdftoppm", tesseract_executable="tesseract",
    )
    monkeypatch.setattr("studio.summary_ingestion.detect_summary_capabilities", lambda: capability)

    def fake_run(command, **_kwargs):
        if command[0] == "pdftoppm":
            from pathlib import Path
            Path(command[-1]).with_suffix(".png").write_bytes(b"synthetic png")
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        return SimpleNamespace(returncode=0, stdout="Nội dung OCR của trang scan.".encode(), stderr=b"")

    monkeypatch.setattr("studio.summary_ingestion.subprocess.run", fake_run)
    source = extract_source("scan.pdf", payload.getvalue(), ocr_language="vie")

    assert source.extraction_method == "PDF_TEXT_OCR"
    assert source.blocks[0].page == 1
    assert "Nội dung OCR" in source.blocks[0].text
