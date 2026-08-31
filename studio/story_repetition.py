"""Sentence-level repetition analysis for canonical story.json documents."""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Mapping

from studio.package_quality_report import _items

REPORT_FILENAME = "story.repetition_report.json"
DEFAULT_SIMILARITY_THRESHOLD = 0.82
MIN_WORDS = 5
_SENTENCE_RE = re.compile(r".+?(?:[.!?…]+(?:[\"'”’\)\]]+)?(?=\s|$)|$)", re.DOTALL)
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


def split_sentences(text: str) -> list[str]:
    return [match.group(0).strip() for match in _SENTENCE_RE.finditer(text.strip()) if match.group(0).strip()]


def normalize_sentence(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text).casefold()
    return " ".join(_WORD_RE.findall(normalized))


def _tokens(normalized: str) -> tuple[str, ...]:
    return tuple(normalized.split())


def _similarity(left: str, right: str) -> float:
    left_tokens, right_tokens = set(_tokens(left)), set(_tokens(right))
    union = left_tokens | right_tokens
    token_score = len(left_tokens & right_tokens) / len(union) if union else 0.0
    sequence_score = SequenceMatcher(None, left, right, autojunk=False).ratio()
    return max(sequence_score, 0.55 * sequence_score + 0.45 * token_score)


