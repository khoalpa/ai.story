from __future__ import annotations

from typing import List

from audio.pipeline.plain_script_parser import normalize_bgm_name
from audio.pipeline.script_pipeline import parse_and_resolve_plain_script


def classify_lines(full_text: str) -> List[dict]:
    results = parse_and_resolve_plain_script(full_text)
    for item in results:
        item["bgm_tag"] = normalize_bgm_name(item.get("bgm_tag"))
    return results
