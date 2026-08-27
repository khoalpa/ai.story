from __future__ import annotations

import base64
from pathlib import Path

FONT_ROOT = Path(__file__).resolve().parent / "assets" / "fonts"

STANDARD_FONTS = (
    "Arial",
    "Calibri",
    "Tahoma",
    "Verdana",
    "Trebuchet MS",
    "Times New Roman",
    "Georgia",
    "Courier New",
    "Noto Sans",
    "Noto Serif",
    "DejaVu Sans",
)

VIETNAMESE_HANDWRITING_FONTS = (
    "Playwrite VN",
    "Patrick Hand",
    "Mali",
)

ARTISTIC_FONTS = (
    "Dancing Script",
    "Pacifico",
    "Phudu",
)

FONT_CHOICES = STANDARD_FONTS + VIETNAMESE_HANDWRITING_FONTS + ARTISTIC_FONTS

BUNDLED_FONT_FILES = {
    "Playwrite VN": FONT_ROOT / "PlaywriteVN[wght].ttf",
    "Patrick Hand": FONT_ROOT / "PatrickHand-Regular.ttf",
    "Mali": FONT_ROOT / "Mali-Medium.ttf",
    "Dancing Script": FONT_ROOT / "DancingScript[wght].ttf",
    "Pacifico": FONT_ROOT / "Pacifico-Regular.ttf",
    "Phudu": FONT_ROOT / "Phudu[wght].ttf",
}

FONT_LICENSE_FILES = tuple(FONT_ROOT.glob("*/OFL.txt"))


def font_choice_label(font_name: str) -> str:
    if font_name in VIETNAMESE_HANDWRITING_FONTS:
        return f"Vietnamese handwriting · {font_name}"
    if font_name in ARTISTIC_FONTS:
        return f"Artistic (short subtitles) · {font_name}"
    return f"Standard · {font_name}"


def bundled_fonts_dir() -> Path | None:
    return FONT_ROOT if FONT_ROOT.is_dir() else None


def font_preview_css(font_name: str) -> str:
    font_file = BUNDLED_FONT_FILES.get(font_name)
    if font_file is None or not font_file.is_file():
        return ""
    encoded = base64.b64encode(font_file.read_bytes()).decode("ascii")
    family = font_name.replace("'", "\\'")
    return (
        f"@font-face{{font-family:'{family}';"
        f"src:url(data:font/ttf;base64,{encoded}) format('truetype');"
        "font-style:normal;font-weight:100 900;}}"
    )
