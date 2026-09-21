"""Shared discovery and thumbnail UI for landscape/portrait story artwork."""
from __future__ import annotations

import json
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, UnidentifiedImageError

from studio.prompt_contract import load_prompt_contract

ASPECTS = ("landscape", "portrait")
EXPECTED_IMAGE_STEMS = (
    "cover", "greeting", "opening", "introduction", "development",
    "climax", "falling", "ending", "farewell", "outro",
)
ZONE_IMAGE_STEMS = {
    "GREETING": "greeting", "OPENING": "opening", "INTRODUCTION": "introduction",
    "DEVELOPMENT": "development", "CLIMAX": "climax", "FALLING": "falling",
    "ENDING": "ending", "FAREWELL": "farewell",
}
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


def is_project_image(path: Path) -> bool:
    """Return whether a directory entry is a completed project image."""
    return (
        path.is_file()
        and path.suffix.lower() in IMAGE_SUFFIXES
        and not path.stem.casefold().endswith(".tmp")
    )


def visual_plan_image_stems(output_dir: Path) -> tuple[str, ...]:
    """Return the persisted active image set, falling back to legacy ZONE names."""
    path = output_dir / "visual_plan.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        assets = document.get("assets") if isinstance(document, dict) else None
        mode = (document.get("resolved_mode") or document.get("resolved_image_generation_mode")) if isinstance(document, dict) else None
        stems = tuple(
            Path(str(item.get("basename"))).stem.casefold()
            for item in assets
            if isinstance(item, dict) and isinstance(item.get("basename"), str)
        ) if isinstance(assets, list) else ()
        if mode in {"ZONE", "SCENE"} and stems and len(stems) == len(set(stems)):
            return stems
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return EXPECTED_IMAGE_STEMS


