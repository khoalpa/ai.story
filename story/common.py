from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from story.paths import resolve_asset_reference, resolve_modes_root, resolve_presets_root, resolve_project_root

ALLOWED_DSL_TAGS = {
    "NARRATOR", "FEMALE", "MALE",
    "SLOW", "NORMAL", "FAST",
    "VI", "EN",
    "PAUSE", "BREAK", "BGM", "BGM_DB", "SFX",
}

SUPPORTED_STORY_MODES = {"trend", "calm"}
DEFAULT_BASE_MODE_ASSET_FILE = "base_mode_defaults.yml"

JSON_FENCE_OBJ_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
JSON_FENCE_ARR_RE = re.compile(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", re.DOTALL)
SQUARE_BRACKET_RE = re.compile(r"\[([^\]]+)\]")
_SENTENCE_END_RE = re.compile(r'''[.!?…]+(?:["'”’）)\]]*)?$''')


def normalize_story_mode(mode: Optional[str]) -> str:
    value = str(mode or "trend").strip().lower()
    return value if value in SUPPORTED_STORY_MODES else "trend"


def _load_base_mode_defaults(project_root: Path | None = None) -> Dict[str, Dict[str, str]]:
    root = resolve_project_root(project_root)
    config_path = resolve_presets_root(root) / DEFAULT_BASE_MODE_ASSET_FILE
    if not config_path.exists() or not config_path.is_file():
        return {}
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    base_modes = data.get("base_modes", data)
    if not isinstance(base_modes, dict):
        return {}
    normalized: Dict[str, Dict[str, str]] = {}
    for raw_mode, raw_value in base_modes.items():
        mode_key = normalize_story_mode(raw_mode)
        if mode_key not in SUPPORTED_STORY_MODES or not isinstance(raw_value, dict):
            continue
        entry: Dict[str, str] = {}
        for field in ("brief", "prompt", "label", "preset_mode"):
            value = raw_value.get(field)
            if isinstance(value, str) and value.strip():
                entry[field] = value.strip()
        if entry:
            normalized[mode_key] = entry
    return normalized


def default_mode_asset_contract(mode: str) -> Dict[str, str]:
    normalized_mode = normalize_story_mode(mode)
    defaults = _load_base_mode_defaults()
    entry = defaults.get(normalized_mode, {})
    return {k: v for k, v in entry.items() if isinstance(v, str) and v.strip()}


def _default_mode_asset_from_contract(mode: str, field: str) -> str | None:
    contract = default_mode_asset_contract(mode)
    value = contract.get(field)
    if not value:
        return None
    root = resolve_project_root()
    resolved = resolve_asset_reference(value, project_root=root)
    if resolved.exists() and resolved.is_file():
        assets_root = resolve_modes_root(root).parent
        for base in (root, assets_root.parent):
            try:
                return resolved.relative_to(base).as_posix()
            except ValueError:
                pass
        return resolved.as_posix()
    return None


def _default_mode_asset(mode: str, suffix: str) -> str:
    mode = normalize_story_mode(mode)
    field = "prompt" if suffix.endswith(".txt") else "brief"
    contract_value = _default_mode_asset_from_contract(mode, field)
    if contract_value:
        return contract_value

    root = resolve_project_root()
    modes_root = resolve_modes_root(root)
    preferred = modes_root / f"{mode}{suffix}"
    if preferred.exists():
        return preferred.resolve().relative_to(root).as_posix()

    if modes_root.exists():
        candidates = sorted(modes_root.glob(f"*{suffix}"))
        if candidates:
            return candidates[0].resolve().relative_to(root).as_posix()

    legacy_folder = "prompts" if suffix.endswith(".txt") else "examples"
    legacy_name = f"{mode}_audio_story_prompt.txt" if suffix.endswith(".txt") else f"{mode}_audio_story.example.yml"
    return f"{legacy_folder}/{legacy_name}"


def default_prompt_filename_for_mode(mode: str) -> str:
    return _default_mode_asset(mode, "_prompt.txt")


def default_brief_filename_for_mode(mode: str) -> str:
    return _default_mode_asset(mode, "_brief.yml")


def mode_profile(mode: str) -> Dict[str, str]:
    mode = normalize_story_mode(mode)
    if mode == "calm":
        return {
            "label": "calm fictional story",
            "genre_default": "calm audio story",
            "audience_default": "Người nghe cần thư giãn trước khi ngủ",
            "theme_default": "Một hành trình đêm yên tĩnh và an toàn",
            "tone_default": "êm, chậm, ấm, an toàn",
            "length_default": "ngắn gọn ~3–5 phút",
            "scene_defaults": "- con đường yên tĩnh dưới đèn vàng\n- hiên nhà có gió nhẹ\n- khu vườn nhỏ sau cơn mưa\n- bước chân chậm và nhịp thở đều",
            "content_rules": "- Câu chuyện phải êm, chậm, an toàn, dễ ngủ.\n- Không dùng sách thật, tác giả thật, công ty thật, nhân vật công chúng, sự kiện thật, hay business facts.\n- Không viết theo kiểu summary, review, lesson, case study, explainer, self-help guide, hay productivity advice.",
            "meta_rule": "- Viết calm fictional story, không bám sách thật hay factual content.\n- Không dùng business facts, tóm tắt kiến thức, bài học thành công, hay case study.\n- Không dùng nhân vật thật, tác giả thật, công ty thật, thương hiệu thật, hay sự kiện thật.",
            "chunk_rule": "- Chỉ dùng hình ảnh trung tính, nhịp chậm, cảm giác an toàn và chuyển cảnh mềm.",
        }
    return {
        "label": "trend fictional story",
        "genre_default": "trend audio story",
        "audience_default": "Người nghe thích câu chuyện bắt tai, hiện đại, giàu hình ảnh",
        "theme_default": "Một câu chuyện hư cấu theo xu hướng với nhịp sống hiện đại và cảm xúc gần gũi",
        "tone_default": "bắt tai, đương đại, cinematic, ấm áp",
        "length_default": "ngắn gọn ~3–5 phút",
        "scene_defaults": "- hành lang chung cư khi đèn vừa lên\n- quán nhỏ cuối phố sau cơn mưa\n- màn hình điện thoại sáng nhẹ trong đêm\n- nhịp bước nhanh rồi chậm lại ở đoạn kết",
        "content_rules": "- Câu chuyện phải hư cấu, hiện đại, dễ vào tai, có nhịp cuốn hút nhưng vẫn an toàn.\n- Không dùng sách thật, tác giả thật, công ty thật, nhân vật công chúng, sự kiện thật, hay business facts.\n- Không viết theo kiểu summary, review, lesson, case study, explainer, self-help guide, hay productivity advice.",
        "meta_rule": "- Viết trend fictional story, hiện đại, cinematic, không bám sách thật hay factual content.\n- Không dùng business facts, tóm tắt kiến thức, bài học thành công, hay case study.\n- Không dùng nhân vật thật, tác giả thật, công ty thật, thương hiệu thật, hay sự kiện thật.",
        "chunk_rule": "- Ưu tiên hình ảnh đương đại, nhịp cuốn hút vừa phải, chuyển cảnh rõ nhưng không gây gắt.",
    }


def eprint(*args):
    print(*args, file=sys.stderr)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    try:
        return float(v)
    except ValueError:
        return default


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_output_base(output_arg: str) -> Path:
    return Path(output_arg)
