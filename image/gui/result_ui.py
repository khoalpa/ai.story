from __future__ import annotations

import json
import base64
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import streamlit as st
try:
    import streamlit.components.v1 as components
except Exception:  # pragma: no cover - fallback for lightweight test stubs
    components = SimpleNamespace(html=lambda *args, **kwargs: None)

from common.gui.handoff_utils import (
    HandoffAction,
    render_handoff_action_row,
)
from common.gui.state import (
    send_image_to_video,
    set_image_handoff,
)
from common.gui.user_messages import (
    show_empty_result,
    show_preview_warning,
)
from common.gui.workspace_source_outputs import (
    workspace_source_outputs,
)
from image.gui.common_ui import (
    _copy_path_hint,
    _normalize_exc,
    _open_output_folder,
    _ui_error,
    _ui_info,
    _ui_success,
    _ui_warning,
)
from image.gui.prompt_state import _get_effective_prompt_edit
from image.workflow_routing import infer_prompt_kind

_IMAGE_TEMP_COVER_PATH_KEY = "image_temp_cover_path"
_IMAGE_TEMP_COVER_SOURCE_KEY = "image_temp_cover_source"


def _safe_read_manifest(path_value: str | Path | None) -> dict[str, Any]:
    if not path_value:
        return {}
    try:
        path = Path(path_value)
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}


