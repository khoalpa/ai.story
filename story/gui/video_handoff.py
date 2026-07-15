from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from story.gui.image_prompts import build_story_slug
from story.image_sequence import ZONE_IMAGE_SEQUENCE
from story.paths import PROJECT_ROOT
from story.handoff import write_handoff


DEFAULT_OUTPUT_BASE = Path("output/story/video_handoff")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_output_base(output_base: str | Path = DEFAULT_OUTPUT_BASE) -> Path:
    base = Path(output_base)
    if not base.is_absolute():
        base = PROJECT_ROOT / base
    return base.resolve()


def materialize_story_handoff_bundle(*, authoring: dict[str, Any], image_prompts: dict[str, dict[str, Any]], output_base: str | Path = DEFAULT_OUTPUT_BASE) -> Path:
    bundle_dir = _resolve_output_base(output_base) / build_story_slug(authoring)
    scene_prompt_dir = bundle_dir / "scene_prompts"
    scene_images_dir = bundle_dir / "scene_images"
    scene_prompt_dir.mkdir(parents=True, exist_ok=True)
    scene_images_dir.mkdir(parents=True, exist_ok=True)

    cover_prompt = dict(image_prompts.get("cover") or {})
    cover_prompt.update({"kind": "cover", "slot": "cover", "image_key": "cover"})
    scene_prompt = dict(image_prompts.get("scene") or {})
    scene_prompt.update({"kind": "scene", "slot": "scene_overview", "image_key": "scene"})

    _write_json(bundle_dir / "cover_prompt.json", cover_prompt)
    _write_json(bundle_dir / "scene_prompt.json", scene_prompt)

    expected_scene_images = []
    for idx, zone_key in enumerate(ZONE_IMAGE_SEQUENCE, start=1):
        payload = dict(image_prompts.get(zone_key) or {})
        payload.update({"kind": "scene", "slot": zone_key, "image_key": zone_key})
        prompt_name = f"{idx:02d}_{zone_key}.json"
        _write_json(scene_prompt_dir / prompt_name, payload)
        expected_scene_images.append({
            "kind": "scene",
            "slot": zone_key,
            "image_key": zone_key,
            "prompt_file": f"scene_prompts/{prompt_name}",
            "expected_image_file": f"scene_images/{zone_key}.png",
        })

    readme_lines = ["Expected scene image filenames for Video slideshow:", *[f"- {zone}.png" for zone in ZONE_IMAGE_SEQUENCE]]
    (scene_images_dir / "README_expected_filenames.txt").write_text("\n".join(readme_lines), encoding="utf-8")

    manifest = {
        "story_title": ((authoring or {}).get("meta") or {}).get("title", ""),
        "bundle_dir": str(bundle_dir),
        "cover_prompt": {
            "kind": "cover",
            "slot": "cover",
            "prompt_file": "cover_prompt.json",
            "expected_image_file": "cover.png",
        },
        "scene_prompt": {
            "kind": "scene",
            "slot": "scene_overview",
            "prompt_file": "scene_prompt.json",
        },
        "scene_prompts_dir": "scene_prompts",
        "scene_images_dir": "scene_images",
        "expected_scene_images": expected_scene_images,
    }
    manifest_path = write_handoff(
        bundle_dir / "manifest.json",
        kind="story.image-handoff",
        artifacts={"prompt_dir": ".", "scene_images_dir": "scene_images"},
    )
    envelope = json.loads(manifest_path.read_text(encoding="utf-8"))
    envelope.update(manifest)
    _write_json(manifest_path, envelope)
    return bundle_dir
