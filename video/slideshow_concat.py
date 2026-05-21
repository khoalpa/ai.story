from __future__ import annotations

from pathlib import Path
from typing import Optional


def escape_ffconcat_path(path: Path) -> str:
    """
    Escape path để ghi vào ffconcat list.
    Luôn resolve tuyệt đối để ffmpeg đọc đúng kể cả khi file .ffconcat nằm trong thư mục tạm.
    """
    s = str(path.resolve())
    s = s.replace("\r", "").replace("\n", "")
    s = s.replace("\\", "\\\\")
    s = s.replace("'", "\\'")
    return s


def estimate_slideshow_duration(
    image_count: int,
    duration_per_image: float,
    *,
    audio_duration: Optional[float] = None,
    match_audio: bool = True,
    audio_match_epsilon: float = 0.2,
) -> float:
    if image_count <= 0 or duration_per_image <= 0:
        return 0.0

    last_duration = duration_per_image
    if match_audio and audio_duration and audio_duration > 0 and image_count >= 1:
        base = duration_per_image * (image_count - 1)
        needed_last = (audio_duration - base) + max(0.0, audio_match_epsilon)
        if needed_last > last_duration:
            last_duration = needed_last
    return duration_per_image * (image_count - 1) + last_duration


def write_concat_list(
    images: list[Path],
    duration_per_image: float,
    out_list_file: Path,
    *,
    audio_duration: Optional[float] = None,
    match_audio: bool = True,
    audio_match_epsilon: float = 0.2,
) -> None:
    if duration_per_image <= 0:
        raise ValueError("--duration-per-image must be > 0")
    if not images:
        raise ValueError("At least 1 image is required to create an ffconcat list")

    last_duration = duration_per_image
    if match_audio and audio_duration and audio_duration > 0 and len(images) >= 1:
        base = duration_per_image * (len(images) - 1)
        needed_last = (audio_duration - base) + max(0.0, audio_match_epsilon)
        if needed_last > last_duration:
            last_duration = needed_last

    lines: list[str] = ["ffconcat version 1.0"]
    for img in images[:-1]:
        img_esc = escape_ffconcat_path(img)
        lines.append(f"file '{img_esc}'")
        lines.append(f"duration {duration_per_image:.6f}")

    last_img = images[-1]
    last_esc = escape_ffconcat_path(last_img)
    lines.append(f"file '{last_esc}'")
    lines.append(f"duration {last_duration:.6f}")
    lines.append(f"file '{last_esc}'")

    out_list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
