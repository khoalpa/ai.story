from __future__ import annotations

from pathlib import Path
from typing import Optional

from video.story_zone_timeline import StoryZoneSegment


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


def build_slideshow_segments(
    images: list[Path],
    duration_per_image: float,
    *,
    audio_duration: Optional[float] = None,
    match_audio: bool = True,
    audio_match_epsilon: float = 0.2,
) -> list[StoryZoneSegment]:
    """Build the existing fixed-duration slideshow as an explicit timeline."""
    if duration_per_image <= 0:
        raise ValueError("--duration-per-image must be > 0")
    if not images:
        raise ValueError("At least 1 image is required to create a slideshow timeline")

    total_duration = estimate_slideshow_duration(
        len(images),
        duration_per_image,
        audio_duration=audio_duration,
        match_audio=match_audio,
        audio_match_epsilon=audio_match_epsilon,
    )
    segments: list[StoryZoneSegment] = []
    for index, image in enumerate(images):
        start = index * duration_per_image
        end = total_duration if index == len(images) - 1 else min(
            total_duration, (index + 1) * duration_per_image
        )
        if end > start:
            segments.append(
                StoryZoneSegment(
                    zone=f"scene_{index + 1}",
                    image=image,
                    start=start,
                    end=end,
                )
            )
    return segments


def prepend_cover_segment(
    segments: list[StoryZoneSegment],
    cover: Optional[Path],
    cover_duration: float,
) -> list[StoryZoneSegment]:
    """Show cover from t=0 while preserving the original timeline end."""
    if cover is None:
        return list(segments)
    if cover_duration <= 0:
        raise ValueError("cover_duration must be > 0")
    if not segments:
        return []

    timeline_end = max(segment.end for segment in segments)
    cover_end = min(float(cover_duration), timeline_end)
    if cover_end <= 0:
        return list(segments)

    result = [StoryZoneSegment(zone="cover", image=cover, start=0.0, end=cover_end)]
    for segment in segments:
        if segment.end <= cover_end:
            continue
        result.append(
            StoryZoneSegment(
                zone=segment.zone,
                image=segment.image,
                start=max(segment.start, cover_end),
                end=segment.end,
            )
        )
    return result


def append_outro_segment(
    segments: list[StoryZoneSegment],
    outro: Optional[Path],
    outro_duration: float,
) -> list[StoryZoneSegment]:
    """Show an end screen at the tail while preserving the timeline duration."""
    if outro is None:
        return list(segments)
    if outro_duration <= 0:
        raise ValueError("outro_duration must be > 0")
    if not segments:
        return []

    timeline_end = max(segment.end for segment in segments)
    outro_start = max(0.0, timeline_end - float(outro_duration))
    if timeline_end <= outro_start:
        return list(segments)

    result: list[StoryZoneSegment] = []
    for segment in segments:
        if segment.start >= outro_start:
            continue
        result.append(
            StoryZoneSegment(
                zone=segment.zone,
                image=segment.image,
                start=segment.start,
                end=min(segment.end, outro_start),
            )
        )
    result.append(
        StoryZoneSegment(
            zone="end_screen",
            image=outro,
            start=outro_start,
            end=timeline_end,
        )
    )
    return result


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


def write_timeline_concat_list(
    segments: list[StoryZoneSegment],
    out_list_file: Path,
) -> None:
    if not segments:
        raise ValueError("At least 1 timeline segment is required to create an ffconcat list")

    lines: list[str] = ["ffconcat version 1.0"]
    for segment in segments:
        if segment.duration <= 0:
            continue
        img_esc = escape_ffconcat_path(segment.image)
        lines.append(f"file '{img_esc}'")
        lines.append(f"duration {segment.duration:.6f}")

    if len(lines) <= 1:
        raise ValueError("Timeline segments did not contain any positive durations")

    last_esc = escape_ffconcat_path(segments[-1].image)
    lines.append(f"file '{last_esc}'")
    out_list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
