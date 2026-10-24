"""Edit a validated story draft without changing its identity or package on disk."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from audio.story_package_v416 import (
    ZONE_LABELS,
    ZONES,
    parse_story_text,
    validate_story,
)

EDITABLE_FIELDS = frozenset({"speaker", "text", "emotion", "speed", "pause_ms", "ambience"})
DRAFT_KEY = "audio_story_editor_is_draft"


def update_story_item(source: str, script_id: str, changes: Mapping[str, Any]) -> str:
    """Only update existing editable fields; retain every ID, order and schema field."""
    if not set(changes) <= EDITABLE_FIELDS:
        raise ValueError("Chỉ được sửa lời thoại, người nói, cảm xúc, tốc độ, khoảng nghỉ và âm nền.")
    story = parse_story_text(source)
    item = next((row for row in story["script"] if row["id"] == script_id), None)
    if item is None:
        raise ValueError("Không tìm thấy câu thoại trong bản nháp hiện tại.")
    item.update(changes)
    errors = validate_story(story)
    if errors:
        raise ValueError("\n".join(errors))
    return json.dumps(story, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def save_story_draft(state: MutableMapping[str, Any], script_id: str, prefix: str, expected_digest: str) -> None:
    source = str(state.get("canonical_editor") or state.get("canonical_json_text") or "")
    if hashlib.sha256(source.encode("utf-8")).hexdigest() != expected_digest:
        state["audio_story_editor_error"] = "Nguồn vừa thay đổi. Hãy chọn lại câu thoại rồi lưu bản nháp."
        return
    changes = {field: state[f"{prefix}_{field}"] for field in EDITABLE_FIELDS}
    try:
        original = next(row for row in parse_story_text(source)["script"] if row["id"] == script_id)
        if changes["ambience"] == "" and original["ambience"] != "":
            changes["ambience"] = None
        updated = update_story_item(source, script_id, changes)
    except ValueError as exc:
        state["audio_story_editor_error"] = str(exc)
        return
    state["canonical_json_text"] = updated
    state["canonical_editor"] = updated
    state[DRAFT_KEY] = True
    state.pop("audio_story_editor_error", None)


def editor_image(root: Path, script_id: str, zone: str) -> Path | None:
    names = [f"{zone.lower()}.png"]
    try:
        plan = json.loads((root / "visual_plan.json").read_text(encoding="utf-8-sig"))
        if plan.get("image_mode") == "SCENE":
            names = [row["basename"] for row in plan.get("assets", [])
                     if isinstance(row, dict) and script_id in row.get("source_script_ids", [])
                     and isinstance(row.get("basename"), str)]
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    for aspect in ("landscape", "portrait"):
        directory = (root / aspect).resolve()
        if not directory.is_relative_to(root.resolve()):
            continue
        for name in names:
            path = (directory / name).resolve()
            if path.parent == directory and path.is_file():
                return path
    return None


def render_story_editor(project_root: Path | None = None) -> None:
    import streamlit as st

    source = str(st.session_state.get("canonical_editor") or st.session_state.get("canonical_json_text") or "")
    if not source.strip():
        st.info("Mở story.json để chỉnh từng câu thoại.")
        return
    try:
        story = parse_story_text(source)
    except ValueError as exc:
        st.warning(f"Cần sửa JSON hợp lệ trước khi dùng biểu mẫu: {exc}")
        return
    if st.session_state.get(DRAFT_KEY):
        st.warning("Đây là bản nháp trong phiên làm việc. Báo cáo kiểm định và ảnh của gói nguồn chưa xác nhận nội dung vừa sửa.")
    if st.session_state.get("audio_story_editor_error"):
        st.error(st.session_state["audio_story_editor_error"])
    st.caption("Giữ nguyên ID, zone, cảnh và thứ tự câu. Lưu bản nháp chỉ cập nhật ô JSON; gói nguồn trên đĩa được giữ nguyên.")
    zone = st.selectbox("Phần truyện", list(ZONES), format_func=lambda value: ZONE_LABELS[value], key="story_editor_zone")
    items = [row for row in story["script"] if row["zone"] == zone]
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    script_id = st.selectbox("Câu thoại", [row["id"] for row in items], key=f"story_editor_item_{zone}_{digest[:12]}",
                             format_func=lambda value: next(f"{row['id']} · {row['text'][:80]}" for row in items if row["id"] == value))
    item = next(row for row in items if row["id"] == script_id)
    prefix = f"story_edit_{script_id}_{digest[:12]}"
    speakers = {"narrator": "Người kể chuyện", **{row["character_id"]: row["name"] for row in story["characters"]}}
    st.caption(f"Cảnh {item['scene_id']} · {len(items)} câu trong phần này")
    columns = st.columns([2, 1])
    with columns[0], st.form(f"{prefix}_form"):
        st.text_area("Lời thoại", value=item["text"], key=f"{prefix}_text", height=140)
        st.selectbox("Người nói", list(speakers), index=list(speakers).index(item["speaker"]),
                     format_func=lambda value: speakers[value], key=f"{prefix}_speaker")
        st.text_input("Cảm xúc", value=item["emotion"], key=f"{prefix}_emotion")
        st.number_input("Tốc độ đọc", value=float(item["speed"]), step=0.05, key=f"{prefix}_speed")
        st.number_input("Khoảng nghỉ sau câu (ms)", min_value=0, value=item["pause_ms"], step=50, key=f"{prefix}_pause_ms")
        st.text_input("Âm nền của câu (để trống nếu không có)", value=item["ambience"] or "", key=f"{prefix}_ambience")
        st.form_submit_button("Lưu bản nháp", on_click=save_story_draft,
                              args=(st.session_state, script_id, prefix, digest))
    with columns[1]:
        seconds = len(item["text"].strip()) / 14.0 / float(item["speed"]) + item["pause_ms"] / 1000
        st.metric("Ước tính câu đang lưu", f"{seconds:.1f} giây")
        st.caption("Ước tính theo độ dài chữ, tốc độ đọc và khoảng nghỉ; chưa phải thời lượng audio thực tế.")
        image = editor_image(project_root, script_id, zone) if project_root else None
        if image:
            try:
                st.image(str(image), caption="Ảnh của gói nguồn", width="stretch")
            except (OSError, ValueError):
                st.info("Ảnh nguồn không đọc được.")
        else:
            st.info("Chưa có ảnh nguồn cho câu này.")
    st.download_button("Tải story.draft.json", data=source.encode("utf-8"), file_name="story.draft.json",
                       mime="application/json", key="story_editor_download")
    st.caption("Bản nháp giữ schema hiện tại. Cần kiểm định lại trước khi dùng để thay thế một gói đã phát hành.")
