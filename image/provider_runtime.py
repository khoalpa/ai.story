from __future__ import annotations

import base64
import copy
import io
import json
import os
import time
import warnings
from pathlib import Path
from typing import Any, Callable

import requests
from PIL import Image, ImageColor, ImageDraw, ImageOps

from image.runtime import package_root
from image.workflow_routing import resolve_workflow_file
from image.model_store import (
    configure_hf_runtime,
    list_local_models,
    provider_hub_snapshots_dir,
    provider_models_dir,
    provider_target_dir,
    resolve_model_reference,
)
from image.providers import get_sd_provider

_LOCAL_PIPELINE_CACHE: dict[tuple[Any, ...], Any] = {}
ProgressCallback = Callable[[float, str], None]


def _emit_progress(progress_callback: ProgressCallback | None, fraction: float, message: str) -> None:
    if progress_callback is None:
        return
    try:
        progress_callback(max(0.0, min(1.0, float(fraction))) * 100.0, message)
    except Exception:
        return


def _merge_prompt_settings(prompt_data: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    merged = dict(defaults)
    merged.update({
        "prompt": prompt_data.get("prompt") or defaults.get("prompt") or "",
        "negative_prompt": prompt_data.get("negative_prompt") or defaults.get("negative_prompt") or "",
        "width": int(defaults.get("width") or prompt_data.get("width") or 832),
        "height": int(defaults.get("height") or prompt_data.get("height") or 1472),
        "steps": int(defaults.get("steps") or prompt_data.get("steps") or 30),
        "cfg": float(defaults.get("cfg") or prompt_data.get("cfg") or 6.5),
        "sampler_name": defaults.get("sampler_name") or prompt_data.get("sampler_name") or "dpmpp_2m",
        "scheduler": defaults.get("scheduler") or prompt_data.get("scheduler") or "karras",
        "seed": int(defaults.get("seed") if defaults.get("seed") is not None else prompt_data.get("seed", -1)),
    })
    provider_payload = dict(prompt_data.get("provider_payload") or {})
    provider_payload.update(defaults.get("provider_payload") or {})
    merged["provider_payload"] = provider_payload
    return merged


def render_with_provider(
    *,
    provider: str,
    base_url: str,
    api_key: str,
    prompt_data: dict[str, Any],
    prompt_path: Path | None,
    output_path: Path,
    settings: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> list[str]:
    provider_meta = get_sd_provider(provider)
    renderer = provider_meta.renderer
    if renderer == "diffusers_local":
        return _render_via_diffusers_local(prompt_data, prompt_path, output_path, settings, progress_callback=progress_callback)
    if renderer == "a1111_remote":
        return _render_via_a1111(base_url, api_key, prompt_data, output_path, settings, progress_callback=progress_callback)
    if renderer == "comfyui_local":
        return _render_via_comfyui_local(prompt_data, prompt_path, output_path, settings, progress_callback=progress_callback)
    if renderer == "comfyui_remote":
        return _render_via_comfyui(base_url, api_key, prompt_data, prompt_path, output_path, settings, progress_callback=progress_callback)
    raise ValueError(f"Unsupported image provider renderer: {renderer}")


def local_provider_status(settings: dict[str, Any]) -> dict[str, Any]:
    provider_name = "image"
    local_provider = str(settings.get("provider") or "stable_diffusion_local").strip().lower()
    model_dir = provider_models_dir(provider_name, __file__)
    cache_env = configure_hf_runtime(provider=provider_name, module_file=__file__, allow_network=False)
    local_models = list_local_models(provider_name, __file__)
    lora_dir = provider_target_dir(provider_name, "lora_local", __file__)
    requested_model = str(settings.get("local_model_id_or_path") or os.getenv("AI_STUDIO_IMAGE_MODEL") or "").strip()
    provider_payload = dict(settings.get("provider_payload") or {})
    requested_lora = str(provider_payload.get("local_lora_model_id_or_path") or "").strip()
    resolved_model = ""
    resolved_lora = ""
    if requested_model:
        try:
            resolved_model, _ = resolve_model_reference(requested_model, provider=provider_name, module_file=__file__, allow_network=False)
        except Exception:
            resolved_model = ""
    if requested_lora:
        try:
            resolved_lora, _ = resolve_model_reference(requested_lora, provider=provider_name, module_file=__file__, allow_network=False)
        except Exception:
            resolved_lora = ""
    return {
        "provider": local_provider,
        "models_dir": str(model_dir),
        "lora_dir": str(lora_dir),
        "cache_dir": str(cache_env.get("HF_HOME") or ""),
        "local_models": local_models,
        "model_count": len(local_models),
        "requested_model": requested_model,
        "resolved_model": resolved_model,
        "requested_lora": requested_lora,
        "resolved_lora": resolved_lora,
    }


def preload_local_provider(settings: dict[str, Any]) -> list[str]:
    local_settings = _coerce_comfyui_local_settings(settings=settings, prompt_data={}, prompt_path=None)
    pipe, model_ref, device, dtype_name = _get_local_pipeline(local_settings, mode="txt2img")
    logs = [
        f"Local preload model={model_ref}",
        f"Local preload device={device}",
        f"Local preload dtype={dtype_name}",
        f"Local preload pipeline={pipe.__class__.__name__}",
    ]
    provider_payload = dict(local_settings.get("provider_payload") or {})
    mode = str(provider_payload.get("local_generation_mode") or "txt2img").strip().lower()
    if mode == "img2img":
        img_pipe, _, _, _ = _get_local_pipeline(local_settings, mode="img2img")
        logs.append(f"Local preload img2img_pipeline={img_pipe.__class__.__name__}")
    if mode == "controlnet":
        ctrl_pipe, _, _, _ = _get_local_pipeline(local_settings, mode="controlnet")
        logs.append(f"Local preload controlnet_pipeline={ctrl_pipe.__class__.__name__}")
    if mode == "inpaint":
        inpaint_pipe, _, _, _ = _get_local_pipeline(local_settings, mode="inpaint")
        logs.append(f"Local preload inpaint_pipeline={inpaint_pipe.__class__.__name__}")
    return logs




def _workflow_node_map(workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(node_id): dict(node or {}) for node_id, node in (workflow or {}).items()}


def _workflow_input_ref(value: Any) -> str | None:
    if isinstance(value, (list, tuple)) and value:
        return str(value[0])
    if isinstance(value, str) and value.isdigit():
        return value
    return None


def _workflow_find_nodes(workflow: dict[str, Any], class_names: set[str]) -> list[tuple[str, dict[str, Any]]]:
    nodes = _workflow_node_map(workflow)
    return [(node_id, node) for node_id, node in nodes.items() if str((node or {}).get("class_type") or "") in class_names]


def _workflow_collect_texts_from_node(workflow: dict[str, Any], node_id: str, *, visited: set[str] | None = None) -> list[str]:
    nodes = _workflow_node_map(workflow)
    node = nodes.get(str(node_id)) or {}
    visited = visited or set()
    if str(node_id) in visited:
        return []
    visited.add(str(node_id))
    texts: list[str] = []
    inputs = dict(node.get("inputs") or {})
    class_type = str(node.get("class_type") or "")
    direct_keys = ("text", "prompt", "string", "value")
    for key in direct_keys:
        value = inputs.get(key)
        if isinstance(value, str) and value.strip():
            texts.append(value.strip())
    if class_type in {"CLIPTextEncode", "CLIPTextEncodeSDXL", "BNK_CLIPTextEncodeAdvanced", "CLIPTextEncodeFlux"}:
        value = inputs.get("text")
        if isinstance(value, str) and value.strip():
            texts.append(value.strip())
    for value in inputs.values():
        ref = _workflow_input_ref(value)
        if ref:
            texts.extend(_workflow_collect_texts_from_node(workflow, ref, visited=visited))
    # dedupe preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for item in texts:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def parse_comfyui_workflow_file(workflow_file: str | Path) -> dict[str, Any]:
    workflow_path = Path(workflow_file).expanduser()
    if not workflow_path.is_file():
        raise FileNotFoundError(f"KhÃƒÂ´ng tÃƒÂ¬m thÃ¡ÂºÂ¥y workflow JSON: {workflow_path}")
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    return parse_comfyui_workflow(workflow, workflow_path=workflow_path)


def parse_comfyui_workflow(workflow: dict[str, Any], *, workflow_path: Path | None = None) -> dict[str, Any]:
    nodes = _workflow_node_map(workflow)
    class_names = {str((node or {}).get("class_type") or "") for node in nodes.values()}
    sampler_types = {"KSampler", "KSamplerAdvanced", "KSamplerSelect", "SamplerCustom", "SamplerCustomAdvanced"}
    checkpoint_types = {"CheckpointLoaderSimple", "CheckpointLoader", "UNETLoader", "TripleCLIPLoader", "DualCLIPLoader", "VAELoader", "LoraLoader", "LoRALoader", "Power Lora Loader (rgthree)"}
    prompt_types = {"CLIPTextEncode", "CLIPTextEncodeSDXL", "BNK_CLIPTextEncodeAdvanced", "CLIPTextEncodeFlux"}
    controlnet_types = {
        "ControlNetLoader", "ControlNetLoaderAdvanced", "DiffControlNetLoader",
        "ControlNetApply", "ControlNetApplyAdvanced", "ACN_AdvancedControlNetApply",
        "ControlNetApplySD3", "ControlNetApplyFlux", "SetUnionControlNetType",
    }
    image_types = {"LoadImage", "LoadImageMask", "ImageOnlyCheckpointLoader", "LoadImageOutput"}
    inpaint_types = {"InpaintModelConditioning", "VAEEncodeForInpaint", "SetLatentNoiseMask", "LoadImageMask"}
    size_types = {"EmptyLatentImage"}
    supportive_types = {"SaveImage", "SaveImageWebsocket", "VAEEncode", "VAEEncodeTiled", "ImageToLatent"}
    ignored_types = {
        "PreviewImage", "Note", "Reroute", "Reroute (rgthree)", "PrimitiveNode", "Fast Groups Bypasser",
        "ConditioningCombine", "ConditioningConcat", "ConditioningAverage", "ConditioningSetMask",
        "LatentUpscale", "LatentBatch", "ImageScale", "ResizeImage", "ImageScaleBy", "ImageResize+",
        "ToBasicPipe", "FromBasicPipe", "Anything Everywhere", "Anything Everywhere3",
    }
    known_types = sampler_types | checkpoint_types | prompt_types | controlnet_types | image_types | inpaint_types | size_types | supportive_types | ignored_types

    summary: dict[str, Any] = {
        "workflow_path": str(workflow_path) if workflow_path else "",
        "node_count": len(nodes),
        "class_names": sorted(class_names),
        "samplers": [],
        "checkpoints": [],
        "loras": [],
        "vae": [],
        "controlnet_models": [],
        "image_inputs": [],
        "mask_inputs": [],
        "prompt_candidates": [],
        "negative_prompt_candidates": [],
        "positive_prompt": "",
        "negative_prompt": "",
        "width": None,
        "height": None,
        "steps": None,
        "cfg": None,
        "sampler_name": "",
        "scheduler": "",
        "seed": None,
        "local_model_id_or_path": "",
        "provider_payload": {},
        "detected_mode": "txt2img",
        "node_summary": [],
        "unsupported_class_names": [],
        "ignored_class_names": [],
        "unsupported_nodes": [],
        "ignored_nodes": [],
    }

    # sampler and latent sizes
    for node_id, node in nodes.items():
        class_type = str(node.get("class_type") or "")
        inputs = dict(node.get("inputs") or {})
        if class_type in sampler_types:
            sampler_entry = {"id": node_id, "class_type": class_type}
            for key in ("seed", "steps", "cfg", "sampler_name", "scheduler", "denoise"):
                if inputs.get(key) is not None:
                    sampler_entry[key] = inputs.get(key)
            summary["samplers"].append(sampler_entry)
            if summary["seed"] is None and inputs.get("seed") is not None:
                summary["seed"] = int(inputs.get("seed") or -1)
            if summary["steps"] is None and inputs.get("steps") is not None:
                summary["steps"] = int(inputs.get("steps") or 30)
            if summary["cfg"] is None and inputs.get("cfg") is not None:
                summary["cfg"] = float(inputs.get("cfg") or 6.5)
            if not summary["sampler_name"] and inputs.get("sampler_name") is not None:
                summary["sampler_name"] = str(inputs.get("sampler_name") or "")
            if not summary["scheduler"] and inputs.get("scheduler") is not None:
                summary["scheduler"] = str(inputs.get("scheduler") or "")
            pos_ref = _workflow_input_ref(inputs.get("positive"))
            neg_ref = _workflow_input_ref(inputs.get("negative"))
            if pos_ref and not summary["positive_prompt"]:
                texts = _workflow_collect_texts_from_node(workflow, pos_ref)
                if texts:
                    summary["positive_prompt"] = texts[0]
                    summary["prompt_candidates"].extend(texts)
            if neg_ref and not summary["negative_prompt"]:
                texts = _workflow_collect_texts_from_node(workflow, neg_ref)
                if texts:
                    summary["negative_prompt"] = texts[0]
                    summary["negative_prompt_candidates"].extend(texts)

        if class_type == "EmptyLatentImage":
            if summary["width"] is None and inputs.get("width") is not None:
                summary["width"] = int(inputs.get("width") or 512)
            if summary["height"] is None and inputs.get("height") is not None:
                summary["height"] = int(inputs.get("height") or 512)

        if class_type in checkpoint_types:
            model_name = str(inputs.get("ckpt_name") or inputs.get("model_name") or inputs.get("unet_name") or inputs.get("clip_name1") or "").strip()
            if class_type in {"LoraLoader", "LoRALoader", "Power Lora Loader (rgthree)"}:
                lora_name = str(inputs.get("lora_name") or inputs.get("name") or model_name).strip()
                if lora_name:
                    summary["loras"].append({"id": node_id, "class_type": class_type, "name": lora_name})
            elif class_type == "VAELoader":
                vae_name = str(inputs.get("vae_name") or model_name).strip()
                if vae_name:
                    summary["vae"].append({"id": node_id, "class_type": class_type, "name": vae_name})
            else:
                if model_name:
                    summary["checkpoints"].append({"id": node_id, "class_type": class_type, "name": model_name})
                    if not summary["local_model_id_or_path"]:
                        summary["local_model_id_or_path"] = model_name

        if class_type in prompt_types:
            text_value = str(inputs.get("text") or inputs.get("prompt") or "").strip()
            if text_value:
                title_hint = f"{node.get('title') or ''} {node.get('_meta', {}).get('title') if isinstance(node.get('_meta'), dict) else ''}".lower()
                entry = {"id": node_id, "class_type": class_type, "text": text_value}
                if "neg" in title_hint:
                    summary["negative_prompt_candidates"].append(text_value)
                    if not summary["negative_prompt"]:
                        summary["negative_prompt"] = text_value
                else:
                    summary["prompt_candidates"].append(text_value)
                    if not summary["positive_prompt"]:
                        summary["positive_prompt"] = text_value
                summary["node_summary"].append(entry)

        if class_type in controlnet_types:
            model_name = str(inputs.get("control_net_name") or inputs.get("model_name") or "").strip()
            if model_name:
                summary["controlnet_models"].append({"id": node_id, "class_type": class_type, "name": model_name})

        if class_type in image_types:
            image_name = str(inputs.get("image") or inputs.get("filename") or inputs.get("path") or "").strip()
            if image_name:
                target_key = "mask_inputs" if class_type == "LoadImageMask" or "mask" in image_name.lower() else "image_inputs"
                summary[target_key].append({"id": node_id, "class_type": class_type, "name": image_name})

        if class_type in inpaint_types and summary["detected_mode"] == "txt2img":
            summary["detected_mode"] = "inpaint"

    if any(name in class_names for name in controlnet_types):
        summary["detected_mode"] = "controlnet"
    elif any(name in class_names for name in inpaint_types):
        summary["detected_mode"] = "inpaint"
    elif summary["image_inputs"] or any(name in class_names for name in {"VAEEncode", "VAEEncodeTiled", "ImageToLatent", "LoadImage"}):
        summary["detected_mode"] = "img2img"

    # fallbacks for prompt values if sampler traversal didn't find them
    if not summary["positive_prompt"] and summary["prompt_candidates"]:
        summary["positive_prompt"] = summary["prompt_candidates"][0]
    if not summary["negative_prompt"] and summary["negative_prompt_candidates"]:
        summary["negative_prompt"] = summary["negative_prompt_candidates"][0]

    provider_payload = dict(summary.get("provider_payload") or {})
    provider_payload["local_generation_mode"] = summary["detected_mode"]
    if summary["controlnet_models"]:
        provider_payload["local_controlnet_model_id_or_path"] = str(summary["controlnet_models"][0].get("name") or "")
    if summary["image_inputs"]:
        first_image_input = str(summary["image_inputs"][0].get("name") or "")
        provider_payload.setdefault("local_init_image", first_image_input)
        if summary["detected_mode"] == "inpaint":
            provider_payload.setdefault("local_inpaint_image", first_image_input)
    if summary["mask_inputs"]:
        provider_payload.setdefault("local_inpaint_mask", str(summary["mask_inputs"][0].get("name") or ""))
    summary["provider_payload"] = provider_payload

    unsupported_class_names = sorted(name for name in class_names if name and name not in known_types)
    ignored_class_names = sorted(name for name in class_names if name and name in ignored_types)
    summary["unsupported_class_names"] = unsupported_class_names
    summary["ignored_class_names"] = ignored_class_names
    if unsupported_class_names:
        summary["unsupported_nodes"] = [
            {"id": node_id, "class_type": str((node or {}).get("class_type") or "")}
            for node_id, node in nodes.items()
            if str((node or {}).get("class_type") or "") in unsupported_class_names
        ]
    if ignored_class_names:
        summary["ignored_nodes"] = [
            {"id": node_id, "class_type": str((node or {}).get("class_type") or "")}
            for node_id, node in nodes.items()
            if str((node or {}).get("class_type") or "") in ignored_class_names
        ]

    # compact node summary for GUI preview
    node_summary = []
    interesting_types = sampler_types | checkpoint_types | prompt_types | controlnet_types | image_types | inpaint_types | size_types | supportive_types
    for node_id, node in nodes.items():
        class_type = str(node.get("class_type") or "")
        if class_type not in interesting_types:
            continue
        inputs = dict(node.get("inputs") or {})
        compact_inputs = {}
        for key in ("text", "ckpt_name", "model_name", "control_net_name", "image", "filename", "width", "height", "steps", "cfg", "sampler_name", "scheduler", "seed", "denoise"):
            if inputs.get(key) is not None:
                compact_inputs[key] = inputs.get(key)
        node_summary.append({"id": node_id, "class_type": class_type, "inputs": compact_inputs})
    summary["node_summary"] = node_summary
    # dedupe some arrays
    for key in ("prompt_candidates", "negative_prompt_candidates"):
        seen = set()
        vals = []
        for item in summary[key]:
            if item and item not in seen:
                seen.add(item)
                vals.append(item)
        summary[key] = vals
    return summary


def parse_comfyui_workflow_preview(workflow_file: str | Path) -> dict[str, Any]:
    parsed = parse_comfyui_workflow_file(workflow_file)
    return {
        "workflow_path": parsed.get("workflow_path") or "",
        "node_count": parsed.get("node_count") or 0,
        "detected_mode": parsed.get("detected_mode") or "txt2img",
        "local_model_id_or_path": parsed.get("local_model_id_or_path") or "",
        "positive_prompt": parsed.get("positive_prompt") or "",
        "negative_prompt": parsed.get("negative_prompt") or "",
        "width": parsed.get("width"),
        "height": parsed.get("height"),
        "steps": parsed.get("steps"),
        "cfg": parsed.get("cfg"),
        "sampler_name": parsed.get("sampler_name") or "",
        "scheduler": parsed.get("scheduler") or "",
        "seed": parsed.get("seed"),
        "controlnet_models": parsed.get("controlnet_models") or [],
        "image_inputs": parsed.get("image_inputs") or [],
        "mask_inputs": parsed.get("mask_inputs") or [],
        "loras": parsed.get("loras") or [],
        "vae": parsed.get("vae") or [],
        "checkpoints": parsed.get("checkpoints") or [],
        "node_summary": parsed.get("node_summary") or [],
        "unsupported_class_names": parsed.get("unsupported_class_names") or [],
        "ignored_class_names": parsed.get("ignored_class_names") or [],
        "unsupported_nodes": parsed.get("unsupported_nodes") or [],
        "ignored_nodes": parsed.get("ignored_nodes") or [],
    }

def _find_workflow_node_ids(workflow: dict[str, Any], class_names: set[str]) -> list[str]:
    results: list[str] = []
    for node_id, node in (workflow or {}).items():
        class_type = str((node or {}).get("class_type") or "")
        if class_type in class_names:
            results.append(str(node_id))
    return results


def _extract_comfyui_local_settings_from_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    parsed = parse_comfyui_workflow(workflow)
    extracted: dict[str, Any] = {
        "prompt": parsed.get("positive_prompt") or "",
        "negative_prompt": parsed.get("negative_prompt") or "",
        "local_model_id_or_path": parsed.get("local_model_id_or_path") or "",
        "provider_payload": dict(parsed.get("provider_payload") or {}),
    }
    for key in ("width", "height", "steps", "cfg", "sampler_name", "scheduler", "seed"):
        if parsed.get(key) is not None:
            extracted[key] = parsed.get(key)
    return extracted


def _coerce_comfyui_local_settings(*, settings: dict[str, Any], prompt_data: dict[str, Any], prompt_path: Path | None) -> dict[str, Any]:
    provider = str(settings.get("provider") or "").strip().lower()
    if provider != "comfyui_local":
        return dict(settings)
    workflow_file = resolve_workflow_file(prompt_data=prompt_data, prompt_path=prompt_path, settings=settings)
    if not workflow_file:
        raise ValueError("ChÃ†Â°a cÃ¡ÂºÂ¥u hÃƒÂ¬nh workflow JSON cho comfyui_local.")
    workflow_path = Path(workflow_file)
    if not workflow_path.is_file():
        raise FileNotFoundError(f"KhÃƒÂ´ng tÃƒÂ¬m thÃ¡ÂºÂ¥y workflow JSON cho comfyui_local: {workflow_path}")
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    extracted = parse_comfyui_workflow(workflow, workflow_path=workflow_path)
    merged = dict(settings)
    provider_payload = dict(extracted.get("provider_payload") or {})
    provider_payload.update(dict(settings.get("provider_payload") or {}))
    merged["provider_payload"] = provider_payload
    for key in ("prompt", "negative_prompt", "width", "height", "steps", "cfg", "sampler_name", "scheduler", "seed"):
        if not merged.get(key) and extracted.get(key) is not None:
            merged[key] = extracted.get(key)
    if not str(merged.get("local_model_id_or_path") or "").strip():
        merged["local_model_id_or_path"] = str(extracted.get("local_model_id_or_path") or "")
    if prompt_path is not None:
        merged["workflow_json_file"] = str(workflow_path)
    return merged


def _render_via_comfyui_local(
    prompt_data: dict[str, Any],
    prompt_path: Path | None,
    output_path: Path,
    settings: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> list[str]:
    local_settings = _coerce_comfyui_local_settings(settings=settings, prompt_data=prompt_data, prompt_path=prompt_path)
    logs = [f"ComfyUI local workflow={local_settings.get('workflow_json_file')}", "ComfyUI local execution=headless/internal"]
    logs.extend(_render_via_diffusers_local(prompt_data, prompt_path, output_path, local_settings, progress_callback=progress_callback))
    return logs



# ---------- Remote A1111 ----------


def _render_via_a1111(
    base_url: str,
    api_key: str,
    prompt_data: dict[str, Any],
    output_path: Path,
    settings: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> list[str]:
    cfg = _merge_prompt_settings(prompt_data, settings)
    headers = {"Content-Type": "application/json"}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    payload = {
        "prompt": cfg["prompt"],
        "negative_prompt": cfg["negative_prompt"],
        "width": cfg["width"],
        "height": cfg["height"],
        "steps": cfg["steps"],
        "cfg_scale": cfg["cfg"],
        "sampler_name": cfg["sampler_name"],
        "seed": cfg["seed"],
    }
    payload.update(dict(cfg.get("provider_payload") or {}))
    _emit_progress(progress_callback, 0.05, f"Posting {output_path.name} to A1111")
    resp = requests.post(f"{base_url.rstrip('/')}/sdapi/v1/txt2img", headers=headers, json=payload, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    images = data.get("images") or []
    if not images:
        raise RuntimeError("A1111-compatible API khÃƒÂ´ng trÃ¡ÂºÂ£ vÃ¡Â»Â Ã¡ÂºÂ£nh nÃƒÂ o.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []
    for index, encoded_image in enumerate(images, start=1):
        target = output_path if index == 1 else output_path.with_name(f"{output_path.stem}_batch{index:02d}{output_path.suffix}")
        target.write_bytes(base64.b64decode(encoded_image))
        saved_paths.append(target)
    _emit_progress(progress_callback, 1.0, f"Saved {len(saved_paths)} image(s) for {output_path.name}")
    return [f"A1111 txt2img -> {path}" for path in saved_paths]


# ---------- Local diffusers runtime ----------


def _resolve_local_dtype(torch_mod: Any, dtype_name: str, *, device: str) -> Any:
    name = str(dtype_name or "auto").strip().lower()
    if name in {"auto", ""}:
        if device == "cuda":
            if hasattr(torch_mod, "bfloat16") and getattr(torch_mod.cuda, "is_bf16_supported", lambda: False)():
                return getattr(torch_mod, "bfloat16")
            return getattr(torch_mod, "float16")
        if device == "mps":
            return getattr(torch_mod, "float16")
        return getattr(torch_mod, "float32")
    mapping = {
        "float16": getattr(torch_mod, "float16", None),
        "fp16": getattr(torch_mod, "float16", None),
        "float32": getattr(torch_mod, "float32", None),
        "fp32": getattr(torch_mod, "float32", None),
        "bfloat16": getattr(torch_mod, "bfloat16", None),
        "bf16": getattr(torch_mod, "bfloat16", None),
    }
    resolved = mapping.get(name)
    if resolved is None:
        raise ValueError(f"local_dtype khÃƒÂ´ng hÃ¡Â»Â£p lÃ¡Â»â€¡: {dtype_name}")
    return resolved


def _resolve_local_device(torch_mod: Any, requested: str) -> str:
    device = str(requested or "prefer_gpu").strip().lower()
    if device in {"", "auto", "prefer_gpu"}:
        if getattr(torch_mod.cuda, "is_available", lambda: False)():
            return "cuda"
        mps_backend = getattr(torch_mod.backends, "mps", None)
        if mps_backend is not None and getattr(mps_backend, "is_available", lambda: False)():
            return "mps"
        return "cpu"
    return device


def _maybe_apply_scheduler(pipe: Any, scheduler_name: str) -> str:
    name = str(scheduler_name or "").strip().lower()
    if not name:
        return "default"
    try:
        from diffusers import DPMSolverMultistepScheduler, EulerAncestralDiscreteScheduler, EulerDiscreteScheduler, UniPCMultistepScheduler
    except Exception:
        return "default"

    scheduler_map = {
        "dpmpp_2m": DPMSolverMultistepScheduler,
        "dpm++ 2m": DPMSolverMultistepScheduler,
        "dpmpp_2m_karras": DPMSolverMultistepScheduler,
        "euler": EulerDiscreteScheduler,
        "euler_a": EulerAncestralDiscreteScheduler,
        "euler ancestral": EulerAncestralDiscreteScheduler,
        "unipc": UniPCMultistepScheduler,
    }
    scheduler_cls = scheduler_map.get(name)
    if scheduler_cls is None:
        return "default"
    pipe.scheduler = scheduler_cls.from_config(pipe.scheduler.config)
    return scheduler_cls.__name__


def _resolve_path(path_like: str | Path | None, *, prompt_path: Path | None) -> Path | None:
    if path_like is None:
        return None
    raw = str(path_like).strip()
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    if candidate.is_absolute() and candidate.exists():
        return candidate
    search_roots: list[Path] = []
    if prompt_path is not None:
        search_roots.append(prompt_path.parent)
        if prompt_path.parent.parent.exists():
            search_roots.append(prompt_path.parent.parent)
    search_roots.append(package_root(__file__).parent)
    search_roots.append(Path.cwd())
    for root in search_roots:
        probe = (root / candidate).resolve()
        if probe.exists():
            return probe
    return candidate if candidate.exists() else None


def _load_pil_image(path_like: str | Path | None, *, prompt_path: Path | None, convert: str = "RGB") -> Image.Image | None:
    resolved = _resolve_path(path_like, prompt_path=prompt_path)
    if resolved is None or not resolved.is_file():
        return None
    with Image.open(resolved) as img:
        return img.convert(convert)


def _load_bundle_manifest(prompt_path: Path | None) -> dict[str, Any]:
    if prompt_path is None:
        return {}
    bundle_dir = prompt_path.parent.parent if prompt_path.parent.name == "scene_prompts" else prompt_path.parent
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.is_file():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _expected_image_from_manifest(prompt_path: Path | None, prompt_data: dict[str, Any], *, asset_kind: str) -> str:
    manifest = _load_bundle_manifest(prompt_path)
    if not manifest:
        return ""
    rel_path = ""
    if prompt_path is not None:
        bundle_dir = prompt_path.parent.parent if prompt_path.parent.name == "scene_prompts" else prompt_path.parent
        try:
            rel_path = str(prompt_path.relative_to(bundle_dir)).replace('\\', '/')
        except Exception:
            rel_path = prompt_path.name
    if asset_kind == "init_image":
        cover_prompt = manifest.get("cover_prompt") or {}
        if rel_path == str(cover_prompt.get("prompt_file") or "cover_prompt.json"):
            return str(cover_prompt.get("expected_image_file") or "")
        for item in manifest.get("expected_scene_images") or []:
            if rel_path == str(item.get("prompt_file") or ""):
                return str(item.get("expected_image_file") or "")
        image_key = str(prompt_data.get("image_key") or "").strip()
        if image_key:
            return f"scene_images/{image_key}.png"
    if asset_kind == "mask_image":
        image_key = str(prompt_data.get("image_key") or "").strip()
        if image_key:
            return f"scene_masks/{image_key}.png"
    return ""


def _resolve_bundle_asset_path(*, prompt_path: Path | None, prompt_data: dict[str, Any], provider_payload: dict[str, Any], asset_kind: str) -> Path | None:
    specific_keys = {
        "init_image": ["local_init_image", "init_image", "image", "init_image_file", "source_image_file"],
        "control_image": ["local_control_image", "control_image", "control_image_file", "conditioning_image"],
        "inpaint_image": ["local_inpaint_image", "inpaint_image", "image", "source_image_file"],
        "mask_image": ["local_inpaint_mask", "inpaint_mask", "mask", "mask_image", "mask_image_file"],
    }
    prompt_assets = dict(prompt_data.get("assets") or {})
    candidates: list[Any] = []
    for key in specific_keys.get(asset_kind, []):
        candidates.append(provider_payload.get(key))
        candidates.append(prompt_data.get(key))
        candidates.append(prompt_assets.get(key))
    manifest_hint = _expected_image_from_manifest(prompt_path, prompt_data, asset_kind=asset_kind)
    if manifest_hint:
        candidates.append(manifest_hint)
    image_key = str(prompt_data.get("image_key") or "").strip()
    if asset_kind in {"init_image", "inpaint_image"}:
        if image_key:
            candidates.extend([f"scene_images/{image_key}.png", f"{image_key}.png", "cover.png"])
    elif asset_kind == "control_image":
        if image_key:
            candidates.extend([f"control_images/{image_key}.png", f"scene_images/{image_key}.png", f"{image_key}.png"])
    elif asset_kind == "mask_image":
        if image_key:
            candidates.extend([f"scene_masks/{image_key}.png", f"masks/{image_key}.png", f"{image_key}_mask.png"])
    for candidate in candidates:
        resolved = _resolve_path(candidate, prompt_path=prompt_path)
        if resolved is not None and resolved.is_file():
            return resolved
    return None


def _load_bundle_or_path_image(*, prompt_path: Path | None, prompt_data: dict[str, Any], provider_payload: dict[str, Any], asset_kind: str, convert: str = "RGB") -> tuple[Image.Image | None, str]:
    resolved = _resolve_bundle_asset_path(prompt_path=prompt_path, prompt_data=prompt_data, provider_payload=provider_payload, asset_kind=asset_kind)
    if resolved is None:
        return None, ""
    with Image.open(resolved) as img:
        return img.convert(convert), str(resolved)


def _image_to_bytes(img: Image.Image) -> bytes:
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    return bio.getvalue()


def _infer_single_file_pipeline_family(model_ref: str, configured_family: str) -> str:
    family = str(configured_family or "auto").strip().lower()
    if family in {"sd15", "sdxl"}:
        return family

    model_name = Path(model_ref).name.lower()
    hints = (model_ref.lower(), model_name)
    if any("sdxl" in item or "xl" in item for item in hints):
        return "sdxl"
    if any(any(token in item for token in ("sd15", "sd-1", "v1-5", "stable-diffusion-v1", "1.5")) for item in hints):
        return "sd15"
    return ""


def _tokenizer_max_length(pipe: Any) -> int:
    for attr in ("tokenizer", "tokenizer_2"):
        tokenizer = getattr(pipe, attr, None)
        max_len = getattr(tokenizer, "model_max_length", None)
        if isinstance(max_len, int) and 0 < max_len < 1000000:
            return int(max_len)
    return 77


def _count_prompt_tokens(text: str, tokenizer: Any, max_length: int) -> int | None:
    if tokenizer is None or not str(text or "").strip():
        return None
    try:
        encoded = tokenizer(str(text), truncation=False, add_special_tokens=True, return_attention_mask=False)
        input_ids = encoded.get("input_ids") if isinstance(encoded, dict) else getattr(encoded, "input_ids", None)
        if isinstance(input_ids, list) and input_ids and isinstance(input_ids[0], list):
            return len(input_ids[0])
        if isinstance(input_ids, list):
            return len(input_ids)
    except Exception:
        return None
    return None


def _estimate_prompt_tokens(text: str) -> int:
    raw = str(text or '').strip()
    if not raw:
        return 0
    import re
    return len(re.findall(r"\\w+|[^\\w\\s]", raw, flags=re.UNICODE))


def preview_prompt_shortening(text: str, *, limit: int = 77) -> dict[str, Any]:
    original = str(text or '').strip()
    before = _estimate_prompt_tokens(original)
    if not original:
        return {
            'original': original,
            'trimmed': original,
            'was_shortened': False,
            'before_tokens': before,
            'after_tokens': before,
            'limit': int(limit),
        }
    if before <= int(limit):
        return {
            'original': original,
            'trimmed': original,
            'was_shortened': False,
            'before_tokens': before,
            'after_tokens': before,
            'limit': int(limit),
        }

    best = original
    for candidate in _prioritized_clause_candidates(original):
        best = candidate
        count = _estimate_prompt_tokens(candidate)
        if count <= int(limit):
            return {
                'original': original,
                'trimmed': candidate,
                'was_shortened': True,
                'before_tokens': before,
                'after_tokens': count,
                'limit': int(limit),
            }

    clauses = [part.strip() for part in original.split(',') if part.strip()]
    if len(clauses) > 1:
        while len(clauses) > 1:
            candidate = ', '.join(clauses)
            best = candidate
            count = _estimate_prompt_tokens(candidate)
            if count <= int(limit):
                return {
                    'original': original,
                    'trimmed': candidate,
                    'was_shortened': True,
                    'before_tokens': before,
                    'after_tokens': count,
                    'limit': int(limit),
                }
            clauses.pop()

    words = best.split()
    while len(words) > 3:
        candidate = ' '.join(words)
        count = _estimate_prompt_tokens(candidate)
        if count <= int(limit):
            return {
                'original': original,
                'trimmed': candidate,
                'was_shortened': True,
                'before_tokens': before,
                'after_tokens': count,
                'limit': int(limit),
            }
        words.pop()

    fallback = ' '.join(original.split()[: max(3, min(12, len(original.split()))) ]).strip()
    after = _estimate_prompt_tokens(fallback)
    return {
        'original': original,
        'trimmed': fallback or original,
        'was_shortened': bool((fallback or original) != original),
        'before_tokens': before,
        'after_tokens': after,
        'limit': int(limit),
    }


def _prompt_clause_priority(index: int, clause: str) -> tuple[int, int]:
    text = str(clause or '').strip().lower()
    score = 0
    if index == 0:
        score += 120

    keyword_groups = {
        90: {
            'subject', 'character', 'person', 'portrait', 'woman', 'man', 'girl', 'boy', 'face', 'hero', 'product',
            'cat', 'dog', 'dragon', 'landscape', 'city', 'car', 'motorbike', 'motorcycle', 'house', 'building',
        },
        70: {
            'style', 'cinematic', 'anime', 'realistic', 'illustration', 'painting', 'photography', 'render', '3d',
            'comic', 'watercolor', 'oil painting', 'concept art',
        },
        55: {
            'camera', 'lens', 'shot on', 'full-frame', '85mm', '35mm', '50mm', 'depth of field', 'bokeh', 'close-up',
        },
        45: {
            'lighting', 'light', 'soft light', 'rim light', 'volumetric', 'golden hour', 'backlight', 'studio light',
            'cinematic lighting',
        },
        25: {
            'high detail', 'ultra detailed', 'high resolution', 'sharp', 'focus', 'composition', 'background',
        },
    }
    for weight, keywords in keyword_groups.items():
        if any(keyword in text for keyword in keywords):
            score += weight
    return score, -index


def _prioritized_clause_candidates(text: str) -> list[str]:
    clauses = [part.strip() for part in str(text or '').split(',') if part.strip()]
    if len(clauses) <= 1:
        return []
    ranked = sorted(range(len(clauses)), key=lambda idx: _prompt_clause_priority(idx, clauses[idx]), reverse=True)
    keep: list[int] = []
    candidates: list[str] = []
    for idx in ranked:
        keep.append(idx)
        candidate = ', '.join(clauses[i] for i in sorted(keep) if clauses[i].strip())
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return list(reversed(candidates))


def _shorten_prompt_to_fit(text: str, tokenizer: Any, max_length: int) -> tuple[str, bool, int | None, int | None]:
    original = str(text or "").strip()
    if not original or tokenizer is None:
        return original, False, None, None
    token_count = _count_prompt_tokens(original, tokenizer, max_length)
    if token_count is not None and token_count <= max_length:
        return original, False, token_count, token_count

    best = original
    for candidate in _prioritized_clause_candidates(original):
        candidate_count = _count_prompt_tokens(candidate, tokenizer, max_length)
        best = candidate
        if candidate_count is not None and candidate_count <= max_length:
            return candidate, True, token_count, candidate_count

    clauses = [part.strip() for part in original.split(',') if part.strip()]
    if len(clauses) > 1:
        while len(clauses) > 1:
            candidate = ', '.join(clauses)
            candidate_count = _count_prompt_tokens(candidate, tokenizer, max_length)
            best = candidate
            if candidate_count is not None and candidate_count <= max_length:
                return candidate, True, token_count, candidate_count
            clauses.pop()

    words = best.split()
    while len(words) > 3:
        candidate = ' '.join(words)
        candidate_count = _count_prompt_tokens(candidate, tokenizer, max_length)
        if candidate_count is not None and candidate_count <= max_length:
            return candidate, True, token_count, candidate_count
        words.pop()

    fallback_words = original.split()[: max(3, min(12, len(original.split())))]
    fallback = ' '.join(fallback_words).strip()
    fallback_count = _count_prompt_tokens(fallback, tokenizer, max_length)
    return fallback or original, True, token_count, fallback_count


def _prepare_prompt_pair_for_clip(
    pipe: Any,
    prompt: str,
    negative_prompt: str,
    logs: list[str],
    *,
    allow_auto_shorten: bool | None = None,
    allow_auto_shorten_prompt: bool = True,
    allow_auto_shorten_negative: bool = True,
) -> tuple[str, str | None]:
    if allow_auto_shorten is not None:
        allow_auto_shorten_prompt = bool(allow_auto_shorten)
        allow_auto_shorten_negative = bool(allow_auto_shorten)
    max_length = _tokenizer_max_length(pipe)
    tokenizer = getattr(pipe, 'tokenizer', None) or getattr(pipe, 'tokenizer_2', None)
    if tokenizer is None:
        raise RuntimeError(
            "Diffusers pipeline loaded without a tokenizer, so it cannot encode prompts. "
            "If you are using a .safetensors/.ckpt checkpoint, set Diffusers config repo "
            "to a local Diffusers model folder/cache snapshot that contains tokenizer files, "
            "or enable warm-cache/network once so Diffusers can prepare the missing components."
        )
    if allow_auto_shorten_prompt:
        prompt_value, prompt_shortened, original_tokens, final_tokens = _shorten_prompt_to_fit(prompt, tokenizer, max_length)
        if prompt_shortened:
            logs.append(
                f"Prompt auto-shortened for CLIP limit: {original_tokens or '?'} -> {final_tokens or '?'} tokens (max={max_length})"
            )
    else:
        prompt_value = str(prompt or "").strip()
        prompt_shortened = False
        original_tokens = _count_prompt_tokens(prompt_value, tokenizer, max_length)
        final_tokens = original_tokens
        if original_tokens is not None and original_tokens > max_length:
            logs.append(
                f"Prompt auto-shortening disabled; keeping prompt over CLIP limit: {original_tokens} tokens (max={max_length})"
            )
    negative_value = str(negative_prompt or '').strip() or None
    if negative_value:
        if allow_auto_shorten_negative:
            negative_value, negative_shortened, negative_original_tokens, negative_final_tokens = _shorten_prompt_to_fit(negative_value, tokenizer, max_length)
            if negative_shortened:
                logs.append(
                    f"Negative prompt auto-shortened for CLIP limit: {negative_original_tokens or '?'} -> {negative_final_tokens or '?'} tokens (max={max_length})"
                )
        else:
            negative_tokens = _count_prompt_tokens(negative_value, tokenizer, max_length)
            if negative_tokens is not None and negative_tokens > max_length:
                logs.append(
                    f"Negative prompt auto-shortening disabled; keeping prompt over CLIP limit: {negative_tokens} tokens (max={max_length})"
                )
    return prompt_value, negative_value


def _filtered_warning_messages(captured: list[warnings.WarningMessage]) -> list[str]:
    lines: list[str] = []
    for item in captured:
        message = str(item.message)
        if "Accessing `__path__`" in message:
            continue
        if "Siglip2ImageProcessorFast is deprecated" in message:
            continue
        lines.append(message)
    return lines


def _infer_local_diffusers_config_repo() -> Path | None:
    hub_root = provider_hub_snapshots_dir("image", __file__)
    if not hub_root.exists():
        return None
    for model_hint in ("stable-diffusion-v1-5", "stable-diffusion-xl-base-1.0"):
        for snapshot_root in hub_root.glob(f"models--*{model_hint.replace('/', '--')}*"):
            snapshots_dir = snapshot_root / "snapshots"
            if not snapshots_dir.is_dir():
                continue
            for snapshot in snapshots_dir.iterdir():
                if snapshot.is_dir() and (snapshot / "model_index.json").is_file():
                    return snapshot
    for snapshot in hub_root.glob("models--*/snapshots/*"):
        if snapshot.is_dir() and (snapshot / "model_index.json").is_file():
            return snapshot
    return None


def _prepare_single_file_kwargs(
    *,
    load_kwargs: dict[str, Any],
    original_config: str,
    diffusers_config_repo: str,
    allow_online_load: bool,
) -> dict[str, Any]:
    single_file_kwargs = dict(load_kwargs)

    resolved_diffusers_config_repo = _resolve_path(diffusers_config_repo, prompt_path=None)
    if resolved_diffusers_config_repo is not None and resolved_diffusers_config_repo.is_dir():
        single_file_kwargs["config"] = str(resolved_diffusers_config_repo.resolve())
    else:
        inferred_repo = _infer_local_diffusers_config_repo()
        if inferred_repo is not None:
            single_file_kwargs["config"] = str(inferred_repo.resolve())

    resolved_original_config = _resolve_path(original_config, prompt_path=None)
    if resolved_original_config is not None and resolved_original_config.is_file():
        single_file_kwargs["original_config"] = str(resolved_original_config.resolve())
    elif str(original_config or "").strip():
        raise FileNotFoundError(
            "KhÃƒÂ´ng tÃƒÂ¬m thÃ¡ÂºÂ¥y original_config_file cho single-file checkpoint: "
            f"{original_config}"
        )
    elif not allow_online_load:
        raise ValueError(
            "Single-file checkpoint Ã„â€˜ang chÃ¡ÂºÂ¡y offline nhÃ†Â°ng chÃ†Â°a cÃƒÂ³ original_config. "
            "HÃƒÂ£y cung cÃ¡ÂºÂ¥p Ã„â€˜Ã†Â°Ã¡Â»Âng dÃ¡ÂºÂ«n local tÃ¡Â»â€ºi file config gÃ¡Â»â€˜c (.yaml/.yml/.json), "
            "hoÃ¡ÂºÂ·c bÃ¡ÂºÂ­t warm-cache/online Ã„â€˜Ã¡Â»Æ’ diffusers tÃ¡Â»Â± tÃ¡ÂºÂ£i config phÃƒÂ¹ hÃ¡Â»Â£p."
        )

    return single_file_kwargs


def _load_local_lora_weights(pipe: Any, *, lora_ref: str, lora_scale: float) -> None:
    clean_ref = str(lora_ref or "").strip()
    if not clean_ref:
        return
    if not hasattr(pipe, "load_lora_weights"):
        raise RuntimeError("Pipeline hiÃ¡Â»â€¡n tÃ¡ÂºÂ¡i khÃƒÂ´ng hÃ¡Â»â€” trÃ¡Â»Â£ load_lora_weights().")
    path = Path(clean_ref)
    if path.is_file():
        _load_lora_weights_compat(pipe, str(path.parent), weight_name=path.name)
    else:
        _load_lora_weights_compat(pipe, clean_ref)
    _set_lora_adapter_scale_if_present(pipe, adapter_name="local_lora", lora_scale=float(lora_scale))


def _load_lora_weights_compat(pipe: Any, lora_ref: str, **kwargs: Any) -> None:
    try:
        pipe.load_lora_weights(lora_ref, adapter_name="local_lora", **kwargs)
    except TypeError as exc:
        message = str(exc)
        if "adapter_name" not in message and "unexpected keyword argument" not in message:
            raise
        pipe.load_lora_weights(lora_ref, **kwargs)


def _present_lora_adapter_names(pipe: Any) -> set[str]:
    names: set[str] = set()
    get_list_adapters = getattr(pipe, "get_list_adapters", None)
    if callable(get_list_adapters):
        try:
            adapters = get_list_adapters()
        except Exception:
            adapters = None
        if isinstance(adapters, dict):
            for value in adapters.values():
                if isinstance(value, str):
                    names.add(value)
                elif isinstance(value, (list, tuple, set)):
                    names.update(str(item) for item in value if str(item))
        elif isinstance(adapters, (list, tuple, set)):
            names.update(str(item) for item in adapters if str(item))
    peft_config = getattr(pipe, "peft_config", None)
    if isinstance(peft_config, dict):
        names.update(str(key) for key in peft_config.keys() if str(key))
    return names


def _set_lora_adapter_scale_if_present(pipe: Any, *, adapter_name: str, lora_scale: float) -> None:
    if not hasattr(pipe, "set_adapters"):
        return
    present = _present_lora_adapter_names(pipe)
    if present and adapter_name not in present:
        return
    try:
        pipe.set_adapters([adapter_name], adapter_weights=[float(lora_scale)])
    except ValueError as exc:
        message = str(exc)
        if "not in the list of present adapters" not in message:
            raise


def _build_local_pipeline(*, model_ref: str, device: str, dtype: Any, variant: str, use_safetensors: bool, mode: str, pipeline_family: str = "auto", original_config: str = "", diffusers_config_repo: str = "", controlnet_model_ref: str = "", lora_model_ref: str = "", lora_scale: float = 1.0, allow_network: bool = False, warm_cache: bool = False, disable_safety_checker: bool = False) -> Any:
    allow_online_load = bool(allow_network or warm_cache)
    cache_env = configure_hf_runtime(provider="image", module_file=__file__, allow_network=allow_online_load)
    cache_dir = cache_env.get("HF_HOME") or ""
    try:
        from diffusers import (
            AutoPipelineForImage2Image,
            AutoPipelineForInpainting,
            AutoPipelineForText2Image,
            ControlNetModel,
            StableDiffusionControlNetPipeline,
            StableDiffusionImg2ImgPipeline,
            StableDiffusionInpaintPipeline,
            StableDiffusionPipeline,
            StableDiffusionXLControlNetPipeline,
            StableDiffusionXLImg2ImgPipeline,
            StableDiffusionXLInpaintPipeline,
            StableDiffusionXLPipeline,
        )
    except Exception as exc:
        raise RuntimeError(
            "ThiÃ¡ÂºÂ¿u hoÃ¡ÂºÂ·c lÃ¡Â»â€”i runtime local image headless. HÃƒÂ£y kiÃ¡Â»Æ’m tra diffusers / transformers / accelerate / safetensors / torch vÃƒÂ  version tÃ†Â°Ã†Â¡ng thÃƒÂ­ch."
        ) from exc

    load_kwargs: dict[str, Any] = {
        "torch_dtype": dtype,
        "cache_dir": cache_dir,
        "local_files_only": not allow_online_load,
    }
    if variant.strip():
        load_kwargs["variant"] = variant.strip()
    if use_safetensors:
        load_kwargs["use_safetensors"] = True
    if disable_safety_checker:
        load_kwargs["safety_checker"] = None
        load_kwargs["requires_safety_checker"] = False

    def _resolve_pretrained_ref(ref: str) -> str:
        resolved_ref = _resolve_path(ref, prompt_path=None)
        if resolved_ref is not None and resolved_ref.exists():
            return str(resolved_ref.resolve())
        return ref

    def _load_single_file_pipeline(ref: str, *, requested_mode: str) -> Any:
        resolved_ref = _resolve_path(ref, prompt_path=None)
        if resolved_ref is None or not resolved_ref.is_file():
            raise FileNotFoundError(
                "KhÃƒÂ´ng tÃƒÂ¬m thÃ¡ÂºÂ¥y single-file checkpoint local: "
                f"{ref}"
            )
        family = _infer_single_file_pipeline_family(str(resolved_ref), pipeline_family)
        if not family:
            raise ValueError(
                "Model local dÃ¡ÂºÂ¡ng .safetensors/.ckpt cÃ¡ÂºÂ§n chÃ¡Â»Ân Ã„â€˜ÃƒÂºng pipeline family. "
                "HÃƒÂ£y Ã„â€˜Ã¡ÂºÂ·t local_pipeline_family = 'sd15' hoÃ¡ÂºÂ·c 'sdxl'."
            )
        pipeline_map = {
            ("sd15", "txt2img"): StableDiffusionPipeline,
            ("sd15", "img2img"): StableDiffusionImg2ImgPipeline,
            ("sd15", "inpaint"): StableDiffusionInpaintPipeline,
            ("sdxl", "txt2img"): StableDiffusionXLPipeline,
            ("sdxl", "img2img"): StableDiffusionXLImg2ImgPipeline,
            ("sdxl", "inpaint"): StableDiffusionXLInpaintPipeline,
        }
        pipeline_cls = pipeline_map.get((family, requested_mode))
        if pipeline_cls is None:
            raise ValueError(
                f"Single-file local pipeline chÃ†Â°a hÃ¡Â»â€” trÃ¡Â»Â£ mode={requested_mode!r} vÃ¡Â»â€ºi pipeline family={family!r}."
            )

        single_file_kwargs = _prepare_single_file_kwargs(
            load_kwargs=load_kwargs,
            original_config=original_config,
            diffusers_config_repo=diffusers_config_repo,
            allow_online_load=allow_online_load,
        )
        if not disable_safety_checker:
            single_file_kwargs["requires_safety_checker"] = False

        return pipeline_cls.from_single_file(
            str(resolved_ref.resolve()),
            **single_file_kwargs,
        )

    def _load_pipeline(factory: Any, ref: str, *, requested_mode: str) -> Any:
        resolved_ref = _resolve_path(ref, prompt_path=None)
        if resolved_ref is not None and resolved_ref.is_file() and resolved_ref.suffix.lower() in {".safetensors", ".ckpt"}:
            return _load_single_file_pipeline(str(resolved_ref), requested_mode=requested_mode)

        pretrained_ref = _resolve_pretrained_ref(ref)
        if not allow_online_load:
            pretrained_path = Path(pretrained_ref)
            if not pretrained_path.exists():
                raise FileNotFoundError(
                    "Model local khÃƒÂ´ng tÃ¡Â»â€œn tÃ¡ÂºÂ¡i trong mÃƒÂ¡y hoÃ¡ÂºÂ·c cache offline chÃ†Â°a cÃƒÂ³ sÃ¡ÂºÂµn: "
                    f"{ref}"
                )

        return factory.from_pretrained(pretrained_ref, **load_kwargs)

    if mode == "txt2img":
        pipe = _load_pipeline(AutoPipelineForText2Image, model_ref, requested_mode="txt2img")
    elif mode == "img2img":
        pipe = _load_pipeline(AutoPipelineForImage2Image, model_ref, requested_mode="img2img")
    elif mode == "inpaint":
        pipe = _load_pipeline(AutoPipelineForInpainting, model_ref, requested_mode="inpaint")
    elif mode == "controlnet":
        if not controlnet_model_ref.strip():
            raise ValueError("ThiÃ¡ÂºÂ¿u local_controlnet_model_id_or_path cho chÃ¡ÂºÂ¿ Ã„â€˜Ã¡Â»â„¢ ControlNet local.")
        ref_path = Path(model_ref)
        if ref_path.is_file() and ref_path.suffix.lower() in {".safetensors", ".ckpt"}:
            raise ValueError(
                "ControlNet local hiÃ¡Â»â€¡n chÃ¡Â»â€° hÃ¡Â»â€” trÃ¡Â»Â£ base model dÃ¡ÂºÂ¡ng Hugging Face repo hoÃ¡ÂºÂ·c thÃ†Â° mÃ¡Â»Â¥c diffusers, chÃ†Â°a hÃ¡Â»â€” trÃ¡Â»Â£ single-file checkpoint."
            )
        resolved_controlnet_ref = _resolve_pretrained_ref(controlnet_model_ref)
        if not allow_online_load and not Path(resolved_controlnet_ref).exists():
            raise FileNotFoundError(
                "ControlNet model local khÃƒÂ´ng tÃ¡Â»â€œn tÃ¡ÂºÂ¡i trong mÃƒÂ¡y hoÃ¡ÂºÂ·c cache offline chÃ†Â°a cÃƒÂ³ sÃ¡ÂºÂµn: "
                f"{controlnet_model_ref}"
            )

        controlnet = ControlNetModel.from_pretrained(
            resolved_controlnet_ref,
            torch_dtype=dtype,
            use_safetensors=use_safetensors,
            cache_dir=cache_dir,
            local_files_only=not allow_online_load,
        )

        resolved_model_ref = _resolve_pretrained_ref(model_ref)
        if not allow_online_load and not Path(resolved_model_ref).exists():
            raise FileNotFoundError(
                "Base model local khÃƒÂ´ng tÃ¡Â»â€œn tÃ¡ÂºÂ¡i trong mÃƒÂ¡y hoÃ¡ÂºÂ·c cache offline chÃ†Â°a cÃƒÂ³ sÃ¡ÂºÂµn: "
                f"{model_ref}"
            )

        pipeline_cls = StableDiffusionXLControlNetPipeline if "xl" in model_ref.lower() else StableDiffusionControlNetPipeline
        pipe = pipeline_cls.from_pretrained(
            resolved_model_ref,
            controlnet=controlnet,
            **load_kwargs,
        )
    else:
        raise ValueError(f"Local pipeline mode khÃƒÂ´ng hÃ¡Â»â€” trÃ¡Â»Â£: {mode}")

    if str(lora_model_ref or "").strip():
        _load_local_lora_weights(pipe, lora_ref=lora_model_ref, lora_scale=float(lora_scale or 1.0))

    if hasattr(pipe, "to"):
        pipe = pipe.to(device)
    return pipe


def _get_local_pipeline(settings: dict[str, Any], *, mode: str) -> tuple[Any, str, str, str]:
    try:
        import torch
    except Exception as exc:
        raise RuntimeError("ThiÃ¡ÂºÂ¿u torch cho local headless image provider. HÃƒÂ£y cÃƒÂ i torch phÃƒÂ¹ hÃ¡Â»Â£p mÃƒÂ¡y cÃ¡Â»Â§a bÃ¡ÂºÂ¡n.") from exc

    requested_model_ref = str(settings.get("local_model_id_or_path") or os.getenv("AI_STUDIO_IMAGE_MODEL") or "").strip()
    if not requested_model_ref:
        raise ValueError(
            "Stable Diffusion local chÃ†Â°a cÃƒÂ³ model Ã„â€˜Ã¡Â»Æ’ chÃ¡ÂºÂ¡y. "
            "HÃƒÂ£y cÃ¡ÂºÂ¥u hÃƒÂ¬nh local_model_id_or_path, vÃƒÂ­ dÃ¡Â»Â¥: "
            "runwayml/stable-diffusion-v1-5 hoÃ¡ÂºÂ·c image/local_models/sdxl"
        )
    allow_network = bool(settings.get("local_allow_network", False))
    model_ref, downloaded = resolve_model_reference(requested_model_ref, provider="image", module_file=__file__, allow_network=allow_network)
    device = _resolve_local_device(torch, str(settings.get("local_device") or "cuda"))
    dtype_name = str(settings.get("local_dtype") or "auto")
    dtype = _resolve_local_dtype(torch, dtype_name, device=device)
    variant = str(settings.get("local_variant") or "").strip()
    use_safetensors = bool(settings.get("local_use_safetensors", True))
    provider_payload = dict(settings.get("provider_payload") or {})
    pipeline_family = str(provider_payload.get("local_pipeline_family") or "auto").strip().lower()
    controlnet_request = str(provider_payload.get("local_controlnet_model_id_or_path") or "").strip()
    lora_enabled = bool(provider_payload.get("local_lora_enabled", False))
    lora_request = str(provider_payload.get("local_lora_model_id_or_path") or "").strip() if lora_enabled else ""
    lora_scale = float(provider_payload.get("local_lora_scale", 1.0) or 1.0)
    original_config = str(provider_payload.get("local_original_config_file") or "").strip()
    diffusers_config_repo = str(provider_payload.get("local_diffusers_config_repo") or "").strip()
    warm_cache = bool(provider_payload.get("local_warm_cache", False))
    disable_safety_checker = bool(provider_payload.get("local_disable_safety_checker", False))
    if warm_cache and not allow_network:
        raise ValueError(
            "local_warm_cache=True yÃƒÂªu cÃ¡ÂºÂ§u local_allow_network=True Ã„â€˜Ã¡Â»Æ’ diffusers cÃƒÂ³ thÃ¡Â»Æ’ tÃ¡ÂºÂ£i vÃƒÂ  lÃƒÂ m Ã¡ÂºÂ¥m cache mÃ¡Â»â„¢t lÃ¡ÂºÂ§n."
        )
    controlnet_model_ref = ""
    if controlnet_request:
        controlnet_model_ref, _ = resolve_model_reference(controlnet_request, provider="image", module_file=__file__, allow_network=allow_network)
    lora_model_ref = ""
    if lora_request:
        lora_model_ref, _ = resolve_model_reference(lora_request, provider="image", module_file=__file__, allow_network=allow_network)

    cache_key = (
        mode,
        model_ref,
        device,
        str(dtype),
        variant,
        str(use_safetensors),
        pipeline_family,
        original_config,
        diffusers_config_repo,
        controlnet_model_ref,
        lora_model_ref,
        lora_scale,
        allow_network,
        warm_cache,
        disable_safety_checker,
    )
    pipe = _LOCAL_PIPELINE_CACHE.get(cache_key)
    if pipe is None:
        pipe = _build_local_pipeline(
            model_ref=model_ref,
            device=device,
            dtype=dtype,
            variant=variant,
            use_safetensors=use_safetensors,
            mode=mode,
            pipeline_family=pipeline_family,
            original_config=original_config,
            diffusers_config_repo=diffusers_config_repo,
            controlnet_model_ref=controlnet_model_ref,
            lora_model_ref=lora_model_ref,
            lora_scale=lora_scale,
            allow_network=allow_network,
            warm_cache=warm_cache,
            disable_safety_checker=disable_safety_checker,
        )
        if bool(settings.get("local_enable_attention_slicing", True)) and hasattr(pipe, "enable_attention_slicing"):
            pipe.enable_attention_slicing()
        if bool(settings.get("local_enable_model_cpu_offload", False)) and device == "cuda" and hasattr(pipe, "enable_model_cpu_offload"):
            pipe.enable_model_cpu_offload()
        _LOCAL_PIPELINE_CACHE[cache_key] = pipe
    return pipe, model_ref, device, str(dtype)


def _build_generator(*, device: str, seed: int) -> Any:
    if seed < 0:
        return None
    try:
        import torch
        return torch.Generator(device=device if device != "mps" else "cpu").manual_seed(int(seed))
    except Exception:
        return None


def _prepare_control_image(image: Image.Image, mode: str) -> Image.Image:
    preprocessor = str(mode or "none").strip().lower()
    if preprocessor in {"", "none", "raw"}:
        return image.convert("RGB")
    if preprocessor == "canny":
        try:
            import cv2  # type: ignore
            import numpy as np
        except Exception as exc:
            raise RuntimeError("ControlNet preprocessor 'canny' cÃ¡ÂºÂ§n opencv-python-headless vÃƒÂ  numpy.") from exc
        arr = np.array(image.convert("RGB"))
        edges = cv2.Canny(arr, 100, 200)
        edges_rgb = np.stack([edges, edges, edges], axis=2)
        return Image.fromarray(edges_rgb)
    raise ValueError(f"ControlNet preprocessor khÃƒÂ´ng hÃ¡Â»â€” trÃ¡Â»Â£: {mode}")


def _detect_face_regions(image: Image.Image, *, max_detections: int, padding: float) -> list[tuple[int, int, int, int]]:
    try:
        import cv2  # type: ignore
        import numpy as np
    except Exception:
        return []

    arr = np.array(image.convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(str(cascade_path))
    detections = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(32, 32))
    regions: list[tuple[int, int, int, int]] = []
    img_w, img_h = image.size
    for (x, y, w, h) in list(detections)[:max_detections]:
        pad_w = int(w * padding)
        pad_h = int(h * padding)
        left = max(0, x - pad_w)
        top = max(0, y - pad_h)
        right = min(img_w, x + w + pad_w)
        bottom = min(img_h, y + h + pad_h)
        regions.append((left, top, right, bottom))
    return regions


def _merge_regions(regions: list[tuple[int, int, int, int]], *, max_detections: int) -> list[tuple[int, int, int, int]]:
    deduped: list[tuple[int, int, int, int]] = []
    for region in regions:
        left, top, right, bottom = region
        replaced = False
        for idx, existing in enumerate(deduped):
            el, et, er, eb = existing
            inter_left = max(left, el)
            inter_top = max(top, et)
            inter_right = min(right, er)
            inter_bottom = min(bottom, eb)
            if inter_right <= inter_left or inter_bottom <= inter_top:
                continue
            inter = (inter_right - inter_left) * (inter_bottom - inter_top)
            union = (right - left) * (bottom - top) + (er - el) * (eb - et) - inter
            iou = inter / union if union > 0 else 0.0
            if iou >= 0.45:
                deduped[idx] = (
                    min(left, el),
                    min(top, et),
                    max(right, er),
                    max(bottom, eb),
                )
                replaced = True
                break
        if not replaced:
            deduped.append(region)
        if len(deduped) >= max_detections:
            break
    return deduped[:max_detections]


def _detect_cascade_combo_regions(image: Image.Image, *, max_detections: int, padding: float) -> list[tuple[int, int, int, int]]:
    try:
        import cv2  # type: ignore
        import numpy as np
    except Exception:
        return _detect_face_regions(image, max_detections=max_detections, padding=padding)

    arr = np.array(image.convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    img_w, img_h = image.size
    cascade_names = [
        "haarcascade_frontalface_default.xml",
        "haarcascade_profileface.xml",
        "haarcascade_upperbody.xml",
        "haarcascade_fullbody.xml",
    ]
    regions: list[tuple[int, int, int, int]] = []
    for cascade_name in cascade_names:
        cascade_path = Path(cv2.data.haarcascades) / cascade_name
        if not cascade_path.is_file():
            continue
        detector = cv2.CascadeClassifier(str(cascade_path))
        detections = detector.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4, minSize=(28, 28))
        for (x, y, w, h) in list(detections):
            pad_w = int(w * padding)
            pad_h = int(h * padding)
            regions.append((
                max(0, x - pad_w),
                max(0, y - pad_h),
                min(img_w, x + w + pad_w),
                min(img_h, y + h + pad_h),
            ))
    merged = _merge_regions(regions, max_detections=max_detections)
    return merged or _detect_face_regions(image, max_detections=max_detections, padding=padding)


def _detect_mediapipe_regions(image: Image.Image, *, max_detections: int, padding: float, include_person: bool = True) -> list[tuple[int, int, int, int]]:
    try:
        import mediapipe as mp  # type: ignore
        import numpy as np
    except Exception:
        return _detect_cascade_combo_regions(image, max_detections=max_detections, padding=padding)

    arr = np.array(image.convert("RGB"))
    img_h, img_w = arr.shape[:2]
    regions: list[tuple[int, int, int, int]] = []

    def _pad_rect(x1: float, y1: float, x2: float, y2: float) -> tuple[int, int, int, int] | None:
        left = max(0, int(x1 - (x2 - x1) * padding))
        top = max(0, int(y1 - (y2 - y1) * padding))
        right = min(img_w, int(x2 + (x2 - x1) * padding))
        bottom = min(img_h, int(y2 + (y2 - y1) * padding))
        if right <= left or bottom <= top:
            return None
        return (left, top, right, bottom)

    try:
        face_detection = mp.solutions.face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.35)
        face_result = face_detection.process(arr)
        for det in list(getattr(face_result, 'detections', []) or []):
            bbox = det.location_data.relative_bounding_box
            region = _pad_rect(
                bbox.xmin * img_w,
                bbox.ymin * img_h,
                (bbox.xmin + bbox.width) * img_w,
                (bbox.ymin + bbox.height) * img_h,
            )
            if region is not None:
                regions.append(region)
        face_detection.close()
    except Exception:
        pass

    if include_person:
        try:
            pose = mp.solutions.pose.Pose(static_image_mode=True, model_complexity=1, min_detection_confidence=0.35)
            pose_result = pose.process(arr)
            landmarks = getattr(getattr(pose_result, 'pose_landmarks', None), 'landmark', None)
            if landmarks:
                xs = [float(lm.x) * img_w for lm in landmarks if getattr(lm, 'visibility', 1.0) >= 0.2]
                ys = [float(lm.y) * img_h for lm in landmarks if getattr(lm, 'visibility', 1.0) >= 0.2]
                if xs and ys:
                    region = _pad_rect(min(xs), min(ys), max(xs), max(ys))
                    if region is not None:
                        regions.append(region)
            pose.close()
        except Exception:
            pass

    merged = _merge_regions(regions, max_detections=max_detections)
    return merged or _detect_cascade_combo_regions(image, max_detections=max_detections, padding=padding)


def _detect_yolo_regions(image: Image.Image, *, max_detections: int, padding: float, model_ref: str = '', confidence: float = 0.25) -> list[tuple[int, int, int, int]]:
    try:
        import numpy as np
        from ultralytics import YOLO  # type: ignore
    except Exception:
        return []

    resolved_model = str(model_ref or 'yolov8n.pt').strip()
    try:
        detector = YOLO(resolved_model)
    except Exception:
        return []

    arr = np.array(image.convert('RGB'))
    img_w, img_h = image.size
    try:
        results = detector.predict(arr, verbose=False, conf=float(confidence or 0.25))
    except Exception:
        return []

    regions: list[tuple[int, int, int, int]] = []
    for result in list(results or []):
        boxes = getattr(result, 'boxes', None)
        if boxes is None:
            continue
        xyxy = getattr(boxes, 'xyxy', None)
        cls = getattr(boxes, 'cls', None)
        if xyxy is None:
            continue
        names = getattr(result, 'names', {}) or {}
        for idx, coords in enumerate(xyxy.tolist()):
            class_id = int(cls[idx].item()) if cls is not None else -1
            label = str(names.get(class_id, class_id)).lower()
            if label not in {'person', 'face', 'head'} and class_id != 0:
                continue
            x1, y1, x2, y2 = coords[:4]
            pad_w = (x2 - x1) * padding
            pad_h = (y2 - y1) * padding
            left = max(0, int(x1 - pad_w))
            top = max(0, int(y1 - pad_h))
            right = min(img_w, int(x2 + pad_w))
            bottom = min(img_h, int(y2 + pad_h))
            if right > left and bottom > top:
                regions.append((left, top, right, bottom))
    return _merge_regions(regions, max_detections=max_detections)


def _parse_manual_regions(value: Any, *, image_size: tuple[int, int]) -> list[tuple[int, int, int, int]]:
    if not value:
        return []
    raw_regions = value
    if isinstance(value, str):
        try:
            raw_regions = json.loads(value)
        except Exception:
            return []
    if not isinstance(raw_regions, list):
        return []
    img_w, img_h = image_size
    regions: list[tuple[int, int, int, int]] = []
    for item in raw_regions:
        if not isinstance(item, dict):
            continue
        x = int(item.get("x", 0))
        y = int(item.get("y", 0))
        w = int(item.get("w", 0))
        h = int(item.get("h", 0))
        if w <= 0 or h <= 0:
            continue
        left = max(0, x)
        top = max(0, y)
        right = min(img_w, x + w)
        bottom = min(img_h, y + h)
        if right > left and bottom > top:
            regions.append((left, top, right, bottom))
    return regions


def preview_local_adetailer_regions(*, image: Image.Image, provider_payload: dict[str, Any]) -> dict[str, Any]:
    detector = str(provider_payload.get("local_adetailer_detector") or "cascade_combo").strip().lower()
    padding = float(provider_payload.get("local_adetailer_padding", 0.35) or 0.35)
    max_detections = int(provider_payload.get("local_adetailer_max_detections", 4) or 4)
    logs: list[str] = []
    fallback_used = False

    if detector == "cascade_combo":
        regions = _detect_cascade_combo_regions(image, max_detections=max_detections, padding=padding)
    elif detector == "face_haar":
        regions = _detect_face_regions(image, max_detections=max_detections, padding=padding)
    elif detector == "mediapipe_face":
        regions = _detect_mediapipe_regions(image, max_detections=max_detections, padding=padding, include_person=False)
    elif detector == "mediapipe_face_person":
        regions = _detect_mediapipe_regions(image, max_detections=max_detections, padding=padding, include_person=True)
    elif detector == "yolo":
        regions = _detect_yolo_regions(
            image,
            max_detections=max_detections,
            padding=padding,
            model_ref=str(provider_payload.get("local_adetailer_yolo_model") or "").strip(),
            confidence=float(provider_payload.get("local_adetailer_yolo_confidence", 0.25) or 0.25),
        )
        if not regions:
            regions = _detect_mediapipe_regions(image, max_detections=max_detections, padding=padding, include_person=True)
            fallback_used = True
            logs.append("YOLO preview fallback -> mediapipe_face_person")
    elif detector == "manual_regions":
        regions = _parse_manual_regions(provider_payload.get("local_adetailer_regions"), image_size=image.size)
    else:
        regions = []
        logs.append(f"Detector preview chÃ†Â°a hÃ¡Â»â€” trÃ¡Â»Â£: {detector}")

    return {
        "detector": detector,
        "regions": regions,
        "logs": logs,
        "fallback_used": fallback_used,
        "count": len(regions),
    }


def draw_detection_preview(*, image: Image.Image, regions: list[tuple[int, int, int, int]]) -> Image.Image:
    preview = image.convert("RGB").copy()
    draw = ImageDraw.Draw(preview)
    try:
        from PIL import ImageFont
        font = ImageFont.load_default()
    except Exception:
        font = None
    for idx, (left, top, right, bottom) in enumerate(regions, start=1):
        draw.rectangle((left, top, right, bottom), outline=(255, 64, 64), width=max(2, max(1, preview.width // 256)))
        label = f"#{idx}"
        text_xy = (left + 4, max(0, top - 14))
        if font is not None:
            draw.text(text_xy, label, fill=(255, 64, 64), font=font)
        else:
            draw.text(text_xy, label, fill=(255, 64, 64))
    return preview






def parse_preview_tint(color_value: str | tuple[int, int, int] | None, *, fallback: tuple[int, int, int] = (255, 64, 64)) -> tuple[int, int, int]:
    if isinstance(color_value, tuple) and len(color_value) == 3:
        try:
            return tuple(max(0, min(255, int(v))) for v in color_value)  # type: ignore[return-value]
        except Exception:
            return fallback
    raw = str(color_value or "").strip()
    if not raw:
        return fallback
    try:
        resolved = ImageColor.getrgb(raw)
        if isinstance(resolved, tuple) and len(resolved) >= 3:
            return int(resolved[0]), int(resolved[1]), int(resolved[2])
    except Exception:
        return fallback
    return fallback


def overlay_mask_preview(*, image: Image.Image, mask: Image.Image, tint: tuple[int, int, int] = (255, 64, 64), alpha: int = 110) -> Image.Image:
    base = image.convert("RGBA")
    mask_l = mask.convert("L")
    overlay = Image.new("RGBA", base.size, tint + (0,))
    alpha_mask = mask_l.point(lambda px: max(0, min(255, int((px / 255.0) * alpha))))
    overlay.putalpha(alpha_mask)
    return Image.alpha_composite(base, overlay).convert("RGB")


def crop_detection_regions(*, image: Image.Image, regions: list[tuple[int, int, int, int]], padding_px: int = 0) -> list[dict[str, Any]]:
    preview = image.convert("RGB")
    img_w, img_h = preview.size
    crops: list[dict[str, Any]] = []
    for idx, (left, top, right, bottom) in enumerate(regions, start=1):
        l = max(0, int(left) - padding_px)
        t = max(0, int(top) - padding_px)
        r = min(img_w, int(right) + padding_px)
        b = min(img_h, int(bottom) + padding_px)
        if r <= l or b <= t:
            continue
        crop = preview.crop((l, t, r, b))
        crops.append({
            "index": idx,
            "bbox": (left, top, right, bottom),
            "padded_bbox": (l, t, r, b),
            "image": crop,
            "size": crop.size,
        })
    return crops


def build_debug_preview_sheet(
    *,
    source_image: Image.Image,
    overlay_image: Image.Image | None = None,
    boxed_image: Image.Image | None = None,
    mask_image: Image.Image | None = None,
    crops: list[dict[str, Any]] | None = None,
    header_lines: list[str] | None = None,
    max_panel_width: int = 480,
) -> Image.Image:
    base = source_image.convert("RGB")
    overlay = overlay_image.convert("RGB") if overlay_image is not None else None
    boxed = boxed_image.convert("RGB") if boxed_image is not None else None
    mask = mask_image.convert("RGB") if mask_image is not None else None
    crop_items = list(crops or [])

    try:
        from PIL import ImageFont
        font = ImageFont.load_default()
    except Exception:
        font = None

    def _fit(img: Image.Image, width: int) -> Image.Image:
        if img.width <= width:
            return img.copy()
        ratio = width / max(1, img.width)
        return img.resize((width, max(1, int(img.height * ratio))), Image.Resampling.LANCZOS)

    def _measure_text(draw: ImageDraw.ImageDraw, text: str) -> tuple[int, int]:
        if font is not None:
            try:
                left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
                return right - left, bottom - top
            except Exception:
                pass
        return max(40, len(text) * 7), 14

    def _panel(title: str, img: Image.Image | None) -> Image.Image:
        content = _fit(img if img is not None else Image.new("RGB", base.size, (245, 245, 245)), max_panel_width)
        title_h = 26
        panel = Image.new("RGB", (content.width + 16, content.height + title_h + 16), (255, 255, 255))
        draw = ImageDraw.Draw(panel)
        draw.rounded_rectangle((0, 0, panel.width - 1, panel.height - 1), radius=12, outline=(210, 210, 210), width=1, fill=(255, 255, 255))
        if font is not None:
            draw.text((8, 6), title, fill=(24, 24, 24), font=font)
        else:
            draw.text((8, 6), title, fill=(24, 24, 24))
        panel.paste(content, (8, title_h))
        return panel

    top_panels = [_panel("Source", base)]
    if overlay is not None:
        top_panels.append(_panel("Mask overlay", overlay))
    if boxed is not None:
        top_panels.append(_panel("Detector boxes", boxed))
    if mask is not None:
        top_panels.append(_panel("Mask", mask))

    gap = 16
    sheet_width = sum(p.width for p in top_panels) + gap * (len(top_panels) + 1)
    top_height = max(p.height for p in top_panels) if top_panels else 0

    header_lines = [str(line).strip() for line in (header_lines or []) if str(line).strip()]
    header_height = 12
    if header_lines:
        probe = ImageDraw.Draw(Image.new("RGB", (8, 8), (255, 255, 255)))
        line_heights = [_measure_text(probe, line)[1] for line in header_lines]
        header_height = sum(line_heights) + 12 + max(0, len(header_lines) - 1) * 4

    crop_panels: list[Image.Image] = []
    for crop in crop_items:
        bbox = tuple(crop.get("bbox") or (0, 0, 0, 0))
        size = tuple(crop.get("size") or (0, 0))
        crop_title = f"Crop #{crop.get('index')} Ã‚Â· {bbox[0]},{bbox[1]}Ã¢â€ â€™{bbox[2]},{bbox[3]} Ã‚Â· {size[0]}x{size[1]}"
        crop_img = crop.get("image") if isinstance(crop.get("image"), Image.Image) else None
        if crop_img is not None:
            crop_panels.append(_panel(crop_title, crop_img))

    crop_rows: list[list[Image.Image]] = []
    if crop_panels:
        current: list[Image.Image] = []
        current_width = gap
        for panel in crop_panels:
            prospective = current_width + panel.width + gap
            if current and prospective > max(sheet_width, max_panel_width * 2):
                crop_rows.append(current)
                current = [panel]
                current_width = gap + panel.width + gap
            else:
                current.append(panel)
                current_width = prospective
        if current:
            crop_rows.append(current)

    crop_height = 0
    if crop_rows:
        crop_height = sum(max(panel.height for panel in row) for row in crop_rows) + gap * (len(crop_rows) + 1) + 28

    sheet_height = header_height + top_height + crop_height + gap * 2
    sheet = Image.new("RGB", (sheet_width, sheet_height), (246, 248, 251))
    draw = ImageDraw.Draw(sheet)

    y = gap
    if header_lines:
        for line in header_lines:
            if font is not None:
                draw.text((gap, y), line, fill=(24, 24, 24), font=font)
            else:
                draw.text((gap, y), line, fill=(24, 24, 24))
            y += _measure_text(draw, line)[1] + 4
        y += 8

    x = gap
    for panel in top_panels:
        sheet.paste(panel, (x, y))
        x += panel.width + gap
    y += top_height + gap

    if crop_rows:
        if font is not None:
            draw.text((gap, y), "Detector region crops", fill=(24, 24, 24), font=font)
        else:
            draw.text((gap, y), "Detector region crops", fill=(24, 24, 24))
        y += 24
        for row in crop_rows:
            row_h = max(panel.height for panel in row)
            x = gap
            for panel in row:
                sheet.paste(panel, (x, y))
                x += panel.width + gap
            y += row_h + gap

    return sheet


def _apply_local_adetailer(
    *,
    base_image: Image.Image,
    cfg: dict[str, Any],
    prompt_path: Path | None,
    settings: dict[str, Any],
    logs: list[str],
) -> Image.Image:
    provider_payload = dict(cfg.get("provider_payload") or {})
    if not bool(provider_payload.get("local_adetailer_enabled", False)):
        return base_image

    detector = str(provider_payload.get("local_adetailer_detector") or "cascade_combo").strip().lower()
    padding = float(provider_payload.get("local_adetailer_padding", 0.35) or 0.35)
    max_detections = int(provider_payload.get("local_adetailer_max_detections", 4) or 4)
    detailer_prompt = str(provider_payload.get("local_adetailer_prompt") or cfg["prompt"]).strip()
    detailer_negative = str(provider_payload.get("local_adetailer_negative_prompt") or cfg["negative_prompt"] or "").strip()
    strength = float(provider_payload.get("local_adetailer_strength", 0.3) or 0.3)
    detailer_steps = int(provider_payload.get("local_adetailer_steps", max(10, int(cfg["steps"]) // 2)) or 15)

    preview = preview_local_adetailer_regions(image=base_image, provider_payload=provider_payload)
    regions = list(preview.get("regions") or [])
    logs.extend([f"Local ADetailer preview: {msg}" for msg in list(preview.get("logs") or [])])
    if preview.get("detector") != detector:
        logs.append(f"Local ADetailer preview detector resolved={preview.get('detector')}")
    if detector not in {"cascade_combo", "face_haar", "mediapipe_face", "mediapipe_face_person", "yolo", "manual_regions"}:
        logs.append(f"Local ADetailer skipped: detector={detector} chÃ†Â°a hÃ¡Â»â€” trÃ¡Â»Â£")
        return base_image

    if not regions:
        logs.append("Local ADetailer: khÃƒÂ´ng tÃƒÂ¬m thÃ¡ÂºÂ¥y region Ã„â€˜Ã¡Â»Æ’ refine")
        return base_image

    detail_settings = dict(settings)
    detail_pipe, _, device, _ = _get_local_pipeline(detail_settings, mode="img2img")
    generator = _build_generator(device=device, seed=int(cfg["seed"]))
    composed = base_image.copy()

    for idx, (left, top, right, bottom) in enumerate(regions, start=1):
        crop = composed.crop((left, top, right, bottom)).convert("RGB")
        run_kwargs: dict[str, Any] = {
            "prompt": detailer_prompt,
            "negative_prompt": detailer_negative or None,
            "image": crop,
            "strength": strength,
            "num_inference_steps": detailer_steps,
            "guidance_scale": float(cfg["cfg"]),
        }
        if generator is not None:
            run_kwargs["generator"] = generator
        result = detail_pipe(**run_kwargs)
        images = list(getattr(result, "images", []) or [])
        if not images:
            continue
        refined = images[0].resize((right - left, bottom - top))
        composed.paste(refined, (left, top))
        logs.append(f"Local ADetailer refined region #{idx}: ({left},{top})-({right},{bottom})")
    return composed


def _invoke_pipeline_with_progress(
    pipe: Any,
    run_kwargs: dict[str, Any],
    *,
    progress_callback: ProgressCallback | None = None,
    progress_label: str = "",
    stage_fraction: float = 0.0,
    stage_weight: float = 1.0,
) -> Any:
    if progress_callback is None:
        return pipe(**run_kwargs)

    total_steps = max(1, int(run_kwargs.get("num_inference_steps") or 1))
    state = {"last_step": 0}

    def _report(step_index: int, message: str) -> None:
        bounded = max(0, min(total_steps, int(step_index)))
        fraction = stage_fraction + stage_weight * (bounded / total_steps)
        _emit_progress(progress_callback, fraction, message or progress_label)

    def _step_callback(*args: Any, **kwargs: Any) -> dict[str, Any]:
        message = str(kwargs.get("message") or progress_label or "Rendering")
        step_index = None
        for value in args:
            if isinstance(value, int):
                step_index = value
                break
        if step_index is None:
            state["last_step"] = min(total_steps, state["last_step"] + 1)
            step_index = state["last_step"]
        else:
            state["last_step"] = int(step_index)
        _report(int(step_index), message)
        callback_kwargs = kwargs.get("callback_kwargs")
        return dict(callback_kwargs) if isinstance(callback_kwargs, dict) else {}

    attempts = (
        {"callback_on_step_end": _step_callback, "callback_on_step_end_tensor_inputs": ["latents"]},
        {"callback": _step_callback, "callback_steps": 1},
    )
    last_type_error: TypeError | None = None
    for extra_kwargs in attempts:
        try:
            return pipe(**run_kwargs, **extra_kwargs)
        except TypeError as exc:
            message = str(exc)
            if "unexpected keyword argument" not in message and "got an unexpected keyword argument" not in message:
                raise
            last_type_error = exc
    if last_type_error is not None:
        return pipe(**run_kwargs)
    return pipe(**run_kwargs)


def _render_via_diffusers_local(
    prompt_data: dict[str, Any],
    prompt_path: Path | None,
    output_path: Path,
    settings: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> list[str]:
    cfg = _merge_prompt_settings(prompt_data, settings)
    provider_payload = dict(cfg.get("provider_payload") or {})
    generation_mode = str(provider_payload.get("local_generation_mode") or "txt2img").strip().lower()
    allow_auto_shorten_prompt = bool(provider_payload.get("local_auto_shorten_prompt", provider_payload.get("local_auto_shorten_prompts", True)))
    allow_auto_shorten_negative = bool(provider_payload.get("local_auto_shorten_negative_prompt", provider_payload.get("local_auto_shorten_prompts", True)))
    if generation_mode not in {"txt2img", "img2img", "controlnet", "inpaint"}:
        raise ValueError(f"Local generation mode khÃƒÂ´ng hÃ¡Â»â€” trÃ¡Â»Â£: {generation_mode}")

    pipeline_mode = generation_mode
    _emit_progress(progress_callback, 0.02, f"Loading local {pipeline_mode} model")
    pipe, model_ref, device, dtype_name = _get_local_pipeline(settings, mode=pipeline_mode)
    scheduler_used = _maybe_apply_scheduler(pipe, cfg.get("sampler_name") or cfg.get("scheduler") or "")
    generator = _build_generator(device=device, seed=int(cfg["seed"]))

    num_images_per_prompt = int(provider_payload.pop("num_images_per_prompt", 1) or 1)
    guidance_scale = float(provider_payload.get("guidance_scale", cfg["cfg"]))

    logs = [
        f"Local headless mode={generation_mode}",
        f"Local model={model_ref}",
        f"Local device={device}",
        f"Local dtype={dtype_name}",
        f"Local scheduler={scheduler_used}",
    ]
    if bool(provider_payload.get("local_lora_enabled", False)) and str(provider_payload.get("local_lora_model_id_or_path") or "").strip():
        logs.append(f"Local LoRA={provider_payload.get('local_lora_model_id_or_path')} scale={provider_payload.get('local_lora_scale', 1.0)}")

    prompt_value, negative_prompt_value = _prepare_prompt_pair_for_clip(
        pipe,
        cfg["prompt"],
        cfg["negative_prompt"],
        logs=logs,
        allow_auto_shorten_prompt=allow_auto_shorten_prompt,
        allow_auto_shorten_negative=allow_auto_shorten_negative,
    )
    run_kwargs: dict[str, Any] = {
        "prompt": prompt_value,
        "negative_prompt": negative_prompt_value,
        "num_inference_steps": int(cfg["steps"]),
        "guidance_scale": guidance_scale,
        "num_images_per_prompt": num_images_per_prompt,
    }
    if generator is not None:
        run_kwargs["generator"] = generator

    if generation_mode == "txt2img":
        run_kwargs.update({
            "width": int(cfg["width"]),
            "height": int(cfg["height"]),
        })
        passthrough = {k: v for k, v in provider_payload.items() if not str(k).startswith("local_")}
        run_kwargs.update(passthrough)
        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            result = _invoke_pipeline_with_progress(
                pipe,
                run_kwargs,
                progress_callback=progress_callback,
                progress_label=f"{generation_mode} {output_path.name}",
                stage_fraction=0.05,
                stage_weight=0.85,
            )
        logs.extend(_filtered_warning_messages(caught_warnings))
    elif generation_mode == "img2img":
        init_image, init_source = _load_bundle_or_path_image(
            prompt_path=prompt_path,
            prompt_data=prompt_data,
            provider_payload=provider_payload,
            asset_kind="init_image",
        )
        if init_image is None:
            raise FileNotFoundError("Img2img local cÃ¡ÂºÂ§n init image; cÃƒÂ³ thÃ¡Â»Æ’ nhÃ¡ÂºÂ­p path tay hoÃ¡ÂºÂ·c Ã„â€˜Ã¡Â»Æ’ bundle/manifest tÃ¡Â»Â± resolve.")
        run_kwargs.update({
            "image": init_image.resize((int(cfg["width"]), int(cfg["height"]))),
            "strength": float(provider_payload.get("local_img2img_strength", 0.45) or 0.45),
        })
        passthrough = {k: v for k, v in provider_payload.items() if not str(k).startswith("local_") and k not in {"init_image", "image"}}
        run_kwargs.update(passthrough)
        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            result = _invoke_pipeline_with_progress(
                pipe,
                run_kwargs,
                progress_callback=progress_callback,
                progress_label=f"{generation_mode} {output_path.name}",
                stage_fraction=0.05,
                stage_weight=0.85,
            )
        logs.extend(_filtered_warning_messages(caught_warnings))
        logs.append(f"Local img2img init={init_source}")
    elif generation_mode == "controlnet":
        control_image, control_source = _load_bundle_or_path_image(
            prompt_path=prompt_path,
            prompt_data=prompt_data,
            provider_payload=provider_payload,
            asset_kind="control_image",
        )
        if control_image is None:
            raise FileNotFoundError("ControlNet local cÃ¡ÂºÂ§n control image; cÃƒÂ³ thÃ¡Â»Æ’ nhÃ¡ÂºÂ­p path tay hoÃ¡ÂºÂ·c Ã„â€˜Ã¡Â»Æ’ bundle/manifest tÃ¡Â»Â± resolve.")
        control_preprocessor = str(provider_payload.get("local_control_preprocessor") or "none")
        conditioned_image = _prepare_control_image(control_image.resize((int(cfg["width"]), int(cfg["height"]))), control_preprocessor)
        run_kwargs.update({
            "image": conditioned_image,
            "width": int(cfg["width"]),
            "height": int(cfg["height"]),
            "controlnet_conditioning_scale": float(provider_payload.get("local_controlnet_conditioning_scale", 1.0) or 1.0),
        })
        passthrough = {k: v for k, v in provider_payload.items() if not str(k).startswith("local_") and k not in {"control_image"}}
        run_kwargs.update(passthrough)
        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            result = _invoke_pipeline_with_progress(
                pipe,
                run_kwargs,
                progress_callback=progress_callback,
                progress_label=f"{generation_mode} {output_path.name}",
                stage_fraction=0.05,
                stage_weight=0.85,
            )
        logs.extend(_filtered_warning_messages(caught_warnings))
        logs.append(f"Local controlnet model={provider_payload.get('local_controlnet_model_id_or_path') or ''}")
        logs.append(f"Local control image={control_source}")
        logs.append(f"Local control preprocessor={control_preprocessor}")
    else:
        inpaint_image, image_source = _load_bundle_or_path_image(
            prompt_path=prompt_path,
            prompt_data=prompt_data,
            provider_payload=provider_payload,
            asset_kind="inpaint_image",
        )
        mask_image, mask_source = _load_bundle_or_path_image(
            prompt_path=prompt_path,
            prompt_data=prompt_data,
            provider_payload=provider_payload,
            asset_kind="mask_image",
            convert="L",
        )
        if inpaint_image is None:
            raise FileNotFoundError("Inpaint local cÃ¡ÂºÂ§n Ã¡ÂºÂ£nh nguÃ¡Â»â€œn; cÃƒÂ³ thÃ¡Â»Æ’ nhÃ¡ÂºÂ­p path tay hoÃ¡ÂºÂ·c Ã„â€˜Ã¡Â»Æ’ bundle/manifest tÃ¡Â»Â± resolve.")
        if mask_image is None:
            raise FileNotFoundError("Inpaint local cÃ¡ÂºÂ§n mask Ã¡ÂºÂ£nh; cÃƒÂ³ thÃ¡Â»Æ’ nhÃ¡ÂºÂ­p path tay hoÃ¡ÂºÂ·c Ã„â€˜Ã¡Â»Æ’ bundle/manifest tÃ¡Â»Â± resolve.")
        run_kwargs.update({
            "image": inpaint_image.resize((int(cfg["width"]), int(cfg["height"]))),
            "mask_image": mask_image.resize((int(cfg["width"]), int(cfg["height"]))),
            "strength": float(provider_payload.get("local_inpaint_strength", 0.55) or 0.55),
        })
        passthrough = {k: v for k, v in provider_payload.items() if not str(k).startswith("local_") and k not in {"inpaint_image", "mask", "mask_image"}}
        run_kwargs.update(passthrough)
        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            result = _invoke_pipeline_with_progress(
                pipe,
                run_kwargs,
                progress_callback=progress_callback,
                progress_label=f"{generation_mode} {output_path.name}",
                stage_fraction=0.05,
                stage_weight=0.85,
            )
        logs.extend(_filtered_warning_messages(caught_warnings))
        logs.append(f"Local inpaint image={image_source}")
        logs.append(f"Local inpaint mask={mask_source}")

    images = list(getattr(result, "images", []) or [])
    if not images:
        raise RuntimeError("Local headless provider khÃƒÂ´ng trÃ¡ÂºÂ£ vÃ¡Â»Â Ã¡ÂºÂ£nh nÃƒÂ o.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []
    for index, image in enumerate(images, start=1):
        output_image = _apply_local_adetailer(base_image=image, cfg=cfg, prompt_path=prompt_path, settings=settings, logs=logs)
        target = output_path if index == 1 else output_path.with_name(f"{output_path.stem}_batch{index:02d}{output_path.suffix}")
        output_image.save(target)
        saved_paths.append(target)
        logs.append(f"Local headless output -> {target}")
    _emit_progress(progress_callback, 1.0, f"Saved {len(saved_paths)} image(s) for {output_path.name}")
    return logs


# ---------- ComfyUI ----------


def _ensure_node_id(raw_id: Any, workflow: dict[str, Any], allowed_classes: set[str]) -> str | None:
    node_id = str(raw_id or "").strip()
    if node_id and node_id in workflow:
        return node_id
    for candidate_id, candidate in workflow.items():
        class_type = str((candidate or {}).get("class_type") or "")
        if class_type in allowed_classes:
            return str(candidate_id)
    return None


_COMFYUI_LORA_NODE_TYPES = {"LoraLoader", "LoRALoader", "Power Lora Loader (rgthree)"}


def _normalize_comfyui_lora_ref(raw_ref: Any) -> str:
    return str(raw_ref or "").strip().replace("\\", "/")


def _apply_comfyui_lora_settings(workflow: dict[str, Any], provider_payload: dict[str, Any]) -> int:
    if not bool(provider_payload.get("local_lora_enabled", False)):
        return 0
    lora_ref = _normalize_comfyui_lora_ref(provider_payload.get("local_lora_model_id_or_path"))
    if not lora_ref:
        return 0
    lora_scale = float(provider_payload.get("local_lora_scale") or 1.0)
    updated = 0
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        if class_type not in _COMFYUI_LORA_NODE_TYPES:
            continue
        inputs = node.setdefault("inputs", {})
        if not isinstance(inputs, dict):
            node["inputs"] = inputs = {}
        if class_type in {"LoraLoader", "LoRALoader"}:
            inputs["lora_name"] = lora_ref
            inputs["strength_model"] = lora_scale
            inputs["strength_clip"] = lora_scale
            updated += 1
            continue
        node_updated = False
        for key, value in list(inputs.items()):
            key_lower = str(key).lower()
            if key_lower in {"lora_name", "name"} or ("lora" in key_lower and isinstance(value, str)):
                inputs[key] = lora_ref
                node_updated = True
            elif "strength" in key_lower and isinstance(value, (int, float)):
                inputs[key] = lora_scale
                node_updated = True
            elif "lora" in key_lower and isinstance(value, dict):
                if "lora" in value:
                    value["lora"] = lora_ref
                if "name" in value:
                    value["name"] = lora_ref
                if "strength" in value:
                    value["strength"] = lora_scale
                if "on" in value:
                    value["on"] = True
                node_updated = True
        if node_updated:
            updated += 1
    return updated


def _inject_comfyui_workflow(workflow: dict[str, Any], prompt_data: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    cfg = _merge_prompt_settings(prompt_data, settings)
    wf = copy.deepcopy(workflow)
    pos_id = _ensure_node_id(settings.get("positive_prompt_node_id", ""), wf, {"CLIPTextEncode"})
    neg_id = _ensure_node_id(settings.get("negative_prompt_node_id", ""), wf, {"CLIPTextEncode"})
    sampler_id = _ensure_node_id(settings.get("sampler_node_id", ""), wf, {"KSampler", "KSamplerAdvanced"})
    latent_id = _ensure_node_id(settings.get("latent_size_node_id", ""), wf, {"EmptyLatentImage"})

    if pos_id:
        wf[pos_id].setdefault("inputs", {})["text"] = cfg["prompt"]
    if neg_id and neg_id != pos_id:
        wf[neg_id].setdefault("inputs", {})["text"] = cfg["negative_prompt"]
    if sampler_id:
        inputs = wf[sampler_id].setdefault("inputs", {})
        inputs["seed"] = cfg["seed"] if cfg["seed"] >= 0 else int(time.time() * 1000) % 2_147_483_647
        inputs["steps"] = cfg["steps"]
        inputs["cfg"] = cfg["cfg"]
        if "sampler_name" in inputs:
            inputs["sampler_name"] = cfg["sampler_name"]
        if "scheduler" in inputs:
            inputs["scheduler"] = cfg["scheduler"]
    if latent_id:
        inputs = wf[latent_id].setdefault("inputs", {})
        if "width" in inputs:
            inputs["width"] = cfg["width"]
        if "height" in inputs:
            inputs["height"] = cfg["height"]
    _apply_comfyui_lora_settings(wf, dict(cfg.get("provider_payload") or {}))
    return wf


def _parse_output_node_ids(raw_value: Any) -> list[str]:
    parts = str(raw_value or "").replace(";", ",").split(",")
    return [part.strip() for part in parts if part.strip()]


def _select_comfyui_output_image(
    node_outputs: dict[str, Any],
    output_node_ids: Any,
) -> tuple[str, dict[str, Any]] | None:
    images_by_node: dict[str, list[dict[str, Any]]] = {}
    ordered_images: list[tuple[str, dict[str, Any]]] = []
    for node_id, node_output in node_outputs.items():
        node_images = [
            dict(image_info)
            for image_info in ((node_output or {}).get("images") or [])
            if isinstance(image_info, dict)
        ]
        if not node_images:
            continue
        node_key = str(node_id)
        images_by_node[node_key] = node_images
        ordered_images.extend((node_key, image_info) for image_info in node_images)

    for node_id in _parse_output_node_ids(output_node_ids):
        node_images = images_by_node.get(node_id)
        if node_images:
            return node_id, node_images[0]
    return ordered_images[0] if ordered_images else None


def _render_via_comfyui(
    base_url: str,
    api_key: str,
    prompt_data: dict[str, Any],
    prompt_path: Path | None,
    output_path: Path,
    settings: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> list[str]:
    workflow_file = resolve_workflow_file(prompt_data=prompt_data, prompt_path=prompt_path, settings=settings)
    if not workflow_file:
        raise ValueError("ChÃ†Â°a cÃ¡ÂºÂ¥u hÃƒÂ¬nh workflow JSON cho ComfyUI.")
    workflow_path = Path(workflow_file)
    if not workflow_path.is_file():
        raise FileNotFoundError(f"KhÃƒÂ´ng tÃƒÂ¬m thÃ¡ÂºÂ¥y workflow JSON: {workflow_path}")
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    payload_workflow = _inject_comfyui_workflow(workflow, prompt_data, settings)
    headers = {"Content-Type": "application/json"}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    resp = requests.post(f"{base_url.rstrip('/')}/prompt", headers=headers, json={"prompt": payload_workflow}, timeout=120)
    resp.raise_for_status()
    prompt_id = str((resp.json() or {}).get("prompt_id") or "").strip()
    if not prompt_id:
        raise RuntimeError("ComfyUI khÃƒÂ´ng trÃ¡ÂºÂ£ vÃ¡Â»Â prompt_id.")
    poll_interval = float(settings.get("poll_interval") or 1.5)
    max_wait = int(settings.get("max_wait_s") or 180)
    history = None
    started = time.time()
    _emit_progress(progress_callback, 0.05, f"Submitted {output_path.name} to ComfyUI")
    while time.time() - started < max_wait:
        elapsed = time.time() - started
        wait_fraction = min(0.95, elapsed / max(1.0, float(max_wait)) * 0.9)
        _emit_progress(progress_callback, 0.05 + wait_fraction * 0.9, f"Waiting for {prompt_id}")
        hist_resp = requests.get(f"{base_url.rstrip('/')}/history/{prompt_id}", headers=headers, timeout=60)
        hist_resp.raise_for_status()
        history = hist_resp.json() or {}
        node_outputs = (history.get(prompt_id) or {}).get("outputs") or {}
        selected_image = _select_comfyui_output_image(node_outputs, settings.get("output_node_ids"))
        if selected_image:
            node_id, image_info = selected_image
            params = {
                "filename": image_info.get("filename"),
                "subfolder": image_info.get("subfolder", ""),
                "type": image_info.get("type", "output"),
            }
            img_resp = requests.get(f"{base_url.rstrip('/')}/view", headers=headers, params=params, timeout=120)
            img_resp.raise_for_status()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(img_resp.content)
            _emit_progress(progress_callback, 1.0, f"Saved {output_path.name}")
            return [f"ComfyUI workflow={workflow_path.name}", f"ComfyUI prompt_id={prompt_id}", f"ComfyUI output node={node_id}", f"ComfyUI image -> {output_path}"]
        time.sleep(poll_interval)
    raise TimeoutError(f"ComfyUI chÃ†Â°a trÃ¡ÂºÂ£ Ã¡ÂºÂ£nh sau {max_wait} giÃƒÂ¢y. prompt_id={prompt_id}")


