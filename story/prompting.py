from __future__ import annotations

from textwrap import dedent
from typing import Any, Dict, List

from .audio_story_spec import ALLOWED_SCRIPT_ZONES, OUTLINE_KEYS
from .common import mode_profile


ZONE_TO_OUTLINE_KEY = {
    "LỜI CHÀO": "greeting",
    "MỞ TRUYỆN": "opening",
    "GIỚI THIỆU": "introduction",
    "TRIỂN KHAI": "development",
    "CAO TRÀO": "climax",
    "HẠ MÀN": "falling",
    "KẾT TRUYỆN": "ending",
    "TẠM BIỆT": "farewell",
}


def compute_required_min_items(brief: Dict[str, Any]) -> int:
    goals = brief.get("goals") or {}
    duration_min = int(goals.get("target_duration_min", 0) or 0)
    return duration_min * 12 if duration_min > 0 else 120


def build_user_prompt(brief: Dict[str, Any], mode: str = "trend") -> str:
    profile = mode_profile(mode)
    genre = str(brief.get("genre", profile["genre_default"])).strip()
    audience = str(brief.get("audience", profile["audience_default"])).strip()
    theme = str(brief.get("theme", profile["theme_default"])).strip()
    tone = str(brief.get("tone", profile["tone_default"])).strip()
    length_target = str(brief.get("length_target", profile["length_default"])).strip()
    language = str(brief.get("language", "vi")).strip().lower()
    key_scenes = brief.get("key_scenes") or []
    variation = brief.get("variation") or {}
    story_seed = str(variation.get("seed") or "").strip()
    seed_instruction = str(variation.get("instruction") or "").strip()
    if isinstance(key_scenes, list) and key_scenes:
        key_scenes_text = "\n".join([f"- {str(x).strip()}" for x in key_scenes if str(x).strip()])
    else:
        key_scenes_text = profile["scene_defaults"]
    required_min_items = compute_required_min_items(brief)
    lang_tag = "VI" if language.startswith("vi") else "EN"
    return dedent(
        f"""
        You are generating a fictional audio-story package.
        Return JSON only. Do not add markdown fences, comments, or trailing commas.

        Story constraints:
        - genre: {genre}
        - audience: {audience}
        - theme: {theme}
        - tone: {tone}
        - target length: {length_target}
        - language: {language}
        - creative seed: {story_seed or 'not specified'}
        - seed instruction: {seed_instruction or 'Use the brief as the primary creative direction.'}
        - required minimum script items: {required_min_items}
        - key scenes:
        {key_scenes_text}

        Script constraints:
        - Use only these zones: {' | '.join(ALLOWED_SCRIPT_ZONES)}
        - Each script item must contain exactly one spoken line in the text field.
        - Do not include square brackets in text.
        - Keep the story fictional and do not reference real copyrighted works.
        - Ensure the full script contains at least {required_min_items} items.

        Output schema:
        {{
          "meta": {{
            "title": "string (tiêu đề hư cấu, không bám tác phẩm thật)",
            "series": "string (có thể rỗng)",
            "episode": "string (có thể rỗng)",
            "author": "string (ví dụ: Audio Story hoặc Night Narrator)",
            "channel": "string",
            "target": "string",
            "length_min": 3,
            "length_max": 5,
            "language": "{language}",
            "genre": "{genre}",
            "audience": "{audience}",
            "tone": "{tone}",
            "tags": ["string", "..."]
          }},
          "outline": {{
            "greeting": "string",
            "opening": "string",
            "introduction": "string",
            "development": "string",
            "climax": "string",
            "falling": "string",
            "ending": "string",
            "farewell": "string"
          }},
          "script": [
            {{
              "zone": "LỜI CHÀO|MỞ TRUYỆN|GIỚI THIỆU|TRIỂN KHAI|CAO TRÀO|HẠ MÀN|KẾT TRUYỆN|TẠM BIỆT",
              "environment": "",
              "voice": "NARRATOR|MALE|FEMALE",
              "speed": "SLOW|NORMAL|FAST",
              "lang": "{lang_tag}",
              "text": "câu thoại duy nhất (không chứa [ hoặc ])"
            }}
          ]
        }}
        """
    ).strip()



