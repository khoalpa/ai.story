from __future__ import annotations

import ast
import json
import re
from typing import Any, Dict, List, Tuple

from .audio_story_spec import validate_canonical_authoring
from .common import ALLOWED_DSL_TAGS, JSON_FENCE_ARR_RE, JSON_FENCE_OBJ_RE, SQUARE_BRACKET_RE


def _strip_fence(t: str) -> str:
    t = (t or "").strip()
    m = JSON_FENCE_OBJ_RE.search(t)
    if m:
        return m.group(1).strip()
    m = JSON_FENCE_ARR_RE.search(t)
    if m:
        return m.group(1).strip()
    return t




def _strip_json_comments(text: str) -> str:
    return re.sub(r"(?m)^\s*//.*$", "", re.sub(r"/\*.*?\*/", "", text or "", flags=re.DOTALL))


def _remove_trailing_commas(text: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", text or "")


def _normalize_jsonish_text(text: str) -> str:
    cleaned = (text or "").strip().lstrip("﻿")
    cleaned = cleaned.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    cleaned = _strip_json_comments(cleaned)
    cleaned = _remove_trailing_commas(cleaned)
    return cleaned.strip()


def _parse_jsonish(candidate: str) -> Any:
    text = _normalize_jsonish_text(candidate)
    if not text:
        raise json.JSONDecodeError("Empty JSON text", candidate or "", 0)
    try:
        return json.loads(text)
    except json.JSONDecodeError as json_exc:
        py_like = re.sub(r"\btrue\b", "True", text, flags=re.IGNORECASE)
        py_like = re.sub(r"\bfalse\b", "False", py_like, flags=re.IGNORECASE)
        py_like = re.sub(r"\bnull\b", "None", py_like, flags=re.IGNORECASE)
        try:
            return ast.literal_eval(py_like)
        except (SyntaxError, ValueError) as ast_exc:
            raise json_exc from ast_exc

def extract_json(llm_text: str) -> Dict[str, Any]:
    t = _strip_fence(llm_text)
    dec = json.JSONDecoder()
    try:
        obj = _parse_jsonish(t)
        if not isinstance(obj, dict):
            raise ValueError("Top-level JSON is not an object.")
        return obj
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    for seg in _iter_json_segments(t):
        try:
            obj = _parse_jsonish(seg)
            if isinstance(obj, dict):
                return obj
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    start = t.find("{")
    if start != -1:
        try:
            obj, _ = dec.raw_decode(_normalize_jsonish_text(t[start:]))
            if isinstance(obj, dict):
                return obj
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = t[start:end + 1].strip()
        obj = _parse_jsonish(candidate)
        if not isinstance(obj, dict):
            raise ValueError("Top-level JSON is not an object.")
        return obj
    obj = _parse_jsonish(t)
    if not isinstance(obj, dict):
        raise ValueError("Top-level JSON is not an object.")
    return obj


def _coerce_nested_json_strings(value: Any, *, max_depth: int = 3) -> Any:
    current = value
    for _ in range(max_depth):
        if not isinstance(current, str):
            return current
        text = current.strip()
        if not text:
            return current
        if not ((text.startswith('[') and text.endswith(']')) or (text.startswith('{') and text.endswith('}'))):
            return current
        try:
            current = _parse_jsonish(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return current
    return current


def _as_array(obj: Any) -> list[Any] | None:
    obj = _coerce_nested_json_strings(obj)
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("script", "items", "data", "lines", "result", "output"):
            v = _coerce_nested_json_strings(obj.get(k))
            if isinstance(v, list):
                return v
    return None


def _iter_json_segments(text: str) -> list[str]:
    segments: list[str] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if ch not in '[{':
            i += 1
            continue
        opener = ch
        closer = ']' if ch == '[' else '}'
        depth = 0
        in_str = False
        escape = False
        start = i
        j = i
        while j < n:
            c = text[j]
            if in_str:
                if escape:
                    escape = False
                elif c == '\\':
                    escape = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == opener:
                    depth += 1
                elif c == closer:
                    depth -= 1
                    if depth == 0:
                        segments.append(text[start:j + 1].strip())
                        i = j
                        break
            j += 1
        i += 1
    return segments


def _extract_object_lines_as_array(text: str) -> list[Any] | None:
    objects: list[Any] = []
    for line in (text or '').splitlines():
        candidate = line.strip().rstrip(',')
        if not candidate:
            continue
        if candidate.startswith('```'):
            continue
        if candidate.startswith('{') and candidate.endswith('}'):
            try:
                parsed = _parse_jsonish(candidate)
                if isinstance(parsed, dict):
                    objects.append(parsed)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
    return objects or None


def _extract_text_lines_as_array(text: str) -> list[str] | None:
    lines: list[str] = []
    for raw in (text or '').splitlines():
        line = raw.strip()
        if not line or line.startswith('```'):
            continue
        line = re.sub(r'^[-*•]\s+', '', line)
        line = re.sub(r'^\d+[.)]\s+', '', line)
        line = line.strip().strip('"')
        if not line:
            continue
        if line.startswith('{') or line.startswith('['):
            continue
        lines.append(line)
    return lines or None


def extract_json_array(llm_text: str) -> list:
    t = _strip_fence((llm_text or '').strip().lstrip('﻿'))
    dec = json.JSONDecoder()

    for candidate in (t, t.strip('`').strip()):
        if not candidate:
            continue
        try:
            obj = _parse_jsonish(candidate)
            arr = _as_array(obj)
            if arr is not None:
                return arr
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    for seg in _iter_json_segments(t):
        for parser in (_parse_jsonish, lambda x: dec.raw_decode(_normalize_jsonish_text(x))[0]):
            try:
                obj = parser(seg)
                arr = _as_array(obj)
                if arr is not None:
                    return arr
            except (TypeError, ValueError, json.JSONDecodeError):
                continue

    start_o = t.find('{')
    if start_o != -1:
        try:
            obj, _ = dec.raw_decode(_normalize_jsonish_text(t[start_o:]))
            arr = _as_array(obj)
            if arr is not None:
                return arr
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    start_a = t.find('[')
    if start_a != -1:
        try:
            obj, _ = dec.raw_decode(_normalize_jsonish_text(t[start_a:]))
            arr = _as_array(obj)
            if arr is not None:
                return arr
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    line_objects = _extract_object_lines_as_array(t)
    if line_objects is not None:
        return line_objects

    line_texts = _extract_text_lines_as_array(t)
    if line_texts is not None:
        return line_texts

    preview = re.sub(r'\s+', ' ', t)[:220]
    raise ValueError(f"Could not extract JSON array from model output. preview={preview}")


def find_illegal_square_brackets(s: str) -> List[str]:
    bad = []
    for m in SQUARE_BRACKET_RE.finditer(s):
        inner = m.group(1).strip()
        if inner.upper() not in ALLOWED_DSL_TAGS:
            bad.append(inner)
    return bad


def validate_authoring(obj: Dict[str, Any]) -> Tuple[bool, str]:
    errors = validate_canonical_authoring(obj)
    if errors:
        return False, "; ".join(errors)
    return True, "OK"
