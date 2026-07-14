from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from PIL import Image, UnidentifiedImageError

from video.config import ASPECT_RESOLUTIONS, IMAGE_EXTENSIONS, ZONE_IMAGE_ALIASES, ZONE_IMAGE_SEQUENCE


ReadinessLevel = Literal["ok", "warning", "error"]


@dataclass(frozen=True)
class ImageAssetStatus:
    path: Path
    role: str
    level: ReadinessLevel
    message: str
    width: Optional[int] = None
    height: Optional[int] = None
    zone: Optional[str] = None

    @property
    def aspect_ratio(self) -> Optional[float]:
        if not self.width or not self.height:
            return None
        return self.width / self.height


@dataclass(frozen=True)
class ImageReadinessReport:
    ready: bool
    errors: list[str]
    warnings: list[str]
    assets: list[ImageAssetStatus]
    expected_width: int
    expected_height: int
    scene_count: int = 0
    mapped_zones: tuple[str, ...] = ()
    missing_zones: tuple[str, ...] = ()
    unmatched_files: tuple[Path, ...] = ()


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


def _scene_key_for_path(image: Path) -> Optional[str]:
    normalized_stem = _normalize_scene_stem(image.stem)
    scene_key = SCENE_ALIAS_INDEX.get(normalized_stem)
    if scene_key is not None:
        return scene_key
    for alias_normalized, alias_scene_key in SCENE_ALIAS_INDEX.items():
        if normalized_stem.endswith("_" + alias_normalized) or normalized_stem.startswith(
            alias_normalized + "_"
        ):
            return alias_scene_key
    return None


def build_zone_slideshow_images(images: list[Path]) -> list[Path]:
    matched: dict[str, Path] = {}
    unmatched: list[Path] = []
    for image in images:
        scene_key = _scene_key_for_path(image)
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


def _expected_resolution(aspect: str) -> tuple[int, int]:
    if aspect in ASPECT_RESOLUTIONS:
        return ASPECT_RESOLUTIONS[aspect]  # type: ignore[index]
    return ASPECT_RESOLUTIONS["9x16"]


def _inspect_image_file(
    path: Path,
    *,
    role: str,
    aspect: str,
    zone: Optional[str] = None,
) -> ImageAssetStatus:
    if not path.is_file():
        return ImageAssetStatus(
            path=path,
            role=role,
            zone=zone,
            level="error",
            message=f"Image file not found: {path}",
        )
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        return ImageAssetStatus(
            path=path,
            role=role,
            zone=zone,
            level="error",
            message=f"Unsupported image extension for video render: {path.name}",
        )

    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
    except (OSError, UnidentifiedImageError) as exc:
        return ImageAssetStatus(
            path=path,
            role=role,
            zone=zone,
            level="error",
            message=f"Image cannot be opened: {path.name} ({exc})",
        )

    expected_width, expected_height = _expected_resolution(aspect)
    expected_ratio = expected_width / expected_height
    actual_ratio = width / height if height else 0.0
    ratio_delta = abs(actual_ratio - expected_ratio)
    min_width = max(1, expected_width // 2)
    min_height = max(1, expected_height // 2)

    if width < min_width or height < min_height:
        return ImageAssetStatus(
            path=path,
            role=role,
            zone=zone,
            level="warning",
            width=width,
            height=height,
            message=(
                f"Image is smaller than recommended for {aspect}: "
                f"{width}x{height}, expected near {expected_width}x{expected_height}"
            ),
        )
    if ratio_delta > 0.08:
        return ImageAssetStatus(
            path=path,
            role=role,
            zone=zone,
            level="warning",
            width=width,
            height=height,
            message=(
                f"Image aspect ratio differs from {aspect}: "
                f"{width}x{height}, expected near {expected_width}x{expected_height}"
            ),
        )
    return ImageAssetStatus(
        path=path,
        role=role,
        zone=zone,
        level="ok",
        width=width,
        height=height,
        message=f"Ready: {width}x{height}",
    )


def inspect_video_image_readiness(
    *,
    mode: str,
    aspect: str,
    cover: Path | None = None,
    scenes_dir: Path | None = None,
) -> ImageReadinessReport:
    expected_width, expected_height = _expected_resolution(aspect)
    assets: list[ImageAssetStatus] = []
    errors: list[str] = []
    warnings: list[str] = []
    mapped_zones: list[str] = []
    unmatched_files: list[Path] = []

    if mode == "static":
        if cover is None:
            errors.append("Static mode requires a cover image.")
        else:
            assets.append(_inspect_image_file(cover, role="cover", aspect=aspect))

    scene_count = 0
    if mode == "slideshow":
        if scenes_dir is None:
            errors.append("Slideshow mode requires a scenes directory.")
        elif not scenes_dir.is_dir():
            errors.append(f"Scenes directory not found: {scenes_dir}")
        else:
            images = collect_scene_images(scenes_dir)
            scene_count = len(images)
            if not images:
                errors.append(f"No .jpg/.png images found in: {scenes_dir}")
            for image in build_zone_slideshow_images(images):
                zone = _scene_key_for_path(image)
                if zone is None:
                    unmatched_files.append(image)
                elif zone not in mapped_zones:
                    mapped_zones.append(zone)
                assets.append(_inspect_image_file(image, role="scene", aspect=aspect, zone=zone))

            unsupported_images = [
                p
                for p in sorted(scenes_dir.iterdir())
                if p.is_file()
                and p.suffix.lower() not in IMAGE_EXTENSIONS
                and p.suffix.lower() in {".webp", ".gif", ".bmp", ".tif", ".tiff"}
            ]
            for unsupported in unsupported_images:
                warnings.append(
                    f"Scene image will be ignored because its extension is unsupported: {unsupported.name}"
                )

    for asset in assets:
        if asset.level == "error":
            errors.append(asset.message)
        elif asset.level == "warning":
            warnings.append(asset.message)

    if mode == "slideshow" and scene_count > 0:
        missing_zones = tuple(zone for zone in ZONE_IMAGE_SEQUENCE if zone not in mapped_zones)
        if unmatched_files:
            warnings.append(
                "Some scene images do not match a known story zone: "
                + ", ".join(path.name for path in unmatched_files)
            )
        if mapped_zones and missing_zones:
            warnings.append("Some story zone images are missing: " + ", ".join(missing_zones))
    else:
        missing_zones = ()

    return ImageReadinessReport(
        ready=not errors,
        errors=errors,
        warnings=warnings,
        assets=assets,
        expected_width=expected_width,
        expected_height=expected_height,
        scene_count=scene_count,
        mapped_zones=tuple(mapped_zones),
        missing_zones=missing_zones,
        unmatched_files=tuple(unmatched_files),
    )
