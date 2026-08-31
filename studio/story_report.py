"""Friendly Streamlit viewer for canonical story.json files."""
from __future__ import annotations

from collections import Counter
from html import escape
from pathlib import Path
from typing import Any, BinaryIO, Mapping

from studio.package_quality_report import _items, _object, _read_report, _short_digest
from studio.project_assets import file_facts, project_asset_path
from studio.report_semantics import display_score
from studio.story_images import (
    ASPECTS,
    discover_story_images,
    image_for_zone,
    render_image_thumbnail,
)
from studio.story_repetition import render_repetition_report

ZONE_ORDER = (
    "GREETING",
    "OPENING",
    "INTRODUCTION",
    "DEVELOPMENT",
    "CLIMAX",
    "FALLING",
    "ENDING",
    "FAREWELL",
)

ZONE_LABELS = {
    "GREETING": "Lời chào",
    "OPENING": "Mở đầu",
    "INTRODUCTION": "Giới thiệu",
    "DEVELOPMENT": "Phát triển",
    "CLIMAX": "Cao trào",
    "FALLING": "Hạ nhiệt",
    "ENDING": "Kết thúc",
    "FAREWELL": "Tạm biệt",
}

OUTLINE_KEYS = {
    "greeting": "Lời chào",
    "opening": "Mở đầu",
    "introduction": "Giới thiệu",
    "development": "Phát triển",
    "climax": "Cao trào",
    "falling": "Hạ nhiệt",
    "ending": "Kết thúc",
    "farewell": "Tạm biệt",
}

VOICE_LABELS = {
    "NARRATOR": "Người kể",
    "FEMALE": "Giọng nữ",
    "MALE": "Giọng nam",
}


def _validate_story(report: Mapping[str, Any]) -> None:
    required = {"meta", "characters", "outline", "script"}
    missing = sorted(required.difference(report))
    if missing:
        raise ValueError("Tệp không đúng định dạng story.json; thiếu: " + ", ".join(missing))
    if not isinstance(report.get("script"), list):
        raise ValueError("Trường script phải là một danh sách.")


