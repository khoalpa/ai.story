from __future__ import annotations

from pathlib import Path


def seconds_to_srt_timestamp(t: float) -> str:
    total_ms = int(round(max(0.0, t) * 1000))
    hours = total_ms // 3_600_000
    total_ms %= 3_600_000
    minutes = total_ms // 60_000
    total_ms %= 60_000
    seconds = total_ms // 1000
    millis = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def write_srt_from_timeline(timeline: list[dict], srt_path: Path) -> None:
    with srt_path.open("w", encoding="utf-8") as srt_f:
        for i, item in enumerate(timeline, start=1):
            srt_f.write(f"{i}\n")
            srt_f.write(
                f"{seconds_to_srt_timestamp(item['start'])} --> {seconds_to_srt_timestamp(item['end'])}\n"
            )
            srt_f.write(item["text"].strip() + "\n\n")
