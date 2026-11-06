"""Runtime capability detection for Summary source ingestion."""
from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class SummaryCapabilities:
    pdf_text: bool
    pdf_render: bool
    image_ocr: bool
    scanned_pdf_ocr: bool
    pdftoppm_executable: str | None
    tesseract_executable: str | None


def detect_summary_capabilities() -> SummaryCapabilities:
    executable = shutil.which("tesseract")
    pdftoppm = shutil.which("pdftoppm")
    pdf_text = importlib.util.find_spec("pypdf") is not None
    return SummaryCapabilities(
        pdf_text=pdf_text,
        pdf_render=pdftoppm is not None,
        image_ocr=executable is not None,
        scanned_pdf_ocr=pdf_text and pdftoppm is not None and executable is not None,
        pdftoppm_executable=pdftoppm,
        tesseract_executable=executable,
    )


__all__ = ["SummaryCapabilities", "detect_summary_capabilities"]