def _script_items(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return _items(report.get("script"))


def _zones_in_story(script: list[Mapping[str, Any]]) -> list[str]:
    present = {str(item.get("zone") or "UNKNOWN") for item in script}
    ordered = [zone for zone in ZONE_ORDER if zone in present]
    return ordered + sorted(present.difference(ordered))


def _select_reader_page(st: Any, *, page_count: int, zone: str) -> int:
    """Render pagination only when the reader has multiple pages."""
    if page_count <= 1:
        return 1
    return int(st.select_slider(
        "Trang",
        options=list(range(1, page_count + 1)),
        value=1,
        format_func=lambda value: f"{value}/{page_count}",
        key=f"story_reader_page_{zone}",
    ))


def _render_header(report: Mapping[str, Any]) -> None:
    import streamlit as st

    meta = _object(report.get("meta"))
    commitment = _object(meta.get("story_quality_commitment"))
    metrics = _object(commitment.get("recomputable_metrics"))
    title = escape(str(meta.get("title") or "Truyện chưa đặt tên"))
    series = escape(str(meta.get("series") or "—"))
    episode = escape(str(meta.get("episode") or "—"))
    author = escape(str(meta.get("author") or "—"))
    duration = float(metrics.get("estimated_duration_minutes") or 0)
    st.markdown(
        f"""
        <div class="story-heading">
          <div><div class="story-eyebrow">{series} · Tập {episode}</div><h2>{title}</h2>
          <div class="story-muted">{author} · {escape(str(meta.get('channel') or '—'))}</div></div>
          <div class="story-duration">{duration:.1f} phút</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_reader(
    report: Mapping[str, Any], *, image_catalog: Mapping[str, Mapping[str, Path]] | None = None,
    image_aspect: str = "landscape",
) -> None:
    import streamlit as st

    script = _script_items(report)
    if not script:
        st.info("Truyện chưa có nội dung kịch bản.")
        return
    zones = _zones_in_story(script)
    zone = st.segmented_control(
        "Vùng truyện",
        zones,
        default=zones[0],
        format_func=lambda value: ZONE_LABELS.get(value, value.replace("_", " ").title()),
        key="story_reader_zone",
    ) or zones[0]
    indexed = [(index, item) for index, item in enumerate(script) if item.get("zone") == zone]
    page_size = 25
    page_count = max(1, (len(indexed) + page_size - 1) // page_size)
    page = _select_reader_page(st, page_count=page_count, zone=zone)
    start = (page - 1) * page_size
    visible = indexed[start:start + page_size]
    st.caption(
        f"{ZONE_LABELS.get(zone, zone)} · {len(indexed)} mục · "
        f"đang hiển thị {start + 1}–{min(start + page_size, len(indexed))}"
    )
    if image_catalog is not None:
        image = image_for_zone(image_catalog, image_aspect, zone)
        _left_space, image_column, _right_space = st.columns([1, 2, 1])
        with image_column:
            render_image_thumbnail(
                image, caption=f"{ZONE_LABELS.get(zone, zone)} · {image_aspect.title()}",
                key=f"story_reader_{image_aspect}_{zone}",
                frame_ratio=(16, 9),
            )

    for index, item in visible:
        voice = str(item.get("voice") or "NARRATOR")
        text = escape(str(item.get("text") or ""))
        environment = escape(str(item.get("environment") or "none").replace("_", " "))
        voice_label = VOICE_LABELS.get(voice, voice.replace("_", " ").title())
        line_class = "story-dialogue" if voice != "NARRATOR" else "story-narration"
        st.markdown(
            f"""
            <div class="story-line {line_class}">
              <div class="story-line-meta"><span>{index + 1}</span><strong>{voice_label}</strong></div>
              <div><div class="story-text">{text}</div>
              <div class="story-cue">{environment} · {escape(str(item.get('speed') or 'NORMAL').lower())}</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_outline(
    report: Mapping[str, Any], *, image_catalog: Mapping[str, Mapping[str, Path]] | None = None,
    image_aspect: str = "landscape",
) -> None:
    import streamlit as st

    outline = _object(report.get("outline"))
    if not outline:
        st.info("Truyện chưa có dàn ý.")
        return
    for key, label in OUTLINE_KEYS.items():
        if key in outline:
            text_col, image_col = st.columns([2, 1]) if image_catalog is not None else (st.container(), st.container())
            with text_col:
                st.markdown(f"**{label}**")
                st.write(str(outline[key]))
            if image_catalog is not None:
                with image_col:
                    zone = key.upper()
                    render_image_thumbnail(
                        image_for_zone(image_catalog, image_aspect, zone),
                        caption=f"{label} · {image_aspect.title()}",
                        key=f"story_outline_{image_aspect}_{key}",
                        frame_ratio=(16, 9),
                    )
            st.divider()


def _render_characters(report: Mapping[str, Any], *, images_root: Path | None = None) -> None:
    import streamlit as st

    characters = _items(report.get("characters"))
    if not characters:
        st.info("Truyện chưa có hồ sơ nhân vật.")
        return
    names = {str(item.get("character_id")): str(item.get("name") or item.get("character_id")) for item in characters}
    selected_id = st.selectbox(
        "Chọn nhân vật",
        list(names),
        format_func=lambda item_id: names[item_id],
        key="story_character",
    )
    selected = next(item for item in characters if str(item.get("character_id")) == selected_id)
    cols = st.columns([1.45, 1, 1, 1.3])
    role = escape(str(selected.get("role") or "—"))
    cols[0].markdown(
        f"""
        <div class="story-role-metric">
          <div class="story-role-label">Vai trò</div>
          <div class="story-role-value">{role}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if images_root is not None:
        asset = _object(selected.get("reference_asset"))
        relative = str(asset.get("reference_image") or "")
        path = project_asset_path(images_root, relative) if relative else None
        _space, preview, _space_right = st.columns([1, 2, 1])
        with preview:
            render_image_thumbnail(path, caption=str(selected.get("name") or selected_id), key="character_reference")
        if path is not None and path.is_file():
            try:
                digest, dimensions = file_facts(path)
                st.caption(f"{relative} · {dimensions} · " + ("SHA-256 khớp hồ sơ" if digest == asset.get("file_sha256") else "SHA-256 chưa khớp hoặc chưa có giá trị đối chiếu"))
            except (OSError, ValueError):
                st.warning("Không đọc được ảnh tham chiếu.")
    age_min = selected.get("canonical_age_min")
    age_max = selected.get("canonical_age_max")
    age = age_min if age_min == age_max else f"{age_min}–{age_max}"
    cols[1].metric("Tuổi canon", age if age_min is not None else "—")
    cols[2].metric("Tầm quan trọng", str(selected.get("visual_story_importance", "—")).title())
    cols[3].metric("Visual eligibility", str(selected.get("adult_visual_eligibility", "—")).replace("_", " ").title())
    traits = selected.get("identity_traits") if isinstance(selected.get("identity_traits"), list) else []
    if traits:
        st.subheader("Dấu hiệu nhận diện")
        st.markdown("\n".join(f"- {trait}" for trait in traits))

    st.subheader("Danh sách nhân vật")
    st.dataframe(
        [{
            "Tên": item.get("name", "—"),
            "Vai trò": item.get("role", "—"),
            "Tuổi": item.get("canonical_age_min", "—"),
            "Tầm quan trọng": str(item.get("visual_story_importance", "—")).title(),
        } for item in characters],
        hide_index=True,
        use_container_width=True,
    )


def _counter_rows(counter: Counter[str], total: int, label: str) -> list[dict[str, Any]]:
    return [
        {label: key.replace("_", " ").title(), "Số mục": count, "Tỷ lệ": f"{count / total:.1%}"}
        for key, count in counter.most_common()
    ]


def _render_statistics(report: Mapping[str, Any]) -> None:
    import streamlit as st

    meta = _object(report.get("meta"))
    commitment = _object(meta.get("story_quality_commitment"))
    metrics = _object(commitment.get("recomputable_metrics"))
    quality = _object(commitment.get("committed_quality_metrics"))
    script = _script_items(report)
    total = len(script) or 1
    cols = st.columns(6)
    cols[0].metric("Tổng số từ", f"{int(metrics.get('total_words') or 0):,}")
    cols[1].metric("Mục kịch bản", len(script))
    cols[2].metric("Nhân vật", len(_items(report.get("characters"))))
    cols[3].metric("Hội thoại", int(metrics.get("direct_dialogue_item_count") or 0))
    cols[4].metric("Tỷ lệ hội thoại", f"{float(metrics.get('direct_dialogue_ratio') or 0):.1%}")
    cols[5].metric("Chất lượng", display_score(quality.get("final_story_quality_score")))

    voice_counts = Counter(str(item.get("voice") or "UNKNOWN") for item in script)
    environment_counts = Counter(str(item.get("environment") or "none") for item in script)
    zone_counts = Counter(str(item.get("zone") or "UNKNOWN") for item in script)
    voice_tab, environment_tab, zone_tab = st.tabs(["Giọng đọc", "Môi trường", "Vùng truyện"])
    with voice_tab:
        st.dataframe(
            [{"Giọng": VOICE_LABELS.get(key, key.title()), "Số mục": count, "Tỷ lệ": f"{count / total:.1%}"}
             for key, count in voice_counts.most_common()],
            hide_index=True,
            use_container_width=True,
        )
    with environment_tab:
        st.dataframe(_counter_rows(environment_counts, total, "Môi trường"), hide_index=True, use_container_width=True)
    with zone_tab:
        st.dataframe(
            [{"Vùng": ZONE_LABELS.get(key, key.title()), "Số mục": count, "Tỷ lệ": f"{count / total:.1%}"}
             for key, count in zone_counts.most_common()],
            hide_index=True,
            use_container_width=True,
        )


def _render_technical(report: Mapping[str, Any]) -> None:
    import streamlit as st

    meta = _object(report.get("meta"))
    commitment = _object(meta.get("story_quality_commitment"))
    quality = _object(commitment.get("committed_quality_metrics"))
    rows = [
        {"Thuộc tính": "Schema", "Giá trị": report.get("schema_version", "—")},
        {"Thuộc tính": "Ngôn ngữ", "Giá trị": meta.get("language", "—")},
        {"Thuộc tính": "Thể loại", "Giá trị": meta.get("genre", "—")},
        {"Thuộc tính": "Thời lượng mục tiêu", "Giá trị": f"{meta.get('length_min', '—')}–{meta.get('length_max', '—')} phút"},
        {"Thuộc tính": "Chất lượng", "Giá trị": quality.get("final_story_quality_score", "—")},
        {"Thuộc tính": "Tiến triển", "Giá trị": quality.get("progression_score", "—")},
        {"Thuộc tính": "Cuốn hút", "Giá trị": quality.get("engagement_score", "—")},
        {"Thuộc tính": "Final script digest", "Giá trị": _short_digest(commitment.get("final_script_text_digest_sha256"))},
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)
    with st.expander("Xem JSON gốc"):
        st.json(report, expanded=False)


def render_story_report(
    report: Mapping[str, Any], *, include_technical: bool = True,
    images_root: Path | None = None,
) -> None:
    import streamlit as st

    _validate_story(report)
    _render_header(report)
    evidence = st.session_state.get("story_evidence_range")
    if evidence:
        start, end = evidence
        script = _script_items(report)
        st.subheader("Đoạn kịch bản từ bằng chứng kiểm định")
        if 0 <= start <= end < len(script):
            st.caption(f"Chỉ số JSON {start}–{end} · mục hiển thị {start + 1}–{end + 1}")
            with st.container(height=360):
                for index in range(start, end + 1):
                    st.write(f"{index + 1}. {script[index].get('text', '')}")
        else:
            st.warning("Vị trí bằng chứng nằm ngoài kịch bản hiện tại; kiểm tra lại nguồn báo cáo.")
        if st.button("Đóng đoạn bằng chứng"):
            st.session_state.pop("story_evidence_range", None)
            st.rerun()
    image_catalog = discover_story_images(images_root) if images_root is not None else None
    image_aspect = "landscape"
    if image_catalog is not None:
        available = [aspect for aspect in ASPECTS if image_catalog.get(aspect)] or list(ASPECTS)
        image_aspect = st.segmented_control(
            "Tỷ lệ hình ảnh", available, default=available[0],
            format_func=str.title, key="story_content_image_aspect",
        ) or available[0]
    labels = ["Đọc truyện", "Dàn ý", "Nhân vật", "Lặp câu", "Thống kê"]
    if include_technical:
        labels.append("Kỹ thuật")
    tabs = st.tabs(labels)
    reader, outline, characters, repetition, statistics = tabs[:5]
    with reader:
        _render_reader(report, image_catalog=image_catalog, image_aspect=image_aspect)
    with outline:
        _render_outline(report, image_catalog=image_catalog, image_aspect=image_aspect)
    with characters:
        _render_characters(report, images_root=images_root)
    with repetition:
        render_repetition_report(report, image_catalog=image_catalog, image_aspect=image_aspect)
    with statistics:
        _render_statistics(report)
    if include_technical:
        with tabs[5]:
            _render_technical(report)


def render_story_workspace(*, embedded: bool = False) -> None:
    import streamlit as st

    if not embedded:
        st.set_page_config(page_title="Story", page_icon=":material/menu_book:", layout="wide")
    st.header("Story")
    st.caption("Đọc story.json theo vùng truyện và tra cứu nhanh dàn ý, nhân vật, giọng đọc, môi trường.")
    st.html(
        """<style>
        .story-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;padding:1.1rem 1.2rem;border:1px solid color-mix(in srgb,currentColor 14%,transparent);border-radius:.8rem;margin:.25rem 0 1rem}
        .story-heading h2{margin:.1rem 0 .2rem;font-size:1.55rem}.story-eyebrow{font-size:.75rem;opacity:.65;text-transform:uppercase;letter-spacing:.08em}.story-muted,.story-cue{font-size:.8rem;opacity:.68}.story-duration{white-space:nowrap;padding:.45rem .7rem;border-radius:999px;font-weight:600;color:#725024;background:rgba(180,130,60,.14)}
        .story-line{display:grid;grid-template-columns:7rem 1fr;gap:.8rem;padding:.7rem .2rem;border-bottom:1px solid color-mix(in srgb,currentColor 10%,transparent)}.story-line-meta{display:flex;gap:.5rem;align-items:flex-start;font-size:.75rem;opacity:.68}.story-line-meta strong{font-weight:600}.story-text{white-space:pre-wrap}.story-dialogue .story-text{padding:.65rem .8rem;border-radius:.65rem;background:rgba(180,130,60,.12)}.story-cue{margin-top:.3rem}
        .story-role-metric{padding:.25rem 0}.story-role-label{font-size:.875rem;line-height:1.25;opacity:.72;margin-bottom:.35rem}.story-role-value{font-size:clamp(1.65rem,2.2vw,2.35rem);line-height:1.15;white-space:normal;overflow-wrap:anywhere;word-break:normal}
        @media(max-width:640px){.story-heading{flex-direction:column}.story-line{grid-template-columns:1fr;gap:.25rem}}
        </style>"""
    )
    uploaded = st.file_uploader("Chọn story.json", type=["json"], key="story_upload")
    path_text = st.text_input(
        "Hoặc nhập đường dẫn tệp trên máy",
        placeholder=r"D:\project\output\story.json",
        key="story_path",
    )
    source: Path | BinaryIO | None = uploaded if uploaded is not None else (Path(path_text.strip()) if path_text.strip() else None)
    if source is None:
        st.info("Chọn một tệp JSON hoặc nhập đường dẫn để đọc truyện.")
        return
    try:
        report = _read_report(source)
        _validate_story(report)
    except (OSError, ValueError) as exc:
        st.error(str(exc))
        return
    images_root = source.parent if isinstance(source, Path) else None
    render_story_report(report, images_root=images_root)


__all__ = ["render_story_report", "render_story_workspace"]
