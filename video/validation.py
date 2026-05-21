from __future__ import annotations

from pathlib import Path

from video.config import IMAGE_EXTENSIONS, ZONE_IMAGE_ALIASES, ZONE_IMAGE_SEQUENCE


def autodetect_subtitle_from_audio(audio: Path | None):
    if audio is None:
        return None

    try:
        audio = Path(audio)
    except TypeError:
        return None

    raw = str(audio).strip()

    # Chặn các path rỗng / "." / thư mục / path không có tên file
    if not raw or raw == "." or audio.name in ("", "."):
        return None

    try:
        for candidate in (audio.with_suffix(".srt"), audio.with_suffix(".ass")):
            if candidate.is_file():
                return candidate
    except ValueError:
        return None

    return None


def validate_static_inputs(audio: Path | None, cover: Path | None) -> None:
    if audio is None:
        raise ValueError("Audio file cannot be empty.")
    if cover is None:
        raise ValueError("Static mode needs a cover image or an asset profile with default_cover.")
    if not cover.is_file():
        raise FileNotFoundError(f"Cover image not found: {cover}")
    if not audio.is_file():
        raise FileNotFoundError(f"Audio not found: {audio}")


def _normalize_scene_stem(value: str) -> str:
    stem = value.strip().lower()
    for old, new in (("-", "_"), (" ", "_"), ("__", "_")):
        while old in stem:
            stem = stem.replace(old, new)
    return stem.strip("_")


def _build_scene_alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for scene_key in ZONE_IMAGE_SEQUENCE:
        index[_normalize_scene_stem(scene_key)] = scene_key
        for alias in ZONE_IMAGE_ALIASES.get(scene_key, ()):  # pragma: no branch
            index[_normalize_scene_stem(alias)] = scene_key
    return index


SCENE_ALIAS_INDEX = _build_scene_alias_index()


def collect_scene_images(scenes_dir: Path) -> list[Path]:
    return [
        p
        for p in sorted(scenes_dir.iterdir())
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]


def build_zone_slideshow_images(images: list[Path]) -> list[Path]:
    matched: dict[str, Path] = {}
    unmatched: list[Path] = []
    for image in images:
        normalized_stem = _normalize_scene_stem(image.stem)
        scene_key = SCENE_ALIAS_INDEX.get(normalized_stem)
        if scene_key is None:
            for alias_normalized, alias_scene_key in SCENE_ALIAS_INDEX.items():
                if normalized_stem.endswith("_" + alias_normalized) or normalized_stem.startswith(
                    alias_normalized + "_"
                ):
                    scene_key = alias_scene_key
                    break
        if scene_key is None:
            unmatched.append(image)
            continue
        matched.setdefault(scene_key, image)

    if not matched:
        return images

    ordered = [matched[key] for key in ZONE_IMAGE_SEQUENCE if key in matched]
    ordered.extend(unmatched)
    return ordered


def validate_slideshow_inputs(audio: Path | None, scenes_dir: Path | None) -> list[Path]:
    if audio is None:
        raise ValueError("Audio file cannot be empty.")
    if scenes_dir is None:
        raise ValueError("Slideshow mode requires --scenes-dir (the image directory).")
    if not scenes_dir.is_dir():
        raise FileNotFoundError(f"Scenes directory not found: {scenes_dir}")
    if not audio.is_file():
        raise FileNotFoundError(f"Audio not found: {audio}")

    images = collect_scene_images(scenes_dir)
    if not images:
        raise ValueError(f"No .jpg/.png images found in: {scenes_dir}")
    return build_zone_slideshow_images(images)
