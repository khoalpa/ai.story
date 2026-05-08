from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

from story.gui.image_prompts import build_image_prompts
from story.gui.video_handoff import materialize_story_handoff_bundle


def image_prompt_handoff_ready(result: dict[str, Any]) -> bool:
    return bool((result.get("image_prompts") or {}) and str(result.get("image_handoff_dir") or "").strip())


def story_summary_action_labels(result: dict[str, Any]) -> list[str]:
    labels = ["Send to Audio"]
    if image_prompt_handoff_ready(result):
        labels.extend(["Send to Image", "Send to Video"])
    return labels


def story_summary_download_labels(result: dict[str, Any]) -> list[str]:
    labels = ["Tải canonical JSON", "Tải gói ZIP kết quả"]
    if image_prompt_handoff_ready(result):
        labels.extend(["Tải cover prompt", "Tải scene overview prompt"])
    return labels


def attach_image_prompts_and_handoff(result: dict[str, Any]) -> Path:
    image_prompts = build_image_prompts(result.get("authoring") or {})
    bundle_dir = materialize_story_handoff_bundle(authoring=result.get("authoring") or {}, image_prompts=image_prompts)
    result["image_prompts"] = image_prompts
    result["image_handoff_dir"] = str(bundle_dir)
    result["video_handoff_dir"] = str(bundle_dir)
    return bundle_dir


def build_story_output_bundle(result: dict[str, Any]) -> bytes:
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("story_authoring.json", json.dumps(result.get("authoring"), ensure_ascii=False, indent=2))
        zf.writestr("story_plain_script.txt", result.get("plain_script") or "")
        image_prompts = result.get("image_prompts") or {}
        if image_prompts:
            zf.writestr("cover_prompt.json", json.dumps(image_prompts.get("cover"), ensure_ascii=False, indent=2))
            zf.writestr("scene_prompt.json", json.dumps(image_prompts.get("scene"), ensure_ascii=False, indent=2))
            for key, payload in sorted(image_prompts.items()):
                if key in {"cover", "scene"}:
                    continue
                zf.writestr(f"scene_prompts/{key}.json", json.dumps(payload, ensure_ascii=False, indent=2))
        bundle_dir_raw = str(result.get("image_handoff_dir") or "").strip()
        bundle_dir = Path(bundle_dir_raw) if bundle_dir_raw else None
        if bundle_dir is not None and bundle_dir.is_dir():
            for path in sorted(bundle_dir.rglob("*")):
                if path.is_file():
                    zf.write(path, arcname=str(Path("story_video_handoff") / path.relative_to(bundle_dir)))
    bundle.seek(0)
    return bundle.getvalue()