def build_meta_outline_prompt(brief: Dict[str, Any], mode: str = "trend") -> str:
    profile = mode_profile(mode)
    language_primary = str((brief.get("project") or {}).get("language_primary", "VI")).strip().upper()
    lang_tag = "VI" if language_primary.startswith("VI") else "EN"
    language_value = "vi" if lang_tag == "VI" else "en"
    genre = str(brief.get("genre", profile["genre_default"])).strip()
    audience = str(brief.get("audience", profile["audience_default"])).strip()
    theme = str(brief.get("theme", profile["theme_default"])).strip()
    tone = str(brief.get("tone", profile["tone_default"])).strip()
    length_target = str(brief.get("length_target", profile["length_default"])).strip()
    key_scenes = brief.get("key_scenes") or []
    variation = brief.get("variation") or {}
    story_seed = str(variation.get("seed") or "").strip()
    seed_instruction = str(variation.get("instruction") or "").strip()
    if isinstance(key_scenes, list) and key_scenes:
        key_scenes_text = "\n".join([f"- {str(x).strip()}" for x in key_scenes if str(x).strip()])
    else:
        key_scenes_text = profile["scene_defaults"]
    return dedent(
        f"""
        You are creating story metadata and a high-level outline for a fictional audio story.
        Return JSON only. Do not add markdown fences, comments, or trailing commas.

        Story brief:
        - genre: {genre}
        - audience: {audience}
        - theme: {theme}
        - tone: {tone}
        - target length: {length_target}
        - language: {language_value}
        - creative seed: {story_seed or 'not specified'}
        - seed instruction: {seed_instruction or 'Use the brief as the primary creative direction.'}
        - key scenes:
        {key_scenes_text}

        Requirements:
        - Fill meta and outline only.
        - Every outline field must be present and non-empty.
        - Keep every outline field short: one sentence, maximum 120 characters.
        - greeting and farewell are mandatory and must not be blank.
        - Keep script as an empty array.
        - Keep the story fictional and do not reference real copyrighted works.
        - Return compact minified JSON only, with no explanation before or after the JSON.

        Output schema:
        {{
          "meta": {{
            "title": "string",
            "series": "string",
            "episode": "string",
            "author": "string",
            "channel": "Audio Story",
            "target": "string",
            "length_min": 3,
            "length_max": 5,
            "language": "{language_value}",
            "genre": "{genre}",
            "audience": "{audience}",
            "tone": "{tone}",
            "tags": ["string", "..."]
          }},
          "outline": {{
            "greeting": "string",
            "opening": "string",
            "introduction": "string",
            "development": "string",
            "climax": "string",
            "falling": "string",
            "ending": "string",
            "farewell": "string"
          }},
          "script": []
        }}
        """
    ).strip()



def build_zone_chunk_prompt(meta: Dict[str, Any], outline: Dict[str, str], zone: str, n_items: int, lang_tag: str = "VI", speed: str = "NORMAL", mode: str = "trend") -> str:
    profile = mode_profile(mode)
    title = str(meta.get("title", "")).strip()
    author = str(meta.get("author", "")).strip()
    tone = str(meta.get("tone", profile["tone_default"])).strip()
    genre = str(meta.get("genre", profile["genre_default"])).strip()
    audience = str(meta.get("audience", profile["audience_default"])).strip()
    outline_lines: List[str] = []
    if isinstance(outline, dict):
        for key in OUTLINE_KEYS:
            value = str(outline.get(key, "")).strip()
            if value:
                outline_lines.append(f"- {key}: {value}")
    outline_text = "\n".join(outline_lines) if outline_lines else "- (none)"
    zone_outline_key = ZONE_TO_OUTLINE_KEY.get(zone, "")
    zone_hint = str(outline.get(zone_outline_key, "")).strip() if isinstance(outline, dict) else ""
    if zone_hint:
        zone_focus = f"- zone focus: {zone_hint}"
    else:
        zone_focus = "- zone focus: follow the outline and the intended dramatic role of this zone"

    return dedent(
        f"""
        Write exactly {n_items} script items for the zone "{zone}".
        Return a JSON array only. Do not add markdown fences, comments, or trailing commas.

        Story context:
        - title: {title or '(untitled)'}
        - author: {author or 'Audio Story'}
        - genre: {genre}
        - audience: {audience}
        - tone: {tone}
        - language tag: {lang_tag}
        - speed: {speed}
        {zone_focus}

        Full outline:
        {outline_text}

        Requirements:
        - Every item must use zone = "{zone}".
        - Use environment = "" unless a later stage populates it.
        - Use a single spoken sentence or line per item.
        - Do not include square brackets in text.
        - Keep continuity with the outline and previous story context.
        - Keep output fictional and safe for narration.

        Output format:
        [
          {{"zone":"{zone}","environment":"","voice":"NARRATOR","speed":"{speed}","lang":"{lang_tag}","text":"..."}}
        ]
        """
    ).strip()



def build_default_zone_counts(min_lines: int) -> Dict[str, int]:
    base = {
        "LỜI CHÀO": 8,
        "MỞ TRUYỆN": 16,
        "GIỚI THIỆU": 24,
        "TRIỂN KHAI": 70,
        "CAO TRÀO": 24,
        "HẠ MÀN": 16,
        "KẾT TRUYỆN": 16,
        "TẠM BIỆT": 8,
    }
    total = sum(base.values())
    if min_lines > total:
        base["TRIỂN KHAI"] += min_lines - total
    return base
