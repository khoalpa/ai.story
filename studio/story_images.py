"""Shared discovery and thumbnail UI for landscape/portrait story artwork."""
from __future__ import annotations

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


def discover_story_images(output_dir: Path) -> dict[str, dict[str, Path]]:
    result: dict[str, dict[str, Path]] = {}
    for aspect in ASPECTS:
        directory = output_dir / aspect
        images: dict[str, Path] = {}
        if directory.is_dir():
            for path in directory.iterdir():
                if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
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
    for aspect, images in discovered.items():
        missing = [f"{stem}.png" for stem in EXPECTED_IMAGE_STEMS if stem not in images]
        noncanonical: list[str] = []
        wrong_size: list[str] = []
        for stem in EXPECTED_IMAGE_STEMS:
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
            except (OSError, UnidentifiedImageError):
                wrong_size.append(f"{path.name} (không đọc được)")
        summary[aspect] = {
            "directory": output_dir / aspect,
            "images": images,
            "count": sum(stem in images for stem in EXPECTED_IMAGE_STEMS),
            "expected": len(EXPECTED_IMAGE_STEMS),
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
    except (OSError, UnidentifiedImageError) as exc:
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
    "ASPECTS", "EXPECTED_IMAGE_STEMS", "ZONE_IMAGE_STEMS", "discover_story_images",
    "image_for_zone", "image_metadata", "inspect_story_images", "render_aspect_cover_gallery",
    "render_image_thumbnail", "stage_applicable_aspects", "thumbnail_bytes",
]
