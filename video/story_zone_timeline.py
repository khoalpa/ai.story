from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Optional

from video.config import IMAGE_EXTENSIONS, ZONE_IMAGE_ALIASES, ZONE_IMAGE_SEQUENCE
from video.validation import collect_scene_images

STORY_ZONE_SEQUENCE: tuple[str, ...] = (
    "greeting",
    "opening",
    "introduction",
    "development",
    "climax",
    "falling",
    "ending",
    "farewell",
)

IMAGE_ZONE_TO_STORY_ZONE: dict[str, str] = {
    "intro_card": "greeting",
    "outro_card": "farewell",
}

ZONE_ALIASES: dict[str, tuple[str, ...]] = {
    "greeting": ("greeting", "loi chao"),
    "opening": ("opening", "intro", "mo truyen", "mo dau"),
    "introduction": ("introduction", "gioi thieu"),
    "development": ("development", "trien khai"),
    "climax": ("climax", "cao trao"),
    "falling": ("falling", "ha man"),
    "ending": ("ending", "ket truyen"),
    "farewell": ("farewell", "tam biet", "outro"),
}


@dataclass(frozen=True)
class SrtEntry:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class StoryZoneSegment:
    zone: str
    image: Path
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def _ascii_key(value: object) -> str:
    raw = "" if value is None else str(value)
    raw = raw.replace("Đ", "D").replace("đ", "d")
    normalized = unicodedata.normalize("NFKD", raw)
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    lowered = without_marks.casefold()
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def normalize_story_zone(value: object) -> Optional[str]:
    key = _ascii_key(value)
    if not key:
        return None
    for zone, aliases in ZONE_ALIASES.items():
        if key == zone or key in aliases:
            return zone
    for zone, aliases in ZONE_ALIASES.items():
        if any(alias in key for alias in aliases):
            return zone
    return None


def _image_alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for image_zone in ZONE_IMAGE_SEQUENCE:
        index[_ascii_key(image_zone)] = image_zone
        for alias in ZONE_IMAGE_ALIASES.get(image_zone, ()):
            index[_ascii_key(alias)] = image_zone
    return index


IMAGE_ALIAS_INDEX = _image_alias_index()


def normalize_image_zone_from_path(path: Path) -> Optional[str]:
    stem_key = _ascii_key(path.stem)
    if not stem_key:
        return None
    matched = IMAGE_ALIAS_INDEX.get(stem_key)
    if matched:
        return matched
    for alias, image_zone in IMAGE_ALIAS_INDEX.items():
        if stem_key.endswith(" " + alias) or stem_key.startswith(alias + " "):
            return image_zone
    return None


def _story_zone_for_image_zone(image_zone: str) -> str:
    return IMAGE_ZONE_TO_STORY_ZONE.get(image_zone, image_zone)


def collect_story_zone_images(scenes_dir: Path) -> dict[str, Path]:
    images = [p for p in collect_scene_images(scenes_dir) if p.suffix.lower() in IMAGE_EXTENSIONS]
    mapped: dict[str, Path] = {}
    for image in images:
        image_zone = normalize_image_zone_from_path(image)
        if image_zone is None:
            continue
        story_zone = _story_zone_for_image_zone(image_zone)
        if story_zone in STORY_ZONE_SEQUENCE:
            mapped.setdefault(story_zone, image)
    return mapped


def _parse_srt_timestamp(value: str) -> float:
    match = re.match(r"^\s*(\d+):(\d{2}):(\d{2})[,.](\d{1,3})\s*$", value)
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {value!r}")
    hours, minutes, seconds, millis = match.groups()
    millis = millis.ljust(3, "0")[:3]
    return (
        int(hours) * 3600.0
        + int(minutes) * 60.0
        + int(seconds)
        + int(millis) / 1000.0
    )


