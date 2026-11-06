"""Deterministic local source extraction and canonical Summary draft creation."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree

from studio.summary_capabilities import detect_summary_capabilities
from studio.summary_schema import validate_summary_document

MAX_SOURCE_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_CHARS = 5_000_000


@dataclass(frozen=True)
class ExtractedBlock:
    label: str
    text: str
    kind: str = "TEXT_OFFSET"
    page: int | None = None
    section: str | None = None
    timestamp_start_ms: int | None = None
    timestamp_end_ms: int | None = None


@dataclass(frozen=True)
class ExtractedSource:
    name: str
    mime_type: str
    size_bytes: int
    sha256: str
    extraction_method: str
    blocks: tuple[ExtractedBlock, ...]
    warnings: tuple[str, ...] = ()


def _clean_text(value: str) -> str:
    text = value.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def _paragraph_blocks(text: str, *, max_chars: int = 4_000) -> tuple[ExtractedBlock, ...]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", _clean_text(text)) if part.strip()]
    blocks: list[ExtractedBlock] = []
    buffer: list[str] = []
    length = 0
    for paragraph in paragraphs:
        if buffer and length + len(paragraph) + 2 > max_chars:
            blocks.append(ExtractedBlock(f"Khối {len(blocks) + 1}", "\n\n".join(buffer)))
            buffer, length = [], 0
        buffer.append(paragraph)
        length += len(paragraph) + 2
    if buffer:
        blocks.append(ExtractedBlock(f"Khối {len(blocks) + 1}", "\n\n".join(buffer)))
    return tuple(blocks)


def _extract_docx(raw: bytes) -> tuple[ExtractedBlock, ...]:
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        info = archive.getinfo("word/document.xml")
        if info.file_size > MAX_EXTRACTED_CHARS * 4:
            raise ValueError("DOCX document.xml vượt giới hạn")
        root = ElementTree.fromstring(archive.read(info))
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(namespace + "p"):
        text = "".join(node.text or "" for node in paragraph.iter(namespace + "t")).strip()
        if text:
            paragraphs.append(text)
    return _paragraph_blocks("\n\n".join(paragraphs))


def _run_tesseract(source: Path, language: str | None) -> str:
    capability = detect_summary_capabilities()
    if not capability.image_ocr or capability.tesseract_executable is None:
        raise ValueError("OCR cần Tesseract trong PATH")
    command = [capability.tesseract_executable, str(source), "stdout"]
    if language:
        command.extend(["-l", language])
    completed = subprocess.run(command, capture_output=True, timeout=120, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"Tesseract OCR thất bại: {detail or completed.returncode}")
    return completed.stdout.decode("utf-8", errors="strict")


def _extract_pdf(raw: bytes, language: str | None) -> tuple[tuple[ExtractedBlock, ...], str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError("Đọc PDF cần cài dependency pypdf") from exc
    reader = PdfReader(BytesIO(raw))
    blocks, used_ocr = [], False
    capability = detect_summary_capabilities()
    with tempfile.TemporaryDirectory(prefix="ai-summary-pdf-") as temporary:
        pdf_path = Path(temporary) / "source.pdf"
        pdf_path.write_bytes(raw)
        for index, page in enumerate(reader.pages, 1):
            text = _clean_text(page.extract_text() or "")
            if not text and capability.scanned_pdf_ocr:
                assert capability.pdftoppm_executable is not None
                prefix = Path(temporary) / f"page-{index:04d}"
                completed = subprocess.run(
                    [capability.pdftoppm_executable, "-f", str(index), "-l", str(index),
                     "-r", "200", "-png", "-singlefile", str(pdf_path), str(prefix)],
                    capture_output=True, timeout=120, check=False,
                )
                rendered = prefix.with_suffix(".png")
                if completed.returncode != 0 or not rendered.is_file():
                    detail = completed.stderr.decode("utf-8", errors="replace").strip()
                    raise ValueError(f"Render PDF trang {index} thất bại: {detail or completed.returncode}")
                text = _clean_text(_run_tesseract(rendered, language))
                used_ocr = bool(text) or used_ocr
            if text:
                blocks.append(ExtractedBlock(f"Trang {index}", text, kind="PDF_PAGE", page=index))
    method = "PDF_TEXT_OCR" if used_ocr else "PDF_TEXT"
    return tuple(blocks), method


def _timestamp_ms(value: str) -> int:
    parts = value.strip().replace(",", ".").split(":")
    if len(parts) == 2:
        hours, minutes, seconds = 0, int(parts[0]), float(parts[1])
    elif len(parts) == 3:
        hours, minutes, seconds = int(parts[0]), int(parts[1]), float(parts[2])
    else:
        raise ValueError(f"Timestamp không hợp lệ: {value}")
    return round((hours * 3600 + minutes * 60 + seconds) * 1000)


def _extract_subtitles(text: str) -> tuple[ExtractedBlock, ...]:
    normalized = _clean_text(text)
    chunks = re.split(r"\n\s*\n", normalized)
    blocks: list[ExtractedBlock] = []
    pattern = re.compile(r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?[,.]\d{3})\s*-->\s*(?P<end>\d{1,2}:\d{2}(?::\d{2})?[,.]\d{3})")
    for chunk in chunks:
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        timing_index = next((i for i, line in enumerate(lines) if pattern.search(line)), None)
        if timing_index is None:
            continue
        match = pattern.search(lines[timing_index])
        assert match is not None
        cue = " ".join(lines[timing_index + 1:]).strip()
        if cue:
            blocks.append(ExtractedBlock(
                f"Cue {len(blocks) + 1}", cue, kind="TIMESTAMP",
                timestamp_start_ms=_timestamp_ms(match.group("start")),
                timestamp_end_ms=_timestamp_ms(match.group("end")),
            ))
    return tuple(blocks)


def _extract_transcript_json(raw: bytes) -> tuple[ExtractedBlock, ...]:
    value = json.loads(raw.decode("utf-8-sig"))
    rows = value.get("segments") if isinstance(value, dict) else value
    if not isinstance(rows, list):
        raise ValueError("Transcript JSON cần root array hoặc field segments")
    blocks = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or not isinstance(row.get("text"), str) or not row["text"].strip():
            continue
        start, end = row.get("start_ms"), row.get("end_ms")
        if start is None and isinstance(row.get("start"), (int, float)):
            start = round(float(row["start"]) * 1000)
        if end is None and isinstance(row.get("end"), (int, float)):
            end = round(float(row["end"]) * 1000)
        kind = "TIMESTAMP" if type(start) is int and type(end) is int and 0 <= start < end else "OTHER"
        blocks.append(ExtractedBlock(
            f"Segment {index}", _clean_text(row["text"]), kind=kind,
            timestamp_start_ms=start if kind == "TIMESTAMP" else None,
            timestamp_end_ms=end if kind == "TIMESTAMP" else None,
        ))
    return tuple(blocks)


def _extract_image_ocr(raw: bytes, suffix: str, language: str | None) -> tuple[ExtractedBlock, ...]:
    capability = detect_summary_capabilities()
    if not capability.image_ocr or capability.tesseract_executable is None:
        raise ValueError("OCR ảnh cần Tesseract trong PATH")
    with tempfile.TemporaryDirectory(prefix="ai-summary-ocr-") as temporary:
        source = Path(temporary) / f"source{suffix}"
        source.write_bytes(raw)
        text = _run_tesseract(source, language)
    return _paragraph_blocks(text)


def extract_source(
    name: str, raw: bytes, mime_type: str | None = None, *, ocr_language: str | None = None,
) -> ExtractedSource:
    if not raw or len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("Nguồn rỗng hoặc vượt giới hạn 50 MiB")
    suffix = Path(name).suffix.casefold()
    mime = mime_type or {
        ".txt": "text/plain", ".md": "text/markdown", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pdf": "application/pdf", ".srt": "application/x-subrip", ".vtt": "text/vtt", ".json": "application/json",
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".tif": "image/tiff", ".tiff": "image/tiff",
    }.get(suffix, "application/octet-stream")
    if suffix in {".txt", ".md"}:
        blocks, method = _paragraph_blocks(raw.decode("utf-8-sig")), "DIRECT_TEXT"
    elif suffix == ".docx":
        blocks, method = _extract_docx(raw), "DOCX_XML"
    elif suffix == ".pdf":
        blocks, method = _extract_pdf(raw, ocr_language)
    elif suffix in {".srt", ".vtt"}:
        blocks, method = _extract_subtitles(raw.decode("utf-8-sig")), "SUBTITLE_CUES"
    elif suffix == ".json":
        blocks, method = _extract_transcript_json(raw), "TRANSCRIPT_JSON"
    elif suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        blocks, method = _extract_image_ocr(raw, suffix, ocr_language), "TESSERACT_OCR"
    else:
        raise ValueError(f"Loại nguồn chưa hỗ trợ: {suffix or name}")
    if not blocks:
        raise ValueError("Không trích xuất được nội dung chữ từ nguồn")
    if sum(len(block.text) for block in blocks) > MAX_EXTRACTED_CHARS:
        raise ValueError("Nội dung trích xuất vượt giới hạn 5 triệu ký tự")
    return ExtractedSource(name, mime, len(raw), hashlib.sha256(raw).hexdigest(), method, blocks)


def _extractive_summary(text: str, limit: int = 500) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?…])\s+", compact)
    selected = " ".join(sentences[:2]).strip()
    if len(selected) <= limit:
        return selected
    return selected[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def build_summary_draft(sources: Iterable[ExtractedSource], *, language: str = "vi") -> dict[str, Any]:
    extracted = tuple(sources)
    if not extracted:
        raise ValueError("Cần ít nhất một nguồn đã trích xuất")
    source_rows: list[dict[str, Any]] = []
    locators: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    narration: list[dict[str, Any]] = []
    for source_index, source in enumerate(extracted, 1):
        source_id = f"src_{source_index:03d}"
        source_rows.append({
            "source_id": source_id, "title": Path(source.name).stem, "type": Path(source.name).suffix.lstrip(".").upper() or "TEXT",
            "version": None, "authors": [], "published_at": None, "publisher": None, "url": None, "accessed_at": None,
            "mime_type": source.mime_type, "size_bytes": source.size_bytes, "sha256": source.sha256,
            "extraction_method": source.extraction_method, "ocr_status": "NOT_APPLICABLE", "scope_read": "Toàn bộ nội dung trích xuất",
        })
        for block in source.blocks:
            sequence = len(sections) + 1
            locator_id, section_id, claim_id = f"loc_{sequence:04d}", f"section_{sequence:03d}", f"claim_{sequence:04d}"
            locators.append({
                "locator_id": locator_id, "source_id": source_id, "kind": block.kind, "label": block.label,
                "page": block.page, "section": block.section, "start_char": None, "end_char": None,
                "timestamp_start_ms": block.timestamp_start_ms, "timestamp_end_ms": block.timestamp_end_ms,
            })
            summary = _extractive_summary(block.text)
            sections.append({"section_id": section_id, "source_id": source_id, "locator_ids": [locator_id],
                             "summary": summary, "key_points": [summary], "uncertainties": []})
            claims.append({"claim_id": claim_id, "statement": summary, "claim_type": "SOURCE",
                           "source_ids": [source_id], "locator_ids": [locator_id], "confidence": "UNKNOWN",
                           "included_in_summary": True})
            narration.append({"narration_id": f"narration_{sequence:04d}", "section_id": section_id,
                              "text": summary, "claim_ids": [claim_id]})
    document = {
        "schema_version": "1.1.0", "prompt_version": "1.4.0",
        "meta": {"title": "Bản nháp tóm tắt", "output_type": "SUMMARY_ANALYSIS", "source_genre": "MIXED",
                 "style": "NEUTRAL_CLEAR", "audience": "Người trưởng thành phổ thông", "language": language,
                 "target_words": None, "target_minutes": None, "image_mode": "SCENE", "coverage": "FULL_SUMMARY",
                 "citation_style": "MARKDOWN", "scene_density_seconds": 30, "max_scenes": 30},
        "sources": source_rows, "locators": locators, "sections": sections, "claims": claims,
        "claim_relations": [], "numeric_facts": [], "glossary": [], "narration": narration,
        "limitations": ["Bản nháp trích xuất tự động; cần biên tập và kiểm tra độ trung thành trước khi COMPLETE."],
    }
    errors = validate_summary_document(document)
    if errors:
        raise ValueError("Không tạo được draft hợp lệ: " + "; ".join(errors))
    return document


__all__ = ["ExtractedBlock", "ExtractedSource", "build_summary_draft", "extract_source"]
