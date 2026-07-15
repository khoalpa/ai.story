from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Iterable

from image.app_api import RenderImageRequest, RenderImageResult
from image.provider_runtime import (
    render_with_provider,
)
from image.workflow_routing import infer_prompt_kind
from image.handoff import read_story_handoff, write_video_handoff

ProgressCallback = Callable[[float, str], None]

PROMPT_CARD_SEQUENCE: tuple[str, ...] = (
    "cover",
    "scene",
    "intro",
    "greeting",
    "opening",
    "introduction",
    "development",
    "climax",
    "falling",
    "ending",
    "farewell",
    "outro",
)

_PROMPT_CARD_SEQUENCE_INDEX = {slot: index for index, slot in enumerate(PROMPT_CARD_SEQUENCE)}
_PROMPT_CARD_ALIASES = {
    "intro_card": "intro",
    "outro_card": "outro",
}


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


def _existing_version_indices(directory: Path, *, stem: str) -> set[int]:
    versions: set[int] = set()
    for pattern in (f"{stem}.png", f"{stem}_*.png"):
        for path in directory.glob(pattern):
            version = _version_index_from_path(path, stem=stem)
            if version is not None:
                versions.add(version)
    return versions


def _next_run_version_index(directory: Path) -> int:
    versions = _existing_version_indices(directory, stem="cover") | _existing_version_indices(directory, stem="scene")
    if not versions:
        return 0
    return max(versions) + 1


def _versioned_image_name(stem: str, version_index: int) -> str:
    if version_index <= 0:
        return f"{stem}.png"
    return f"{stem}_{version_index}.png"


def _generated_output_variants(primary_output: Path) -> list[Path]:
    outputs: list[Path] = []
    if primary_output.is_file():
        outputs.append(primary_output)
    for candidate in sorted(primary_output.parent.glob(f"{primary_output.stem}_batch*{primary_output.suffix}")):
        if candidate.is_file() and candidate not in outputs:
            outputs.append(candidate)
    return outputs


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _image_key_from_prompt_file(prompt_file: Path) -> str:
    stem = prompt_file.stem
    if stem.endswith("_prompt"):
        stem = stem[: -len("_prompt")]
    return stem or prompt_file.stem


def _prompt_sort_key(prompt_file: Path) -> tuple[int, str]:
    slot = _image_key_from_prompt_file(prompt_file)
    slot = _PROMPT_CARD_ALIASES.get(slot, slot)
    return (_PROMPT_CARD_SEQUENCE_INDEX.get(slot, len(PROMPT_CARD_SEQUENCE)), prompt_file.name)


def _iter_root_scene_prompt_files(handoff_dir: Path) -> Iterable[Path]:
    reserved_names = {"cover_prompt.json", "scene_prompt.json"}
    for prompt_file in sorted(handoff_dir.glob("*_prompt.json"), key=_prompt_sort_key):
        if prompt_file.name in reserved_names:
            continue
        if prompt_file.is_file():
            yield prompt_file


def iter_prompt_files(handoff_dir: Path) -> Iterable[tuple[Path, dict[str, Any], Path]]:
    cover_prompt = handoff_dir / "cover_prompt.json"
    if cover_prompt.is_file():
        prompt_data = _load_json(cover_prompt)
        prompt_data["kind"] = infer_prompt_kind(prompt_data, cover_prompt)
        yield cover_prompt, prompt_data, handoff_dir / "cover.png"

    scene_prompt = handoff_dir / "scene_prompt.json"
    if scene_prompt.is_file():
        prompt_data = _load_json(scene_prompt)
        prompt_data["kind"] = infer_prompt_kind(prompt_data, scene_prompt)
        image_key = str(prompt_data.get("image_key") or "scene").strip()
        yield scene_prompt, prompt_data, handoff_dir / "images" / f"{image_key}.png"

    for prompt_file in _iter_root_scene_prompt_files(handoff_dir):
        prompt_data = _load_json(prompt_file)
        prompt_data["kind"] = infer_prompt_kind(prompt_data, prompt_file)
        image_key = str(prompt_data.get("image_key") or _image_key_from_prompt_file(prompt_file)).strip()
        yield prompt_file, prompt_data, handoff_dir / "images" / f"{image_key}.png"

    scene_prompt_dir = handoff_dir / "scene_prompts"
    if scene_prompt_dir.is_dir():
        for prompt_file in sorted(scene_prompt_dir.glob("*.json")):
            prompt_data = _load_json(prompt_file)
            prompt_data["kind"] = infer_prompt_kind(prompt_data, prompt_file)
            image_key = str(prompt_data.get("image_key") or prompt_file.stem).strip()
            yield prompt_file, prompt_data, handoff_dir / "images" / f"{image_key}.png"


