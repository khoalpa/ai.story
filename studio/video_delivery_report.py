"""Discovery, validation, summaries, and friendly views for rendered videos."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Mapping

from studio.audio_delivery_report import format_bytes, format_duration
from studio.package_quality_report import _items, _object, _read_report
from studio.story_images import discover_story_images, render_image_thumbnail

RESULT_SUFFIX = ".result.json"
QUALITY_SUFFIX = ".video_quality.json"
DEFAULT_VIDEO_REPORTS = (
    "video_landscape.result.json",
    "video_landscape.video_quality.json",
    "video_portrait.result.json",
    "video_portrait.video_quality.json",
)

VIDEO_PREVIEW_STYLE = """
<style>
.st-key-story_video_preview video[data-testid="stVideo"] {
    width: 100%;
    aspect-ratio: 16 / 9;
    object-fit: contain;
    background: #000;
}
</style>
"""


def video_report_identity(filename: str) -> tuple[str, str]:
    if filename.endswith(QUALITY_SUFFIX):
        return filename[: -len(QUALITY_SUFFIX)], "quality"
    if filename.endswith(RESULT_SUFFIX):
        return filename[: -len(RESULT_SUFFIX)], "result"
    raise ValueError("tên tệp phải kết thúc bằng .result.json hoặc .video_quality.json")


def discover_video_report_names(directory: Path) -> tuple[str, ...]:
    names = set(DEFAULT_VIDEO_REPORTS)
    if directory.is_dir():
        names.update(path.name for path in directory.glob(f"*{RESULT_SUFFIX}") if path.is_file())
        names.update(path.name for path in directory.glob(f"*{QUALITY_SUFFIX}") if path.is_file())
    return tuple(sorted(names, key=lambda name: (video_report_identity(name)[0], name.endswith(RESULT_SUFFIX))))


def _validate_result(report: Mapping[str, Any]) -> None:
    if report.get("kind") != "video.result-manifest":
        raise ValueError("kind phải là video.result-manifest")
    artifacts = _object(report.get("artifacts"))
    if not _object(artifacts.get("video")).get("path"):
        raise ValueError("thiếu artifacts.video.path")


def _validate_quality(report: Mapping[str, Any]) -> None:
    for key in ("measured", "duration", "video_stream", "audio_stream", "checks"):
        if not isinstance(report.get(key), Mapping):
            raise ValueError(f"thiếu hoặc sai kiểu trường {key}")
    if not isinstance(report.get("passed"), bool):
        raise ValueError("trường passed phải là boolean")


def read_video_report(source: BinaryIO | Path, kind: str) -> dict[str, Any]:
    report = _read_report(source)
    (_validate_result if kind == "result" else _validate_quality)(report)
    return report


def load_video_deliveries(directory: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    variants: dict[str, dict[str, Any]] = {}
    statuses: dict[str, str] = {}
    for filename in discover_video_report_names(directory):
        variant, kind = video_report_identity(filename)
        path = directory / filename
        if not path.is_file():
            statuses[filename] = "Thiếu"
            continue
        try:
            variants.setdefault(variant, {})[kind] = read_video_report(path, kind)
        except (OSError, ValueError) as exc:
            statuses[filename] = f"Không hợp lệ: {exc}"
            continue
        statuses[filename] = "Có dữ liệu"
    return variants, statuses


def apply_video_report_override(
    variants: dict[str, dict[str, Any]], source: BinaryIO, filename: str
) -> tuple[str, str]:
    variant, kind = video_report_identity(filename)
    variants.setdefault(variant, {})[kind] = read_video_report(source, kind)
    return variant, kind


def inspect_video_variant(
    variant: str, reports: Mapping[str, Any], directory: Path
) -> dict[str, Any]:
    result, quality = _object(reports.get("result")), _object(reports.get("quality"))
    artifacts = _object(result.get("artifacts"))
    video_artifact = _object(artifacts.get("video"))
    video_name = str(video_artifact.get("path") or "")
    video_path = directory / video_name if video_name else None
    video_exists = bool(video_path and video_path.is_file())
    expected_size = video_artifact.get("size_bytes")
    size_ok = bool(video_exists and (expected_size in {None, ""} or video_path.stat().st_size == int(expected_size)))
    checks = _object(quality.get("checks"))
    failed_checks = [name for name, passed in checks.items() if passed is not True]
    stream, audio, duration = (_object(quality.get(key)) for key in ("video_stream", "audio_stream", "duration"))
    subtitle = _object(quality.get("subtitle"))
    metadata = _object(result.get("metadata"))
    issues: list[str] = []
    if result and not video_exists:
        issues.append(f"Không tìm thấy video `{video_name}`.")
    elif video_exists and not size_ok:
        issues.append("Kích thước video không khớp result manifest.")
    if failed_checks:
        issues.append(f"{len(failed_checks)} phép kiểm tra chất lượng chưa đạt.")
    if not result:
        issues.append(f"Thiếu `{variant}{RESULT_SUFFIX}`.")
    if not quality:
        issues.append(f"Thiếu `{variant}{QUALITY_SUFFIX}`.")
    passed = quality.get("passed") is True
    return {
        "variant": variant,
        "label": variant.replace("video_", "").replace("_", " ").title(),
        "ready": bool(result and quality and passed and video_exists and size_ok),
        "passed": passed,
        "video_path": video_path if video_exists else None,
        "video_name": video_name or "—",
        "size": format_bytes(expected_size),
        "resolution": metadata.get("resolution") or (f"{stream.get('width')}×{stream.get('height')}" if stream else "—"),
        "duration": float(metadata.get("duration_seconds") or duration.get("container_seconds") or 0),
        "fps": stream.get("avg_frame_rate", "—"),
        "video_codec": stream.get("codec_name", "—"),
        "audio_codec": audio.get("codec_name", "—"),
        "loudness": _object(quality.get("measured")).get("integrated_lufs", "—"),
        "subtitle_present": subtitle.get("present") is True,
        "subtitle_timing_ok": subtitle.get("timing_ok") is True,
        "long_lines": _items(subtitle.get("long_lines")),
        "checks": checks,
        "failed_checks": failed_checks,
        "visual_samples": _items(quality.get("visual_samples")),
        "black_segments": _items(quality.get("black_segments")),
        "decode_errors": str(quality.get("decode_errors") or ""),
        "issues": issues,
        "created_at": result.get("created_at"),
        "quality": quality,
        "result": result,
    }


def build_video_delivery_summary(
    variants: Mapping[str, Mapping[str, Any]], directory: Path
) -> list[dict[str, Any]]:
    return [inspect_video_variant(name, reports, directory) for name, reports in sorted(variants.items())]


def _check_label(name: str) -> str:
    labels = {
        "integrated_loudness": "Loudness tổng thể", "true_peak": "True peak",
        "av_duration_sync": "Đồng bộ Audio/Video", "resolution": "Độ phân giải",
        "square_pixels": "Pixel vuông", "frame_rate": "Tốc độ khung hình",
        "video_codec": "Codec video", "pixel_format": "Định dạng pixel",
        "bt709_color": "Không gian màu BT.709", "audio_codec": "Codec audio",
        "audio_sample_rate": "Sample rate audio", "audio_channels": "Kênh audio",
        "faststart": "Fast start", "non_negative_start": "Mốc bắt đầu",
        "decode": "Giải mã", "black_frames": "Khung hình đen",
        "subtitle_timing": "Thời gian phụ đề", "subtitle_line_length": "Độ dài dòng phụ đề",
        "visual_ssim": "Độ tương đồng hình ảnh",
    }
    return labels.get(name, name.replace("_", " ").title())


def render_video_deliveries(
    variants: Mapping[str, Mapping[str, Any]], directory: Path
) -> None:
    import streamlit as st

    summaries = build_video_delivery_summary(variants, directory)
    if not summaries:
        st.info("Chưa phát hiện tệp kết quả hoặc báo cáo chất lượng video.")
        return
    options = [item["variant"] for item in summaries]
    selected = st.selectbox(
        "Phiên bản video", options,
        format_func=lambda value: next(item["label"] for item in summaries if item["variant"] == value),
        key="story_video_variant",
    )
    summary = next(item for item in summaries if item["variant"] == selected)
    tab_overview, tab_quality, tab_visual, tab_technical = st.tabs(
        ["Tổng quan", "Kiểm tra chất lượng", "Hình ảnh & phụ đề", "Tệp & kỹ thuật"]
    )
    with tab_overview:
        if summary["ready"]:
            st.success("**Sẵn sàng xuất bản** · Video và toàn bộ phép kiểm tra chất lượng đều đạt.")
        elif summary["issues"]:
            st.warning("**Cần kiểm tra** · " + " ".join(summary["issues"]))
        columns = st.columns(6)
        values = (
            ("Kết quả", "Đạt" if summary["passed"] else "Không đạt"),
            ("Độ phân giải", summary["resolution"]),
            ("Thời lượng", format_duration(summary["duration"])),
            ("FPS", summary["fps"]),
            ("Video codec", str(summary["video_codec"]).upper()),
            ("Dung lượng", summary["size"]),
        )
        for column, (label, value) in zip(columns, values):
            column.metric(label, value)
        if summary["video_path"]:
            st.html(VIDEO_PREVIEW_STYLE)
            with st.container(key="story_video_preview"):
                st.video(str(summary["video_path"]))
        created = summary["created_at"]
        if created:
            try:
                created = datetime.fromisoformat(str(created)).astimezone().strftime("%d/%m/%Y %H:%M")
            except ValueError:
                pass
            st.caption(f"Tạo lúc {created} · {summary['video_name']}")

    with tab_quality:
        checks = summary["checks"]
        if not checks:
            st.info("Chưa có dữ liệu kiểm tra chất lượng.")
        else:
            passed_count = sum(value is True for value in checks.values())
            st.metric("Phép kiểm tra đạt", f"{passed_count}/{len(checks)}")
            st.dataframe(
                [{"Kiểm tra": _check_label(name), "Kết quả": "Đạt" if passed else "Không đạt"} for name, passed in checks.items()],
                width="stretch", hide_index=True,
            )
            quality = summary["quality"]
            measured, duration = _object(quality.get("measured")), _object(quality.get("duration"))
            st.caption(
                f"Loudness {measured.get('integrated_lufs', '—')} LUFS · True peak {measured.get('true_peak_dbtp', '—')} dBTP · "
                f"Sai lệch Audio/Video {duration.get('delta_seconds', '—')} giây"
            )

    with tab_visual:
        subtitle_col, visual_col = st.columns(2)
        with subtitle_col:
            st.subheader("Phụ đề")
            st.metric("Trạng thái", "Đạt" if summary["subtitle_present"] and summary["subtitle_timing_ok"] else "Cần kiểm tra")
            st.caption(f"{len(summary['long_lines']):,} dòng dài · " + ("Đúng thời gian" if summary["subtitle_timing_ok"] else "Sai thời gian"))
            if summary["long_lines"]:
                with st.expander("Xem các dòng dài"):
                    for line in summary["long_lines"]:
                        st.markdown(f"- {line}")
        with visual_col:
            st.subheader("Mẫu hình ảnh")
            samples = summary["visual_samples"]
            st.metric("Số mẫu", len(samples))
            if samples:
                st.caption("Gallery chi tiết được hiển thị bên dưới theo thứ tự timeline.")
        if summary["black_segments"]:
            st.error(f"Phát hiện {len(summary['black_segments'])} đoạn hình đen.")
        samples = summary["visual_samples"]
        if samples:
            aspect = "portrait" if "portrait" in selected.casefold() else "landscape"
            catalog = discover_story_images(directory)
            st.subheader(f"Gallery kiểm định · {aspect.title()}")
            ordered_samples = sorted(samples, key=lambda item: float(item.get("timestamp_seconds") or 0))
            for row_start in range(0, len(ordered_samples), 3):
                columns = st.columns(3)
                for column, item in zip(columns, ordered_samples[row_start:row_start + 3]):
                    reference = str(item.get("reference") or "")
                    stem = Path(reference).stem.casefold()
                    score = item.get("ssim")
                    score_text = f"{float(score):.3f}" if score is not None else "—"
                    with column:
                        render_image_thumbnail(
                            catalog.get(aspect, {}).get(stem),
                            caption=reference or "Ảnh tham chiếu",
                            key=f"video_sample_{selected}_{stem}",
                            detail=(
                                f"{format_duration(item.get('timestamp_seconds'))} · "
                                f"SSIM {score_text} · "
                                f"{'Đạt' if score is not None and float(score) >= 0.9 else 'Cần xem'}"
                            ),
                        )

    with tab_technical:
        st.dataframe(
            [
                {"Thành phần": "Video", "Tệp": summary["video_name"], "Trạng thái": "Có dữ liệu" if summary["video_path"] else "Thiếu", "Thông tin": summary["size"]},
                {"Thành phần": "Result manifest", "Tệp": f"{selected}{RESULT_SUFFIX}", "Trạng thái": "Có dữ liệu" if summary["result"] else "Thiếu", "Thông tin": "Manifest đầu ra"},
                {"Thành phần": "Quality report", "Tệp": f"{selected}{QUALITY_SUFFIX}", "Trạng thái": "Có dữ liệu" if summary["quality"] else "Thiếu", "Thông tin": f"{len(summary['checks'])} phép kiểm tra"},
            ], width="stretch", hide_index=True,
        )
        if summary["decode_errors"]:
            st.error(summary["decode_errors"])
        with st.expander("JSON kỹ thuật"):
            st.json({"result": summary["result"], "quality": summary["quality"]}, expanded=False)


__all__ = [
    "DEFAULT_VIDEO_REPORTS", "QUALITY_SUFFIX", "RESULT_SUFFIX", "VIDEO_PREVIEW_STYLE",
    "apply_video_report_override", "build_video_delivery_summary",
    "discover_video_report_names", "inspect_video_variant", "load_video_deliveries",
    "read_video_report", "render_video_deliveries", "video_report_identity",
]