def extract_story_sentences(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    sentences: list[dict[str, Any]] = []
    global_index = 0
    for block_index, item in enumerate(_items(report.get("script"))):
        for sentence_index, text in enumerate(split_sentences(str(item.get("text") or ""))):
            normalized = normalize_sentence(text)
            words = _tokens(normalized)
            global_index += 1
            sentences.append({
                "sentence_number": global_index,
                "block_index": block_index,
                "block_number": block_index + 1,
                "sentence_in_block": sentence_index + 1,
                "zone": str(item.get("zone") or "UNKNOWN"),
                "voice": str(item.get("voice") or "UNKNOWN"),
                "text": text,
                "normalized": normalized,
                "word_count": len(words),
            })
    return sentences


def analyze_story_repetition(
    report: Mapping[str, Any],
    *,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    minimum_words: int = MIN_WORDS,
) -> dict[str, Any]:
    sentences = extract_story_sentences(report)
    eligible = [item for item in sentences if item["word_count"] >= minimum_words]
    pairs: list[dict[str, Any]] = []
    exact_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in eligible:
        exact_groups[item["normalized"]].append(item)
    for group in exact_groups.values():
        if len(group) < 2:
            continue
        for index, left in enumerate(group):
            for right in group[index + 1:]:
                pairs.append(_pair_row(left, right, 1.0, "exact"))
    unique_groups = list(exact_groups.values())
    for group_index, left_group in enumerate(unique_groups):
        left = left_group[0]
        for right_group in unique_groups[group_index + 1:]:
            right = right_group[0]
            shorter, longer = sorted((left["word_count"], right["word_count"]))
            if longer and shorter / longer < 0.55:
                continue
            score = _similarity(left["normalized"], right["normalized"])
            if score >= similarity_threshold:
                for left_item in left_group:
                    for right_item in right_group:
                        earlier, later = sorted(
                            (left_item, right_item), key=lambda item: item["sentence_number"]
                        )
                        pairs.append(_pair_row(earlier, later, score, "near"))
    pairs.sort(key=lambda item: (-item["similarity"], item["left"]["sentence_number"], item["right"]["sentence_number"]))
    by_type = Counter(item["type"] for item in pairs)
    by_severity = Counter(item["severity"] for item in pairs)
    affected = {item[side]["sentence_number"] for item in pairs for side in ("left", "right")}
    zones = sorted({item[side]["zone"] for item in pairs for side in ("left", "right")})
    return {
        "schema_version": 1,
        "kind": "story.repetition-report",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "settings": {"similarity_threshold": similarity_threshold, "minimum_words": minimum_words},
        "summary": {
            "total_sentences": len(sentences),
            "eligible_sentences": len(eligible),
            "pair_count": len(pairs),
            "exact_pair_count": by_type["exact"],
            "near_pair_count": by_type["near"],
            "high_severity_count": by_severity["high"],
            "affected_sentence_count": len(affected),
            "affected_zones": zones,
        },
        "pairs": pairs,
    }


def _pair_row(left: Mapping[str, Any], right: Mapping[str, Any], score: float, kind: str) -> dict[str, Any]:
    severity = "high" if kind == "exact" and min(left["word_count"], right["word_count"]) >= 8 else (
        "medium" if kind == "exact" or score >= 0.9 else "low"
    )
    fields = ("sentence_number", "block_index", "block_number", "sentence_in_block", "zone", "voice", "text", "word_count")
    return {
        "type": kind,
        "severity": severity,
        "similarity": round(score, 4),
        "distance": right["sentence_number"] - left["sentence_number"],
        "same_zone": left["zone"] == right["zone"],
        "left": {field: left[field] for field in fields},
        "right": {field: right[field] for field in fields},
    }


def repetition_report_json(report: Mapping[str, Any]) -> bytes:
    return json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")


def render_repetition_report(
    story: Mapping[str, Any], *,
    image_catalog: Mapping[str, Mapping[str, Path]] | None = None,
    image_aspect: str = "landscape",
) -> None:
    import streamlit as st

    from studio.story_images import image_for_zone, render_image_thumbnail

    threshold_percent = st.slider(
        "Ngưỡng gần trùng", min_value=82, max_value=98, value=82, step=1,
        format="%d%%", help="Ngưỡng cao cho ít cảnh báo hơn nhưng có thể bỏ sót câu viết lại nhẹ.",
        key="story_repetition_threshold",
    )
    report = analyze_story_repetition(story, similarity_threshold=threshold_percent / 100)
    summary, pairs = report["summary"], report["pairs"]
    columns = st.columns(5)
    for column, (label, value) in zip(columns, (
        ("Tổng số câu", summary["total_sentences"]),
        ("Lặp chính xác", summary["exact_pair_count"]),
        ("Gần trùng", summary["near_pair_count"]),
        ("Câu bị ảnh hưởng", summary["affected_sentence_count"]),
        ("Vùng bị ảnh hưởng", len(summary["affected_zones"])),
    )):
        column.metric(label, value)
    if not pairs:
        st.success("Không phát hiện câu lặp cần xem lại với ngưỡng hiện tại.")
    else:
        st.warning(f"Phát hiện {len(pairs)} cặp câu cần xem lại. Kết quả chỉ là gợi ý, không tự động sửa nội dung.")
    filter_columns = st.columns(3)
    severity = filter_columns[0].multiselect(
        "Mức độ", ["high", "medium", "low"], default=["high", "medium", "low"],
        format_func=lambda value: {"high": "Cao", "medium": "Vừa", "low": "Thấp"}[value],
        key="story_repetition_severity",
    )
    kinds = filter_columns[1].multiselect(
        "Loại", ["exact", "near"], default=["exact", "near"],
        format_func=lambda value: "Chính xác" if value == "exact" else "Gần trùng",
        key="story_repetition_kind",
    )
    zone_options = sorted({item[side]["zone"] for item in pairs for side in ("left", "right")})
    zones = filter_columns[2].multiselect("Vùng truyện", zone_options, default=zone_options, key="story_repetition_zones")
    same_zone_only = st.checkbox("Chỉ hiện các cặp trong cùng vùng truyện", key="story_repetition_same_zone")
    visible = [item for item in pairs if item["severity"] in severity and item["type"] in kinds and (item["left"]["zone"] in zones or item["right"]["zone"] in zones) and (not same_zone_only or item["same_zone"])]
    st.dataframe([
        {
            "Mức độ": {"high": "Cao", "medium": "Vừa", "low": "Thấp"}[item["severity"]],
            "Loại": "Chính xác" if item["type"] == "exact" else "Gần trùng",
            "Câu gốc": f"#{item['left']['sentence_number']} · {item['left']['text']}",
            "Câu lặp": f"#{item['right']['sentence_number']} · {item['right']['text']}",
            "Vùng": f"{item['left']['zone']} → {item['right']['zone']}",
            "Độ giống": f"{item['similarity']:.0%}",
        }
        for item in visible
    ], width="stretch", hide_index=True)
    st.caption(f"Hiển thị {len(visible)}/{len(pairs)} cặp · Bỏ qua câu dưới {report['settings']['minimum_words']} từ")
    if visible and image_catalog is not None:
        selected_context = st.selectbox(
            "Ngữ cảnh hình ảnh",
            list(range(len(visible))),
            format_func=lambda index: (
                f"Câu {visible[index]['left']['sentence_number']} ↔ "
                f"{visible[index]['right']['sentence_number']} · {visible[index]['similarity']:.0%}"
            ),
            key="story_repetition_image_context",
        )
        context = visible[int(selected_context)]
        context_columns = st.columns(2)
        for column, side, label in zip(context_columns, ("left", "right"), ("Câu gốc", "Câu lặp")):
            item = context[side]
            with column:
                render_image_thumbnail(
                    image_for_zone(image_catalog, image_aspect, item["zone"]),
                    caption=f"{label} · {item['zone']} · {image_aspect.title()}",
                    key=f"repetition_{image_aspect}_{side}_{item['sentence_number']}",
                    frame_ratio=(16, 9),
                )
    for index, item in enumerate(visible[:30], start=1):
        with st.expander(f"{index}. Câu {item['left']['sentence_number']} ↔ {item['right']['sentence_number']} · {item['similarity']:.0%}"):
            left_col, right_col = st.columns(2)
            left_col.markdown(f"**Câu gốc · {item['left']['zone']} · block {item['left']['block_number']}**")
            left_col.write(item["left"]["text"])
            right_col.markdown(f"**Câu lặp · {item['right']['zone']} · block {item['right']['block_number']}**")
            right_col.write(item["right"]["text"])
            st.caption(f"Khoảng cách {item['distance']} câu · Voice {item['left']['voice']} → {item['right']['voice']}")
    st.download_button(
        "Tải báo cáo JSON", data=repetition_report_json(report), file_name=REPORT_FILENAME,
        mime="application/json", key="download_story_repetition_report",
    )


__all__ = [
    "DEFAULT_SIMILARITY_THRESHOLD", "MIN_WORDS", "REPORT_FILENAME",
    "analyze_story_repetition", "extract_story_sentences", "normalize_sentence",
    "render_repetition_report", "repetition_report_json", "split_sentences",
]