def parse_srt(path: Path) -> list[SrtEntry]:
    text = path.read_text(encoding="utf-8-sig")
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n").strip())
    entries: list[SrtEntry] = []
    for block in blocks:
        lines = [line.strip("\ufeff") for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        time_index = next((idx for idx, line in enumerate(lines) if "-->" in line), None)
        if time_index is None:
            continue
        start_raw, end_raw = [part.strip() for part in lines[time_index].split("-->", 1)]
        body = "\n".join(lines[time_index + 1 :]).strip()
        entries.append(
            SrtEntry(
                start=_parse_srt_timestamp(start_raw),
                end=_parse_srt_timestamp(end_raw),
                text=body,
            )
        )
    return entries


def load_story_script(story_json: Path) -> list[dict[str, Any]]:
    raw = json.loads(story_json.read_text(encoding="utf-8-sig"))
    script = raw.get("script") if isinstance(raw, dict) else None
    if not isinstance(script, list):
        raise ValueError(f"story.json must contain a script array: {story_json}")
    return [item for item in script if isinstance(item, dict)]


def _text_key(value: object) -> str:
    return _ascii_key(value)


def _match_script_to_srt(script: list[dict[str, Any]], entries: list[SrtEntry]) -> list[tuple[dict[str, Any], SrtEntry]]:
    if len(script) == len(entries):
        return list(zip(script, entries))

    unmatched_entries = list(entries)
    matched: list[tuple[dict[str, Any], SrtEntry]] = []
    for item in script:
        item_text = _text_key(item.get("text", ""))
        if not item_text:
            continue
        best_idx: Optional[int] = None
        best_score = 0.0
        for idx, entry in enumerate(unmatched_entries):
            entry_text = _text_key(entry.text)
            if not entry_text:
                continue
            if item_text in entry_text or entry_text in item_text:
                score = 1.0
            else:
                score = SequenceMatcher(a=item_text, b=entry_text).ratio()
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_idx is not None and best_score >= 0.78:
            matched.append((item, unmatched_entries.pop(best_idx)))
    return matched


def _iter_zone_ranges(
    script_srt_pairs: Iterable[tuple[dict[str, Any], SrtEntry]]
) -> list[tuple[str, float, float]]:
    ranges: dict[str, list[float]] = {}
    for item, entry in script_srt_pairs:
        zone = normalize_story_zone(item.get("zone"))
        if zone is None:
            continue
        if entry.end <= entry.start:
            continue
        current = ranges.setdefault(zone, [entry.start, entry.end])
        current[0] = min(current[0], entry.start)
        current[1] = max(current[1], entry.end)

    ordered: list[tuple[str, float, float]] = []
    for zone in STORY_ZONE_SEQUENCE:
        if zone not in ranges:
            continue
        start, end = ranges[zone]
        if end > start:
            ordered.append((zone, start, end))
    if ordered:
        adjusted: list[tuple[str, float, float]] = []
        for idx, (zone, start, end) in enumerate(ordered):
            if idx == 0:
                start = 0.0
            if idx + 1 < len(ordered):
                next_start = ordered[idx + 1][1]
                if next_start > end:
                    end = next_start
            adjusted.append((zone, start, end))
        ordered = adjusted
    return ordered


def build_story_zone_segments(
    *,
    story_json: Path,
    subtitle: Path,
    scenes_dir: Path,
) -> list[StoryZoneSegment]:
    script = load_story_script(story_json)
    entries = parse_srt(subtitle)
    if not entries:
        raise ValueError(f"No SRT entries found: {subtitle}")

    pairs = _match_script_to_srt(script, entries)
    if not pairs:
        raise ValueError("Could not match story.json script items to subtitle entries.")

    zone_ranges = _iter_zone_ranges(pairs)
    if not zone_ranges:
        raise ValueError(
            "Could not build zone timing from story.json and story.srt. "
            "Check that the SRT timestamps are not all zero."
        )

    image_by_zone = collect_story_zone_images(scenes_dir)
    if not image_by_zone:
        raise ValueError(f"No scene images matched story zones in: {scenes_dir}")

    segments: list[StoryZoneSegment] = []
    previous_image: Optional[Path] = None
    first_image = next(iter(image_by_zone.values()))
    for zone, start, end in zone_ranges:
        image = image_by_zone.get(zone) or previous_image or first_image
        segments.append(StoryZoneSegment(zone=zone, image=image, start=start, end=end))
        previous_image = image
    return segments


def estimate_story_zone_duration(segments: list[StoryZoneSegment]) -> float:
    if not segments:
        return 0.0
    return sum(segment.duration for segment in segments)
