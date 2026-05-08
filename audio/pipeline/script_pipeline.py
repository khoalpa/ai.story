from __future__ import annotations

from dataclasses import asdict
from typing import Any, List, Mapping, Optional

from audio.audio_story_spec import TAG_PATTERN, detect_zone_from_comment, extract_base_token
from audio.pipeline.flow_state import EnvironmentFlowState, ZoneFlowState
from audio.pipeline.plain_script_models import ParsedScriptLine, ResolvedScriptLine
from audio.pipeline.plain_script_parser import detect_env_from_text, map_sfx_value_to_env, parse_tags_and_text
from audio.pipeline.segment_planner import assign_segments, expand_silence_segments


def _extract_inline_env(raw_line: str) -> Optional[str]:
    tags = TAG_PATTERN.findall(raw_line)
    sfx_tags = [t for t in tags if extract_base_token(t.strip().upper()) == "SFX" or t.strip().upper().startswith("SFX=")]
    if not sfx_tags:
        return None
    tag = sfx_tags[-1]
    value = tag.split("=", 1)[1].strip() if "=" in tag else ""
    return map_sfx_value_to_env(value)


def parse_plain_script(full_text: str, *, voice_rate_map: Mapping[str, Any] | None = None) -> List[ParsedScriptLine]:
    parsed: List[ParsedScriptLine] = []

    for raw in full_text.splitlines():
        line = raw.strip()
        if not line or line.upper() == "SCRIPT:":
            continue

        if line.startswith("#") or line.startswith("//"):
            maybe_zone = detect_zone_from_comment(line)
            if maybe_zone:
                parsed.append(ParsedScriptLine(raw=raw, text="", kind="zone_comment", zone_hint=maybe_zone))
                continue

            comment_upper = line.lstrip("/ ").strip().upper()
            mapped_env = None
            if comment_upper.startswith("SFX"):
                val = ""
                if "=" in comment_upper:
                    _, val = comment_upper.split("=", 1)
                else:
                    parts = comment_upper.split(None, 1)
                    if len(parts) == 2:
                        val = parts[1]
                mapped_env = map_sfx_value_to_env(val)

            if mapped_env is not None:
                parsed.append(ParsedScriptLine(raw=raw, text="", kind="env_comment", env_hint=mapped_env))
            continue

        (
            voice_from_tag,
            rate_from_tag,
            bgm_from_tag,
            bgm_gain_db_from_tag,
            silence_ms,
            text_clean,
            lang_tag,
        ) = parse_tags_and_text(raw, voice_rate_map=voice_rate_map)

        parsed.append(
            ParsedScriptLine(
                raw=raw,
                text=text_clean,
                kind="content",
                voice_tag=voice_from_tag,
                rate_tag=rate_from_tag,
                bgm_tag=bgm_from_tag,
                bgm_db_tag=bgm_gain_db_from_tag,
                lang_tag=lang_tag,
                silence_ms=silence_ms,
                env_hint=_extract_inline_env(raw),
            )
        )

    return parsed


def resolve_script_flows(parsed_lines: List[ParsedScriptLine], *, voice_rate_map: Mapping[str, Any] | None = None) -> List[ResolvedScriptLine]:
    resolved: List[ResolvedScriptLine] = []
    zone_flow = ZoneFlowState()
    env_flow = EnvironmentFlowState()

    for item in parsed_lines:
        if item.kind == "zone_comment":
            zone_flow.apply_comment(item.zone_hint)
            continue
        if item.kind == "env_comment":
            env_flow.apply_comment(item.env_hint)
            continue

        line_env = item.env_hint
        if line_env is None and env_flow.current_env == "none":
            line_env = detect_env_from_text(item.text)
        resolved_env = env_flow.resolve_for_line(line_env)

        resolved.append(
            ResolvedScriptLine(
                raw=item.raw,
                text=item.text,
                zone=zone_flow.current_zone,
                env=resolved_env,
                voice_tag=item.voice_tag,
                rate_tag=item.rate_tag,
                bgm_tag=item.bgm_tag,
                bgm_db_tag=item.bgm_db_tag,
                lang_tag=item.lang_tag,
                silence_ms=item.silence_ms,
            )
        )

    return resolved


def resolved_lines_to_dicts(resolved_lines: List[ResolvedScriptLine]) -> List[dict]:
    return [asdict(item) for item in resolved_lines]


def parse_and_resolve_plain_script(full_text: str, *, voice_rate_map: Mapping[str, Any] | None = None) -> List[dict]:
    return resolved_lines_to_dicts(resolve_script_flows(parse_plain_script(full_text, voice_rate_map=voice_rate_map), voice_rate_map=voice_rate_map))


def plan_segments_from_plain_script(full_text: str, *, voice_rate_map: Mapping[str, Any] | None = None):
    return assign_segments(expand_silence_segments(parse_and_resolve_plain_script(full_text, voice_rate_map=voice_rate_map)), voice_rate_map=voice_rate_map)