def _list_image_files(dir_value: str | Path | None) -> list[Path]:
    if not dir_value:
        return []
    directory = Path(dir_value)
    if not directory.is_dir():
        return []
    items: list[Path] = []
    for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        items.extend(sorted(directory.glob(pattern)))
    deduped: list[Path] = []
    seen: set[str] = set()
    for item in items:
        key = str(item.resolve()) if item.exists() else str(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _version_index_from_path(path: Path, *, stem: str) -> int | None:
    if path.suffix.lower() != ".png":
        return None
    if path.stem == stem:
        return 0
    prefix = f"{stem}_"
    if not path.stem.startswith(prefix):
        return None
    suffix = path.stem[len(prefix):]
    if not suffix.isdigit():
        return None
    return int(suffix)


def _versioned_image_path(directory: Path, *, stem: str, version_index: int) -> Path:
    if version_index <= 0:
        return directory / f"{stem}.png"
    return directory / f"{stem}_{version_index}.png"


def _existing_version_indices(directory: Path, *, stem: str) -> set[int]:
    versions: set[int] = set()
    for pattern in (f"{stem}.png", f"{stem}_*.png"):
        for path in directory.glob(pattern):
            version = _version_index_from_path(path, stem=stem)
            if version is not None:
                versions.add(version)
    return versions


def _previous_complete_run_version(directory: Path) -> int | None:
    cover_versions = _existing_version_indices(directory, stem="cover")
    scene_versions = _existing_version_indices(directory, stem="scene")
    common_versions = sorted(cover_versions & scene_versions)
    if not common_versions:
        return None
    if len(common_versions) == 1:
        return common_versions[0]
    return common_versions[-2]


def _current_result_version_index(result: Any) -> int | None:
    cover_image = getattr(result, "cover_image", None)
    if cover_image:
        try:
            cover_path = Path(cover_image)
            version = _version_index_from_path(cover_path, stem="cover")
            if version is not None:
                return version
        except Exception:
            pass

    versions: set[int] = set()
    for generated_path in list(getattr(result, "generated_files", []) or []):
        try:
            path = Path(generated_path)
        except Exception:
            continue
        if not path.is_file():
            continue
        for stem in ("cover", "scene"):
            version = _version_index_from_path(path, stem=stem)
            if version is not None:
                versions.add(version)
                break
    if versions:
        return max(versions)
    return None


def _base_image_stem(path: Path) -> str:
    stem = path.stem
    if "_" in stem:
        head, tail = stem.rsplit("_", 1)
        if tail.isdigit():
            return head
    return stem


def _find_scene_output_by_key(scene_dir: Path | None, *, image_key: str, version_index: int | None = None) -> Path | None:
    if scene_dir is None or not scene_dir.is_dir():
        return None
    normalized_key = str(image_key or "").strip()
    if not normalized_key:
        return None

    if version_index is not None:
        versioned_patterns = [
            f"{normalized_key}_{version_index}.png",
            f"{normalized_key}_{version_index}.jpg",
            f"{normalized_key}_{version_index}.jpeg",
            f"{normalized_key}_{version_index}.webp",
        ]
        for pattern in versioned_patterns:
            matches = sorted(scene_dir.glob(pattern))
            if matches:
                return matches[0]

    direct_patterns = [
        f"{normalized_key}.png",
        f"{normalized_key}.jpg",
        f"{normalized_key}.jpeg",
        f"{normalized_key}.webp",
        f"{normalized_key}_*.png",
        f"{normalized_key}_*.jpg",
        f"{normalized_key}_*.jpeg",
        f"{normalized_key}_*.webp",
    ]
    for pattern in direct_patterns:
        matches = sorted(scene_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


def _current_temp_cover_path() -> Path | None:
    value = str(st.session_state.get(_IMAGE_TEMP_COVER_PATH_KEY) or "").strip()
    if not value:
        return None
    path = Path(value)
    if path.is_file():
        return path
    return None


def _set_temp_cover(path_value: str | Path, *, source_label: str = "") -> None:
    path = Path(path_value)
    st.session_state[_IMAGE_TEMP_COVER_PATH_KEY] = str(path)
    st.session_state[_IMAGE_TEMP_COVER_SOURCE_KEY] = source_label or path.name


def _expected_output_path(
    result: Any,
    *,
    kind: str,
    prompt_data: dict[str, Any] | None = None,
    rel_path: str = "",
    slot: str = "",
    suggested_output: str | Path | None = None,
) -> Path:
    prompt_data = dict(prompt_data or {})
    output_dir = Path(str(getattr(result, "output_dir", "") or ""))
    scene_images_dir_value = str(getattr(result, "scene_images_dir", "") or "").strip()
    scene_dir = Path(scene_images_dir_value) if scene_images_dir_value else (output_dir / "images")
    suggested_output_name = ""
    if suggested_output is not None:
        try:
            suggested_output_name = Path(suggested_output).name
        except Exception:
            suggested_output_name = ""
    if kind == "cover":
        cover_image = getattr(result, "cover_image", None)
        if cover_image and Path(cover_image).is_file():
            return Path(cover_image)
        if _current_temp_cover_path() is not None and _current_temp_cover_path().is_file():
            return _current_temp_cover_path()
        if suggested_output_name:
            candidate_cover = output_dir / suggested_output_name
            if candidate_cover.is_file():
                return candidate_cover
        fallback_cover = output_dir / "images" / "cover.png"
        if fallback_cover.is_file():
            return fallback_cover
        legacy_cover = output_dir / "cover.png"
        if legacy_cover.is_file():
            return legacy_cover
        scene_cover = scene_dir / "cover.png"
        if scene_cover.is_file():
            return scene_cover
        return fallback_cover
    image_key = str(
        prompt_data.get("image_key")
        or Path(suggested_output_name).stem
        or slot
        or Path(rel_path or "scene").stem
    ).strip()
    current_version = _current_result_version_index(result)
    resolved = _find_scene_output_by_key(scene_dir, image_key=image_key, version_index=current_version)
    if resolved is not None:
        return resolved
    return scene_dir / f"{image_key}.png"


def _versioned_expected_output_path(result: Any, entry: dict[str, Any], *, fallback_path: Path | None = None) -> Path | None:
    prompt_data = dict(entry.get("prompt_data") or {})
    kind = str(entry.get("kind") or infer_prompt_kind(prompt_data, entry.get("path")) or "").strip().lower()
    current_version = _current_result_version_index(result)
    if current_version is None:
        return fallback_path

    output_dir = Path(str(getattr(result, "output_dir", "") or ""))
    scene_images_dir_value = str(getattr(result, "scene_images_dir", "") or "").strip()
    scene_dir = Path(scene_images_dir_value) if scene_images_dir_value else (output_dir / "images")

    if kind == "cover":
        return _versioned_image_path(scene_dir, stem="cover", version_index=current_version)

    suggested_output = entry.get("suggested_output")
    suggested_output_name = ""
    if suggested_output is not None:
        try:
            suggested_output_name = Path(suggested_output).name
        except Exception:
            suggested_output_name = ""
    image_key = str(
        prompt_data.get("image_key")
        or Path(suggested_output_name).stem
        or entry.get("slot")
        or Path(entry.get("rel_path") or "scene").stem
    ).strip()
    return _versioned_image_path(scene_dir, stem=image_key, version_index=current_version)


def _resolve_result_output_for_entry(result: Any, entry: dict[str, Any]) -> Path:
    prompt_data = dict(entry.get("prompt_data") or {})
    kind = str(entry.get("kind") or infer_prompt_kind(prompt_data, entry.get("path")) or "").strip().lower()
    return _expected_output_path(
        result,
        kind=kind,
        prompt_data=prompt_data,
        rel_path=str(entry.get("rel_path") or ""),
        slot=str(entry.get("slot") or ""),
        suggested_output=entry.get("suggested_output"),
    )


def _resolve_latest_run_cover_preview(result: Any) -> Path | None:
    expected_cover = _expected_output_path(result, kind="cover")
    if expected_cover.is_file():
        return expected_cover
    if not bool(getattr(result, "_prefer_filesystem_cover", False)):
        temp_cover = _current_temp_cover_path()
        if temp_cover is not None and temp_cover.is_file():
            return temp_cover
    return None


def _resolve_latest_run_scene_preview(result: Any) -> Path | None:
    generated_files = list(getattr(result, "generated_files", []) or [])
    for generated_path in reversed(generated_files):
        try:
            path = Path(generated_path)
        except Exception:
            continue
        if path.is_file() and path.name.lower() != "cover.png":
            return path

    scene_images_dir_value = str(getattr(result, "scene_images_dir", "") or "").strip()
    if not scene_images_dir_value:
        return None
    scene_dir = Path(scene_images_dir_value)
    preview_version = _previous_complete_run_version(scene_dir)
    if preview_version is None:
        return None
    scene_path = _versioned_image_path(scene_dir, stem="scene", version_index=preview_version)
    if scene_path.is_file():
        return scene_path
    return None


def _build_existing_run_preview_result(output_dir_value: str | Path | None) -> Any | None:
    output_dir_text = str(output_dir_value or "").strip()
    if not output_dir_text:
        return None
    output_dir = Path(output_dir_text)
    if not output_dir.is_dir():
        return None

    manifest_path = output_dir / "image_result_manifest.json"
    manifest_data = _safe_read_manifest(manifest_path)
    scene_dir = output_dir / "images"
    preview_version = _previous_complete_run_version(scene_dir)
    if preview_version is None:
        return None

    cover_image = _versioned_image_path(scene_dir, stem="cover", version_index=preview_version)
    scene_image = _versioned_image_path(scene_dir, stem="scene", version_index=preview_version)
    if not cover_image.is_file() or not scene_image.is_file():
        return None

    return SimpleNamespace(
        provider=str(manifest_data.get("provider") or ""),
        output_dir=output_dir,
        cover_image=cover_image,
        scene_images_dir=scene_dir,
        generated_files=[cover_image, scene_image],
        manifest_path=manifest_path if manifest_path.is_file() else None,
        logs=[],
        _prefer_filesystem_cover=True,
    )


def _version_pair_label(version_index: int) -> str:
    if version_index <= 0:
        return "current"
    if version_index == 1:
        return "previous"
    return f"previous-{version_index}"


def _result_images_dir(result: Any) -> Path:
    images_dir_value = str(getattr(result, "images_dir", "") or "").strip()
    if images_dir_value:
        return Path(images_dir_value)
    scene_images_dir_value = str(getattr(result, "scene_images_dir", "") or "").strip()
    if scene_images_dir_value:
        return Path(scene_images_dir_value)
    return Path(str(getattr(result, "output_dir", "") or "")) / "images"


def _build_double_click_image_view(
    path: Path,
    *,
    caption: str,
    alt_text: str | None = None,
    tooltip: str = "Open 100% view",
) -> tuple[str, int]:
    image_bytes = path.read_bytes()
    encoded = base64.b64encode(image_bytes).decode("ascii")
    suffix = path.suffix.lower()
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".png": "image/png",
    }.get(suffix, "image/png")
    alt = alt_text or caption or path.name
    html = f"""
    <div class="viewer-shell">
      <div class="thumb-wrap" title="{tooltip}">
        <img id="thumb" class="thumb" alt="{alt}" src="data:{mime};base64,{encoded}" />
        <div class="hint">{tooltip}</div>
      </div>
    </div>
    <style>
      html, body {{
        margin: 0;
        padding: 0;
        background: transparent;
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Arial, sans-serif;
      }}
      .viewer-shell {{
        width: 100%;
        color: #e5e7eb;
        box-sizing: border-box;
      }}
      .thumb-wrap {{
        position: relative;
        display: inline-block;
        width: 100%;
        cursor: zoom-in;
        user-select: none;
      }}
      .thumb {{
        display: block;
        width: 100%;
        height: auto;
        border-radius: 14px;
        box-shadow: 0 14px 40px rgba(0, 0, 0, 0.14);
        border: 1px solid rgba(255, 255, 255, 0.12);
        background: #111827;
      }}
      .hint {{
        position: absolute;
        left: 12px;
        bottom: 12px;
        padding: 0.3rem 0.55rem;
        border-radius: 999px;
        background: rgba(17, 24, 39, 0.78);
        color: #fff;
        font-size: 12px;
        font-weight: 600;
        letter-spacing: 0.01em;
      }}
    </style>
    <script>
      const thumb = document.getElementById('thumb');
      function openZoomWindow() {{
        const popup = window.open('', '_blank', 'noopener,noreferrer');
        if (!popup) {{
          return;
        }}
        popup.document.open();
        popup.document.write(`<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{caption}</title>
    <style>
      html, body {{
        margin: 0;
        padding: 0;
        background: #0b1220;
        width: 100%;
        height: 100%;
        overflow: auto;
      }}
      .frame {{
        min-width: 100%;
        min-height: 100%;
        display: flex;
        align-items: flex-start;
        justify-content: flex-start;
        flex-direction: column;
        padding: 12px;
        box-sizing: border-box;
        gap: 10px;
        color: #e5e7eb;
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Arial, sans-serif;
      }}
      .hint {{
        font-size: 12px;
        font-weight: 600;
        letter-spacing: 0.01em;
        color: #cbd5e1;
      }}
      img {{
        display: block;
        width: auto;
        height: auto;
        max-width: none;
        max-height: none;
      }}
    </style>
  </head>
  <body>
    <div class="frame">
      <div class="hint">100% view</div>
      <img alt="{alt}" src="data:{mime};base64,{encoded}" />
    </div>
  </body>
</html>`);
        popup.document.close();
        popup.focus();
      }}
      thumb.addEventListener('dblclick', (event) => {{
        event.preventDefault();
        event.stopPropagation();
        openZoomWindow();
      }});
    </script>
    """
    height = 480
    try:
        from PIL import Image

        with Image.open(path) as img:
            height = max(380, min(900, int(img.height) + 120))
    except Exception:
        height = 480
    return html, height

def _render_double_click_image(path: Path, *, caption: str, tooltip: str = "Open 100% view") -> None:
    html, height = _build_double_click_image_view(path, caption=caption, tooltip=tooltip)
    components.html(html, height=height, scrolling=False)


def _output_status_for_entry(result: Any, entry: dict[str, Any]) -> tuple[str, str, Path]:
    output_path = _resolve_result_output_for_entry(result, entry)
    temp_cover = _current_temp_cover_path()
    if temp_cover is not None and output_path.exists() and temp_cover.resolve() == output_path.resolve():
        return "using temp cover", "warning", output_path
    if output_path.is_file():
        return "generated", "success", output_path
    return "missing", "error", output_path


def _status_badge_text(level: str, text: str) -> str:
    icon = {"success": "[ok]", "warning": "[warn]", "error": "[error]", "info": "[info]"}.get(level, "-")
    return f"{icon} {text}"


def _display_value(value: Any, *, missing_label: str = "missing", empty_label: str = "empty") -> str:
    if value is None:
        return missing_label
    text = str(value)
    if not text:
        return empty_label
    return text


def _prompt_card_meta_text(*, kind: str, rel_path: str, image_key: str, output_path: Path | None = None, actual_path: Path | None = None) -> str:
    parts = [
        f"kind={_display_value(kind)}",
        f"rel={_display_value(rel_path)}",
        f"key={_display_value(image_key)}",
    ]
    if output_path is not None:
        parts.append(f"expected={_display_value(output_path.name)}")
    if output_path is not None and actual_path is not None:
        expected_version = _version_index_from_path(output_path, stem=_base_image_stem(output_path))
        actual_version = _version_index_from_path(actual_path, stem=_base_image_stem(actual_path))
        if actual_path.name != output_path.name and expected_version != actual_version:
            parts.append(f"actual={_display_value(actual_path.name)}")
    return " | ".join(parts)


def _expected_output_location_text(*, kind: str, output_path: Path, prompt_name: str | None = None) -> str:
    name = str(prompt_name or kind or "item").strip() or "item"
    return f"{name} -> {output_path}"


def _filtered_entries_for_run(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kinds = sorted({str((entry.get("prompt_data") or {}).get("kind") or entry.get("kind") or "unknown").strip() or "unknown" for entry in entries})
    selected_kinds = st.multiselect(
        "Filter prompt cards by kind",
        options=kinds,
        default=kinds,
        key="image_run_kind_filter",
    )
    if not selected_kinds:
        return []
    selected = set(selected_kinds)
    return [
        entry for entry in entries
        if (str((entry.get("prompt_data") or {}).get("kind") or entry.get("kind") or "unknown").strip() or "unknown") in selected
    ]


def _apply_latest_image_handoff(cover_image_path: str, scene_images_dir: str, manifest_path: str) -> None:
    set_image_handoff(cover_image_path=cover_image_path, scene_images_dir=scene_images_dir, manifest_path=manifest_path)
    _ui_success("Applied latest Image handoff.")


def _persist_temp_cover_to_result(result: Any) -> None:
    temp_cover = _current_temp_cover_path()
    if result is None or temp_cover is None:
        _ui_warning("No temporary cover is available to persist.")
        return
    output_dir = Path(getattr(result, "output_dir"))
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "images" / "cover.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        from shutil import copy2

        copy2(temp_cover, target)
        if getattr(result, "cover_image", None) is None or Path(getattr(result, "cover_image")).resolve() != target.resolve():
            setattr(result, "cover_image", target)
        workspace_source_outputs(st.session_state).image_cover_output = str(target)
        set_image_handoff(cover_image_path=str(target), scene_images_dir=str(getattr(result, "scene_images_dir")), manifest_path=str(getattr(result, "manifest_path") or ""))
        manifest_data = _safe_read_manifest(getattr(result, "manifest_path", None))
        if manifest_data:
            manifest_data["cover_image"] = str(target)
            Path(getattr(result, "manifest_path")).write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8")
        st.session_state["image_last_result"] = result
        _ui_success(f"Persisted temporary cover into real file: {target}")
    except Exception as exc:
        _ui_error(f"Could not persist cover: {_normalize_exc(exc)}")


def _render_result_action_panel(result: Any, *, key_prefix: str) -> None:
    if result is None:
        return
    cover_image = str(getattr(result, "cover_image", None) or "")
    scene_images_dir = str(getattr(result, "scene_images_dir", "") or "")
    manifest_path = str(getattr(result, "manifest_path", None) or "")
    output_dir = str(getattr(result, "output_dir", "") or "")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_handoff_action_row([
            HandoffAction(
                label="Send to Video",
                key=f"{key_prefix}::send_to_video",
                callback=lambda: send_image_to_video(
                    cover_image_path=cover_image,
                    scene_images_dir=scene_images_dir,
                    manifest_path=manifest_path,
                ),
                success_message="Sent cover/scenes to Video.",
                rerun_after_click=False,
            )
        ])
    with c2:
        if st.button("Open output folder", key=f"{key_prefix}::open_output", width="stretch"):
            _open_output_folder(output_dir)
    with c3:
        _copy_path_hint(output_dir, key=f"{key_prefix}::copy_output")
    with c4:
        if st.button(
            "Use latest Image handoff",
            key=f"{key_prefix}::use_handoff",
            width="stretch",
            help="Copy the currently selected cover and scene version into the shared Image handoff state.",
        ):
            _apply_latest_image_handoff(cover_image, scene_images_dir, manifest_path)


def _render_result_preview_panel(result: Any, *, settings: dict[str, Any] | None = None, prompt_dir: Path | None = None, entries: list[dict[str, Any]] | None = None, key_prefix: str) -> None:
    if result is None:
        show_empty_result("image result preview", actions=["Run Generate images in the Run tab."])
        return
    manifest_data = _safe_read_manifest(getattr(result, "manifest_path", None))
    cover_image = getattr(result, "cover_image", None)
    scene_images_dir = getattr(result, "scene_images_dir", None)
    preview_tab, logs_tab, manifest_tab = st.tabs(["Preview", "Logs", "Manifest & debug"])
    with preview_tab:
        expected_cover = _expected_output_path(result, kind="cover")
        latest_cover_preview = _resolve_latest_run_cover_preview(result)
        latest_scene_preview = _resolve_latest_run_scene_preview(result)
        temp_cover = _current_temp_cover_path()
        images_dir = _result_images_dir(result)
        preview_version = _previous_complete_run_version(images_dir)
        preview_version_label = _version_pair_label(preview_version or 0)
        st.caption(f"Showing the {preview_version_label} complete version pair from `output/images`.")
        if latest_cover_preview is not None and latest_scene_preview is not None and latest_cover_preview.resolve() != latest_scene_preview.resolve():
            cover_col, scene_col = st.columns(2)
            with cover_col:
                st.image(str(latest_cover_preview), caption=f"Cover version: {latest_cover_preview.name}", width="stretch")
            with scene_col:
                st.image(str(latest_scene_preview), caption=f"Scene version: {latest_scene_preview.name}", width="stretch")
            st.caption("The preview always shows the last completed cover/scene pair before the newest version.")
        else:
            if latest_cover_preview is not None:
                st.image(str(latest_cover_preview), caption=f"Cover version: {latest_cover_preview.name}", width="stretch")
            else:
                show_preview_warning("cover version", actions=[f"Expected cover output: {expected_cover}", "Generate a new versioned cover image or choose a scene as the temporary cover."])
            if latest_scene_preview is not None:
                if latest_cover_preview is None or latest_scene_preview.resolve() != latest_cover_preview.resolve():
                    st.image(str(latest_scene_preview), caption=f"Scene version: {latest_scene_preview.name}", width="stretch")
                else:
                    st.caption("Scene version matches the cover version.")
            elif latest_cover_preview is not None:
                show_preview_warning("scene version", actions=["Generate a new versioned scene image or check the image_key/output mapping."])
            if temp_cover is not None:
                source_label = str(st.session_state.get(_IMAGE_TEMP_COVER_SOURCE_KEY) or temp_cover.name)
                st.caption(f"Temporary cover available for the next run: {source_label}")

                _persist_temp_cover_to_result(result)
        _render_result_action_panel(result, key_prefix=f"{key_prefix}::actions")
    with logs_tab:
        logs = list(getattr(result, "logs", None) or st.session_state.get("image_last_logs") or [])
        mode_key = f"{key_prefix}::debug_logs"
        debug_logs = bool(st.toggle("Debug logs", key=mode_key, value=bool(st.session_state.get(mode_key, False)), help="Enable this to show full runtime logs, including noisy lines such as __path__ alias warnings."))
        filtered_logs = logs if debug_logs else logs
        if filtered_logs:
            st.code("\n".join(str(line) for line in filtered_logs), language=None)
        else:
            show_empty_result("image logs", actions=["Run a new job or check provider output."])
    with manifest_tab:
        payload = {
            "provider": getattr(result, "provider", ""),
            "output_dir": str(getattr(result, "output_dir", "") or ""),
            "cover_image": str(cover_image or ""),
            "scene_images_dir": str(scene_images_dir or ""),
            "generated_files": [str(p) for p in list(getattr(result, "generated_files", []) or [])],
            "manifest_path": str(getattr(result, "manifest_path", None) or ""),
            "runtime_manifest": manifest_data,
        }
        st.json(payload)
        st.markdown("### Result summary")
        summary_cols = st.columns(4)
        with summary_cols[0]:
            st.caption(f"Output dir: {_display_value(getattr(result, 'output_dir', None))}")
        with summary_cols[1]:
            st.caption(f"Cover image: {_display_value(cover_image)}")
        with summary_cols[2]:
            st.caption(f"Scene dir: {_display_value(scene_images_dir)}")
        with summary_cols[3]:
            st.caption(f"Manifest: {_display_value(getattr(result, 'manifest_path', None))}")


def _render_prompt_cards_in_run(settings: dict[str, Any], prompt_dir: Path | None, entries: list[dict[str, Any]], result: Any) -> None:
    if not entries:
        return
    st.markdown("### Prompt cards")
    filtered_entries = _filtered_entries_for_run(entries)
    if not filtered_entries:
        _ui_info("No prompt card matches the currently selected kind filter.")
        return
    for entry in filtered_entries:
        prompt_data = dict(entry.get("prompt_data") or {})
        effective = _get_effective_prompt_edit(entry["rel_path"], prompt_data)
        suggested_output = entry.get("suggested_output")
        suggested_output_name = ""
        if suggested_output is not None:
            try:
                suggested_output_name = Path(suggested_output).name
            except Exception:
                suggested_output_name = ""
        image_key = str(prompt_data.get("image_key") or Path(suggested_output_name).stem or entry.get("slot") or Path(entry.get("rel_path") or "scene").stem).strip()
        kind = str(entry.get("kind") or infer_prompt_kind(prompt_data, entry.get("path")) or "unknown").strip() or "unknown"
        status_text = "not run yet"
        status_level = "info"
        output_path = None
        if result is not None:
            status_text, status_level, output_path = _output_status_for_entry(result, entry)
        expected_path = _versioned_expected_output_path(result, entry, fallback_path=output_path if output_path is not None else None)
        with st.container(border=True):
            head_col, action_col = st.columns([1.5, 1.0])
            with head_col:
                st.markdown(f"**{entry.get('slot') or entry['rel_path']}**")
                st.caption(f"kind={kind} | file={entry['rel_path']} | {_status_badge_text(status_level, status_text)}")
            with action_col:
                if result is not None and output_path is not None and output_path.is_file() and st.button("Set as temporary cover", key=f"run_temp_cover::{entry['rel_path']}", width="stretch"):
                    _set_temp_cover(output_path, source_label=f"run card | {entry['rel_path']}")
                    st.rerun()
            body_col, preview_col = st.columns([1.2, 1.0])
            with body_col:
                st.text_area("Prompt", value=str(effective.get("prompt") or ""), height=120, disabled=True, key=f"run_prompt::{entry['rel_path']}")
                from image.gui.prompt_ui import _render_clip_token_estimate, _render_prompt_trim_status, _render_quick_input_previews

                _render_clip_token_estimate("Prompt estimate", str(effective.get("prompt") or ""), key_suffix=f"run_prompt::{entry['rel_path']}")
                _render_prompt_trim_status(
                    "Prompt",
                    str(effective.get("prompt") or ""),
                    enabled=bool(st.session_state.get("image_local_auto_shorten_prompt", False)),
                    key_suffix=f"run_prompt_status::{entry['rel_path']}",
                )
                st.text_area("Negative prompt", value=str(effective.get("negative_prompt") or ""), height=80, disabled=True, key=f"run_negative::{entry['rel_path']}")
                _render_clip_token_estimate("Negative estimate", str(effective.get("negative_prompt") or ""), key_suffix=f"run_negative::{entry['rel_path']}")
                _render_prompt_trim_status(
                    "Negative prompt",
                    str(effective.get("negative_prompt") or ""),
                    enabled=bool(st.session_state.get("image_local_auto_shorten_negative_prompt", False)),
                    key_suffix=f"run_negative_status::{entry['rel_path']}",
                )
                with st.expander("Quick inputs", expanded=False):
                    _render_quick_input_previews(settings, prompt_dir, entry, section_key=f"run::{entry['rel_path']}", result=result)
            with preview_col:
                st.caption(_prompt_card_meta_text(kind=kind, rel_path=str(entry["rel_path"]), image_key=image_key, output_path=expected_path, actual_path=output_path))
                st.caption(_expected_output_location_text(kind=kind, output_path=output_path, prompt_name=image_key))
                if output_path is not None and output_path.is_file():
                    st.image(str(output_path), caption=output_path.name, width="stretch")
                    st.caption(str(output_path))
                else:
                    show_preview_warning("generated image", actions=["Run Generate images or check the image_key/output mapping."])