def apply_visual_plan_zone_aliases(
    catalog: dict[str, dict[str, Path]], output_dir: Path
) -> None:
    """Map each story zone to its first selected SCENE image for reader views."""
    try:
        document = json.loads((output_dir / "visual_plan.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return
    if not isinstance(document, dict) or (document.get("resolved_mode") or document.get("resolved_image_generation_mode")) != "SCENE":
        return
    assets = document.get("assets")
    if not isinstance(assets, list):
        return
    for item in assets:
        if not isinstance(item, dict):
            continue
        zone_stem = ZONE_IMAGE_STEMS.get(str(item.get("zone") or "").upper())
        basename = item.get("basename")
        scene_stem = Path(basename).stem.casefold() if isinstance(basename, str) else ""
        if not zone_stem or not scene_stem:
            continue
        for images in catalog.values():
            if scene_stem in images:
                images.setdefault(zone_stem, images[scene_stem])


def scene_assets_for_items(
    output_dir: Path, item_indexes: list[int],
) -> tuple[dict[str, Any], ...]:
    """Return planned SCENE assets that cover the supplied script indexes.

    Reader views use this to describe an absent image as a missing *scene*,
    rather than incorrectly implying that every script item needs its own
    ZONE image. Older plans without item spans retain the zone association.
    """
    try:
        document = json.loads((output_dir / "visual_plan.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return ()
    if not isinstance(document, dict):
        return ()
    mode = document.get("resolved_mode") or document.get("resolved_image_generation_mode")
    assets = document.get("assets")
    if mode != "SCENE" or not isinstance(assets, list) or not item_indexes:
        return ()

    first, last = min(item_indexes), max(item_indexes)
    selected: list[dict[str, Any]] = []
    for asset in assets:
        if not isinstance(asset, dict) or str(asset.get("role") or "").upper() != "SCENE":
            continue
        basename = asset.get("basename")
        start, end = asset.get("script_item_start"), asset.get("script_item_end")
        if not isinstance(basename, str) or not isinstance(start, int) or not isinstance(end, int):
            continue
        if start <= last and end >= first:
            selected.append({"basename": basename, "start": start, "end": end})
    return tuple(sorted(selected, key=lambda asset: (asset["start"], asset["end"], asset["basename"])))


def image_for_context(
    catalog: Mapping[str, Mapping[str, Path]], output_dir: Path | None, *,
    aspect: str, zone: str, item_indexes: list[int],
) -> tuple[Path | None, tuple[dict[str, Any], ...]]:
    """Resolve an image for a UI context, respecting the active image mode.

    The second result lists missing planned SCENE assets.  ZONE packages and
    contexts outside a planned scene keep the established zone-image fallback.
    """
    assets = image_assets_for_context(catalog, output_dir, aspect=aspect, zone=zone, item_indexes=item_indexes)
    missing = tuple(
        {key: asset[key] for key in ("basename", "start", "end")}
        for asset in assets if asset["path"] is None and asset["scene"]
    )
    return next((asset["path"] for asset in assets if asset["path"] is not None), None), missing


def image_assets_for_context(
    catalog: Mapping[str, Mapping[str, Path]], output_dir: Path | None, *,
    aspect: str, zone: str, item_indexes: list[int],
) -> tuple[dict[str, Any], ...]:
    """Return ordered image slots for one UI context.

    SCENE slots retain their planned order and remain present when their image
    file is absent, allowing callers to render an honest gallery with gaps.
    """
    planned = scene_assets_for_items(output_dir, item_indexes) if output_dir else ()
    images = catalog.get(aspect, {})
    if planned:
        return tuple({
            **asset,
            "path": images.get(Path(asset["basename"]).stem.casefold()),
            "scene": True,
        } for asset in planned)
    path = image_for_zone(catalog, aspect, zone)
    return ({"basename": f"{zone.casefold()}.png", "start": None, "end": None, "path": path, "scene": False},)


def discover_story_images(output_dir: Path) -> dict[str, dict[str, Path]]:
    result: dict[str, dict[str, Path]] = {}
    for aspect in ASPECTS:
        directory = output_dir / aspect
        images: dict[str, Path] = {}
        if directory.is_dir():
            for path in directory.iterdir():
                if is_project_image(path):
                    images.setdefault(path.stem.casefold(), path.resolve())
        result[aspect] = images
    return result


def inspect_story_images(output_dir: Path) -> dict[str, dict[str, Any]]:
    discovered = discover_story_images(output_dir)
    contract = load_prompt_contract()
    expected_size = {
        "landscape": contract.landscape_size,
        "portrait": contract.portrait_size,
    }
    summary: dict[str, dict[str, Any]] = {}
    expected_stems = visual_plan_image_stems(output_dir)
    for aspect, images in discovered.items():
        missing = [f"{stem}.png" for stem in expected_stems if stem not in images]
        noncanonical: list[str] = []
        wrong_size: list[str] = []
        for stem in expected_stems:
            path = images.get(stem)
            if path is None:
                continue
            if path.name != f"{stem}.png":
                noncanonical.append(path.name)
            try:
                metadata = image_metadata(path)
                if (metadata["width"], metadata["height"]) != expected_size[aspect]:
                    wrong_size.append(
                        f"{path.name} ({metadata['width']}×{metadata['height']})"
                    )
            except (OSError, SyntaxError, UnidentifiedImageError):
                wrong_size.append(f"{path.name} (không đọc được)")
        summary[aspect] = {
            "directory": output_dir / aspect,
            "images": images,
            "count": sum(stem in images for stem in expected_stems),
            "expected": len(expected_stems),
            "missing": missing,
            "noncanonical": noncanonical,
            "wrong_size": wrong_size,
            "prompt_conformant": not missing and not noncanonical and not wrong_size,
            "expected_size": expected_size[aspect],
            "total_bytes": sum(path.stat().st_size for path in images.values() if path.is_file()),
        }
    return summary


def image_for_zone(
    catalog: Mapping[str, Mapping[str, Path]], aspect: str, zone: str
) -> Path | None:
    stem = ZONE_IMAGE_STEMS.get(zone.upper())
    return catalog.get(aspect, {}).get(stem) if stem else None


@lru_cache(maxsize=128)
def _thumbnail_cached(
    path_text: str, modified_ns: int, max_width: int,
    frame_width: int, frame_height: int,
) -> bytes:
    del modified_ns
    path = Path(path_text)
    with Image.open(path) as image:
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGB")
        if frame_width > 0 and frame_height > 0:
            canvas_height = round(max_width * frame_height / frame_width)
            image.thumbnail((max_width, canvas_height), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (max_width, canvas_height), (17, 24, 39))
            if image.mode == "RGBA":
                canvas.paste(
                    image, ((max_width - image.width) // 2, (canvas_height - image.height) // 2), image
                )
            else:
                canvas.paste(image, ((max_width - image.width) // 2, (canvas_height - image.height) // 2))
            image = canvas
        else:
            image.thumbnail((max_width, max_width), Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, format="WEBP", quality=82, method=4)
        return output.getvalue()


def thumbnail_bytes(
    path: Path, *, max_width: int = 480,
    frame_ratio: tuple[int, int] | None = None,
) -> bytes:
    stat = path.stat()
    frame_width, frame_height = frame_ratio or (0, 0)
    return _thumbnail_cached(
        str(path.resolve()), stat.st_mtime_ns, max_width, frame_width, frame_height
    )


def image_metadata(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        return {
            "width": image.width,
            "height": image.height,
            "mode": image.mode,
            "format": image.format or path.suffix.lstrip(".").upper(),
            "size_bytes": path.stat().st_size,
        }


def _format_size(size: int) -> str:
    return f"{size / 1024 / 1024:.1f} MB" if size >= 1024 * 1024 else f"{size / 1024:.1f} KB"


def render_image_thumbnail(
    path: Path | None,
    *,
    caption: str,
    key: str,
    detail: str = "",
    show_download: bool = True,
    frame_ratio: tuple[int, int] | None = None,
) -> None:
    import streamlit as st

    if path is None or not path.is_file():
        st.info(f"Thiếu ảnh · {caption}")
        return
    try:
        preview = thumbnail_bytes(path, frame_ratio=frame_ratio)
        metadata = image_metadata(path)
    except (OSError, SyntaxError, UnidentifiedImageError) as exc:
        st.error(f"Không thể đọc `{path.name}`: {exc}")
        return
    st.image(preview, caption=caption, width="stretch")
    if detail:
        st.caption(detail)
    if st.button("Phóng to", key=f"image_zoom_{key}", width="stretch"):
        _show_image_dialog(path, caption, metadata, show_download=show_download)


def _show_image_dialog(
    path: Path, caption: str, metadata: Mapping[str, Any], *, show_download: bool
) -> None:
    import streamlit as st

    @st.dialog(caption, width="large")
    def dialog() -> None:
        st.image(str(path), width="stretch")
        st.caption(
            f"{metadata['width']}×{metadata['height']} · {metadata['format']} · "
            f"{_format_size(int(metadata['size_bytes']))} · `{path.name}`"
        )
        if show_download:
            st.download_button(
                "Tải ảnh gốc", data=path.read_bytes(), file_name=path.name,
                mime=Image.MIME.get(str(metadata["format"]).upper(), "application/octet-stream"),
                key=f"download_image_{path.parent.name}_{path.name}",
            )

    dialog()


def stage_applicable_aspects(stage: str | None) -> tuple[str, ...]:
    """Return image aspects owned by or inherited into the current package stage."""
    if stage == "STAGE1":
        return ()
    if stage == "STAGE2":
        return ("landscape",)
    return ASPECTS


def render_aspect_cover_gallery(
    output_dir: Path, *, key_prefix: str, stage: str | None = None
) -> None:
    import streamlit as st

    summary = inspect_story_images(output_dir)
    columns = st.columns(2)
    for column, aspect in zip(columns, ASPECTS):
        data = summary[aspect]
        with column:
            st.markdown(f"**{aspect.title()}**")
            if aspect not in stage_applicable_aspects(stage):
                st.info("Chưa áp dụng ở stage này.")
                continue
            cover = data["images"].get("cover")
            render_image_thumbnail(
                cover, caption=f"Cover · {aspect.title()}", key=f"{key_prefix}_{aspect}",
                detail=f"{data['count']}/{data['expected']} ảnh · {_format_size(data['total_bytes'])}",
                frame_ratio=(16, 9),
            )
            if data["missing"]:
                st.warning("Thiếu: " + ", ".join(data["missing"]))
            if data["noncanonical"]:
                st.warning("Dùng để xem được nhưng không đúng package PNG: " + ", ".join(data["noncanonical"]))
            if data["wrong_size"]:
                width, height = data["expected_size"]
                st.warning(f"Sai kích thước prompt {width}×{height}: " + ", ".join(data["wrong_size"]))
            if data["prompt_conformant"]:
                st.success("Đạt file set, PNG và kích thước deterministic của prompt.")


__all__ = [
    "ASPECTS", "EXPECTED_IMAGE_STEMS", "ZONE_IMAGE_STEMS", "apply_visual_plan_zone_aliases", "discover_story_images",
    "image_assets_for_context", "image_for_context", "image_for_zone", "image_metadata", "inspect_story_images", "is_project_image", "render_aspect_cover_gallery", "scene_assets_for_items",
    "visual_plan_image_stems",
    "render_image_thumbnail", "stage_applicable_aspects", "thumbnail_bytes",
]