def _apply_prompt_edit(prompt_data: dict[str, Any], prompt_edit: Any) -> dict[str, Any]:
    if isinstance(prompt_edit, str):
        patched = dict(prompt_data)
        patched["prompt"] = prompt_edit
        return patched
    if not isinstance(prompt_edit, dict):
        return prompt_data

    patched = dict(prompt_data)
    if "prompt" in prompt_edit:
        patched["prompt"] = str(prompt_edit.get("prompt") or "")
    if "negative_prompt" in prompt_edit:
        patched["negative_prompt"] = str(prompt_edit.get("negative_prompt") or "")

    provider_payload = dict(prompt_data.get("provider_payload") or {})
    if isinstance(prompt_edit.get("provider_payload"), dict):
        provider_payload.update(prompt_edit["provider_payload"])
    if provider_payload:
        patched["provider_payload"] = provider_payload
    return patched


def _emit_progress(progress_callback: ProgressCallback | None, fraction: float, message: str) -> None:
    if progress_callback is None:
        return
    progress_callback(max(0.0, min(1.0, float(fraction))) * 100.0, message)


def run_image_job(request: RenderImageRequest, progress_callback: ProgressCallback | None = None) -> RenderImageResult:
    handoff_dir = request.handoff_dir
    if handoff_dir.is_file():
        handoff_dir = read_story_handoff(handoff_dir).prompt_dir
    if not handoff_dir.is_dir():
        raise FileNotFoundError(f"Prompt directory not found: {handoff_dir}")

    output_dir = request.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    scenes_dir = output_dir / "images"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    run_version = _next_run_version_index(scenes_dir)
    cover_output = scenes_dir / _versioned_image_name("cover", run_version)

    manifest_data = {}
    manifest_path = handoff_dir / "manifest.json"
    if manifest_path.is_file():
        manifest_data = _load_json(manifest_path)

    prompt_items = list(iter_prompt_files(handoff_dir))
    if not prompt_items:
        raise FileNotFoundError(
            "Prompt directory does not contain any renderable prompt files. "
            "Expected cover_prompt.json, scene_prompt.json, *_prompt.json, or scene_prompts/*.json."
        )
    total_prompts = max(1, len(prompt_items))
    logs: list[str] = []
    generated: list[Path] = []
    generated_prompt_files: list[dict[str, Any]] = []

    settings = {
        "provider": request.provider,
        "width": request.width,
        "height": request.height,
        "steps": request.steps,
        "cfg": request.cfg,
        "sampler_name": request.sampler_name,
        "scheduler": request.scheduler,
        "seed": request.seed,
        "negative_prompt": request.negative_prompt,
        "local_model_id_or_path": request.local_model_id_or_path,
        "local_device": request.local_device,
        "local_dtype": request.local_dtype,
        "local_variant": request.local_variant,
        "local_use_safetensors": request.local_use_safetensors,
        "local_enable_attention_slicing": request.local_enable_attention_slicing,
        "local_enable_model_cpu_offload": request.local_enable_model_cpu_offload,
        "provider_payload": request.provider_payload,
        "workflow_json_file": request.workflow_json_file,
        "cover_workflow_json_file": request.cover_workflow_json_file,
        "scene_workflow_json_file": request.scene_workflow_json_file,
        "fallback_workflow_json_file": request.fallback_workflow_json_file or request.workflow_json_file,
        "auto_select_workflow_by_kind": request.auto_select_workflow_by_kind,
        "positive_prompt_node_id": request.positive_prompt_node_id,
        "negative_prompt_node_id": request.negative_prompt_node_id,
        "sampler_node_id": request.sampler_node_id,
        "latent_size_node_id": request.latent_size_node_id,
        "output_node_ids": request.output_node_ids,
        "poll_interval": request.poll_interval,
        "max_wait_s": request.max_wait_s,
    }

    if progress_callback is not None:
        _emit_progress(progress_callback, 0.01, f"Found {len(prompt_items)} prompt(s)")

    for prompt_index, (prompt_path, prompt_data, suggested_output) in enumerate(prompt_items, start=1):
        override_key = str(prompt_path.relative_to(handoff_dir)).replace('\\', '/')
        prompt_edit = (request.prompt_overrides or {}).get(override_key)
        prompt_data = _apply_prompt_edit(prompt_data, prompt_edit)

        prompt_base = (prompt_index - 1) / total_prompts
        prompt_span = 1.0 / total_prompts
        prompt_detail = f"{prompt_index}/{total_prompts} {prompt_path.name}"
        _emit_progress(progress_callback, prompt_base + 0.03 * prompt_span, f"Preparing {prompt_detail}")

        if prompt_data.get("kind") == "cover":
            target = cover_output
        else:
            image_stem = Path(suggested_output.name).stem or "scene"
            target = scenes_dir / _versioned_image_name(image_stem, run_version)
        target.parent.mkdir(parents=True, exist_ok=True)
        logs.append(f"Render {prompt_path.name} -> {target.name}")
        _emit_progress(progress_callback, prompt_base + 0.1 * prompt_span, f"Rendering {prompt_detail} -> {target.name}")
        provider_logs = render_with_provider(
            provider=request.provider,
            base_url=request.base_url,
            api_key=request.api_key,
            prompt_data=prompt_data,
            prompt_path=prompt_path,
            output_path=target,
            settings=settings,
            progress_callback=lambda fraction, message, *, _base=prompt_base, _span=prompt_span: _emit_progress(
                progress_callback,
                _base + max(0.0, min(1.0, float(fraction) / 100.0)) * _span,
                message,
            ) if progress_callback is not None else None,
        )
        logs.extend(provider_logs)
        prompt_outputs = _generated_output_variants(target)
        generated.extend(prompt_outputs)
        generated_prompt_files.append(
            {
                "prompt_file": str(prompt_path),
                "rel_path": override_key,
                "kind": str(prompt_data.get("kind") or ""),
                "primary_output": str(target),
                "generated_files": [str(path) for path in prompt_outputs],
            }
        )
        _emit_progress(progress_callback, prompt_base + prompt_span * 0.98, f"Finished {prompt_detail} -> {len(prompt_outputs)} image(s)")

    runtime_manifest = output_dir / "image_result_manifest.json"
    runtime_manifest.write_text(
        json.dumps(
            {
                "provider": request.provider,
                "handoff_dir": str(handoff_dir),
                "output_dir": str(output_dir),
                "cover_image": str(cover_output) if cover_output.is_file() else "",
                "scene_images_dir": str(scenes_dir),
                "generated_files": [str(p) for p in generated],
                "generated_prompt_files": generated_prompt_files,
                "source_manifest": manifest_data,
                "prompt_overrides": request.prompt_overrides,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_video_handoff(
        output_dir / "image_video_handoff.json",
        cover=cover_output if cover_output.is_file() else None,
        scenes=scenes_dir,
    )
    _emit_progress(progress_callback, 1.0, "Image generation completed")
    return RenderImageResult(
        provider=request.provider,
        output_dir=output_dir,
        cover_image=cover_output if cover_output.is_file() else None,
        scene_images_dir=scenes_dir,
        generated_files=generated,
        manifest_path=runtime_manifest,
        logs=logs,
    )

