"""Audio-first speech timing checks for generated video prompt plans."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


_TIMESTAMP = re.compile(
    r"^(?P<hours>\d{2}):(?P<minutes>\d{2}):(?P<seconds>\d{2})[,.](?P<millis>\d{3})$"
)


@dataclass(frozen=True)
class SubtitleCue:
    start_seconds: float
    end_seconds: float
    text: str

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


def _seconds(value: str) -> float:
    match = _TIMESTAMP.fullmatch(value.strip())
    if match is None:
        raise ValueError(f"Timestamp SRT không hợp lệ: {value!r}")
    parts = {name: int(number) for name, number in match.groupdict().items()}
    return (
        parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
        + parts["millis"] / 1000
    )


def parse_srt(text: str) -> list[SubtitleCue]:
    """Parse ordinary SRT cues without depending on an optional subtitle package."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    cues: list[SubtitleCue] = []
    for block in re.split(r"\n{2,}", normalized):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None or timing_index + 1 >= len(lines):
            continue
        start_raw, end_raw = (part.strip() for part in lines[timing_index].split("-->", 1))
        start, end = _seconds(start_raw), _seconds(end_raw)
        if end <= start:
            raise ValueError("Cue SRT phải có thời lượng dương")
        cues.append(SubtitleCue(start, end, " ".join(lines[timing_index + 1 :])))
    return cues


def normalize_speech_text(text: str) -> str:
    """Normalize typography and whitespace while preserving the spoken wording."""
    value = unicodedata.normalize("NFC", text)
    value = value.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"}))
    return " ".join(value.split()).strip()


def required_container_duration(
    speech_duration_seconds: float,
    allowed_durations: Iterable[int],
    *,
    safety_margin_seconds: float = 0.5,
) -> int | None:
    """Return the smallest provider container that safely holds measured speech."""
    required = speech_duration_seconds + safety_margin_seconds
    return next((duration for duration in sorted(set(allowed_durations)) if duration >= required), None)


def _clip_text(clip: Mapping[str, Any]) -> str:
    voice_plan = clip.get("voice_plan")
    segments = voice_plan.get("segments") if isinstance(voice_plan, dict) else None
    if not isinstance(segments, list):
        return ""
    return normalize_speech_text(
        " ".join(str(segment.get("text", "")) for segment in segments if isinstance(segment, dict))
    )


def speech_timing_preflight(
    clips: Sequence[Any],
    subtitle_text: str,
    allowed_durations: Iterable[int],
    *,
    safety_margin_seconds: float = 0.5,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Compare exact planned speech with measured SRT cues in source order."""
    cues = parse_srt(subtitle_text)
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    cursor = 0
    for position, raw_clip in enumerate(clips, 1):
        if not isinstance(raw_clip, dict) or not raw_clip.get("voice_plan"):
            continue
        clip_id = str(raw_clip.get("clip_id", f"clip_{position:04d}"))
        planned_text = _clip_text(raw_clip)
        match_index = next(
            (index for index in range(cursor, len(cues))
             if normalize_speech_text(cues[index].text) == planned_text),
            None,
        )
        if match_index is None:
            errors.append(f"{clip_id}: SPEECH_TIMING_NOT_FOUND trong story.srt.")
            continue
        cursor = match_index + 1
        cue = cues[match_index]
        measured = round(cue.duration_seconds, 3)
        recommended = required_container_duration(
            measured, allowed_durations, safety_margin_seconds=safety_margin_seconds
        )
        planned = raw_clip.get("duration_seconds")
        rows.append({
            "clip_id": clip_id,
            "speech_duration_seconds": measured,
            "safety_margin_seconds": safety_margin_seconds,
            "planned_duration_seconds": planned,
            "recommended_duration_seconds": recommended,
        })
        if recommended is None:
            errors.append(
                f"{clip_id}: SPEECH_REQUIRES_SEGMENTATION — thoại {measured:.3f}s + "
                f"đệm {safety_margin_seconds:.3f}s vượt container lớn nhất."
            )
        elif type(planned) not in {int, float} or float(planned) < measured + safety_margin_seconds:
            errors.append(
                f"{clip_id}: SPEECH_DOES_NOT_FIT_CONTAINER — thoại {measured:.3f}s + "
                f"đệm {safety_margin_seconds:.3f}s cần container {recommended}s, hiện là {planned}s."
            )
    return errors, rows


__all__ = [
    "SubtitleCue",
    "normalize_speech_text",
    "parse_srt",
    "required_container_duration",
    "speech_timing_preflight",
]
