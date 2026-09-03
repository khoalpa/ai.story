"""Friendly readers and Streamlit views for audio-to-video delivery artifacts."""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Mapping, Sequence

from studio.package_quality_report import _items, _object, _read_report

PRODUCTION_FILES = {
    "handoff": "audio_video_handoff.json",
    "audio_quality": "story.audio_quality.json",
    "subtitle": "story.srt",
}

_TIMESTAMP = re.compile(
    r"^(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2}),(?P<ms>\d{3})$"
)


@dataclass(frozen=True)
class SubtitleCue:
    index: int
    start_ms: int
    end_ms: int
    text: str

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


def _timestamp_ms(value: str) -> int:
    match = _TIMESTAMP.match(value.strip())
    if not match:
        raise ValueError(f"timestamp SRT không hợp lệ: {value!r}")
    parts = {key: int(number) for key, number in match.groupdict().items()}
    if parts["m"] > 59 or parts["s"] > 59:
        raise ValueError(f"timestamp SRT không hợp lệ: {value!r}")
    return (((parts["h"] * 60 + parts["m"]) * 60 + parts["s"]) * 1000 + parts["ms"])


def format_timestamp(milliseconds: int) -> str:
    total_seconds, ms = divmod(max(0, int(milliseconds)), 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"


def format_duration(seconds: float | int | None) -> str:
    issues: list[str] = []
    duration = _report_duration(seconds, "duration", issues)
    if issues:
        return "—"
    total = round(duration)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _report_duration(value: Any, field: str, issues: list[str]) -> float:
    """Keep malformed measurements visible without breaking the report view."""
    if value is None:
        return 0.0
    try:
        if isinstance(value, bool):
            raise ValueError
        duration = float(value)
        if not math.isfinite(duration) or duration < 0:
            raise ValueError
        return duration
    except (TypeError, ValueError, OverflowError):
        issues.append(f"Thời lượng {field} không hợp lệ.")
        return 0.0


def format_bytes(value: Any) -> str:
    try:
        size = max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return "—"
    units = ("B", "KB", "MB", "GB")
    amount = float(size)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return "—"


def _artifact_size_matches(path: Path | None, expected: Any) -> bool:
    """Malformed size declarations must not crash or pass delivery checks."""
    if path is None:
        return False
    try:
        if not path.is_file():
            return False
        if expected is None or expected == "":
            return True
        if isinstance(expected, bool) or not isinstance(expected, (int, str)):
            return False
        size = int(expected)
        return size >= 0 and path.stat().st_size == size
    except (OSError, ValueError):
        return False


def parse_srt(text: str) -> list[SubtitleCue]:
    """Parse standard SRT while retaining useful validation errors."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    cues: list[SubtitleCue] = []
    for position, block in enumerate(re.split(r"\n{2,}", normalized), start=1):
        lines = [line.rstrip() for line in block.splitlines()]
        if len(lines) < 3:
            raise ValueError(f"khối phụ đề {position} không đầy đủ")
        try:
            index = int(lines[0].lstrip("\ufeff").strip())
        except ValueError as exc:
            raise ValueError(f"số thứ tự phụ đề không hợp lệ tại khối {position}") from exc
        if " --> " not in lines[1]:
            raise ValueError(f"mốc thời gian bị thiếu tại phụ đề {index}")
        start_text, end_text = lines[1].split(" --> ", 1)
        start_ms, end_ms = _timestamp_ms(start_text), _timestamp_ms(end_text.split()[0])
        if end_ms <= start_ms:
            raise ValueError(f"thời lượng không hợp lệ tại phụ đề {index}")
        cues.append(SubtitleCue(index, start_ms, end_ms, "\n".join(lines[2:]).strip()))
    return cues


def _validate_handoff(report: Mapping[str, Any]) -> None:
    if report.get("kind") != "audio.video-handoff":
        raise ValueError("kind phải là audio.video-handoff")
    artifacts = _object(report.get("artifacts"))
    for key in ("audio", "subtitle", "quality_report"):
        artifact = _object(artifacts.get(key))
        if not artifact.get("path"):
            raise ValueError(f"thiếu artifacts.{key}.path")


def _validate_audio_quality(report: Mapping[str, Any]) -> None:
    for key in ("target", "measured", "duration", "stream", "checks"):
        if not isinstance(report.get(key), Mapping):
            raise ValueError(f"thiếu hoặc sai kiểu trường {key}")
    if not isinstance(report.get("passed"), bool):
        raise ValueError("trường passed phải là boolean")


def load_audio_delivery(directory: Path) -> tuple[dict[str, Any], dict[str, str]]:
    data: dict[str, Any] = {}
    statuses: dict[str, str] = {}
    if not directory.is_dir():
        return data, {key: "Không tìm thấy thư mục" for key in PRODUCTION_FILES}
    for key, filename in PRODUCTION_FILES.items():
        path = directory / filename
        if not path.is_file():
            statuses[key] = "Thiếu"
            continue
        try:
            value: dict[str, Any] | list[SubtitleCue]
            if key == "subtitle":
                value = parse_srt(path.read_text(encoding="utf-8-sig"))
            else:
                value = _read_report(path)
                (_validate_handoff if key == "handoff" else _validate_audio_quality)(value)
        except (OSError, UnicodeError, ValueError) as exc:
            statuses[key] = f"Không hợp lệ: {exc}"
            continue
        data[key] = value
        statuses[key] = "Có dữ liệu"
    return data, statuses


def read_audio_delivery_override(source: BinaryIO, key: str) -> Any:
    """Read and validate one user-uploaded production artifact."""
    if key not in PRODUCTION_FILES:
        raise ValueError(f"loại tệp sản xuất không được hỗ trợ: {key}")
    if key == "subtitle":
        raw = source.read()
        text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else str(raw)
        return parse_srt(text)
    report = _read_report(source)
    (_validate_handoff if key == "handoff" else _validate_audio_quality)(report)
    return report


def inspect_audio_delivery(data: Mapping[str, Any], directory: Path) -> dict[str, Any]:
    handoff = _object(data.get("handoff"))
    quality = _object(data.get("audio_quality"))
    subtitle = data.get("subtitle")
    cues: list[SubtitleCue] = subtitle if isinstance(subtitle, list) else []
    artifacts = _object(handoff.get("artifacts"))
    checks = _object(quality.get("checks"))
    issues: list[str] = []
    artifact_rows: list[dict[str, Any]] = []
    for key, label in (("audio", "Audio"), ("subtitle", "Phụ đề"), ("quality_report", "Báo cáo chất lượng")):
        artifact = _object(artifacts.get(key))
        relative = str(artifact.get("path") or "")
        path = directory / relative if relative else None
        exists = bool(path and path.is_file())
        expected_size = artifact.get("size_bytes")
        size_matches = _artifact_size_matches(path, expected_size)
        if artifact and not exists:
            issues.append(f"Không tìm thấy {label.lower()} `{relative}`.")
        elif exists and not size_matches:
            issues.append(f"Kích thước {label.lower()} không khớp handoff.")
        artifact_rows.append({
            "key": key,
            "label": label,
            "path": path,
            "filename": relative or "—",
            "media_type": artifact.get("media_type", "—"),
            "size": format_bytes(expected_size),
            "sha256": str(artifact.get("sha256") or ""),
            "exists": exists,
            "size_matches": size_matches,
        })
    measurements = _items(_object(quality.get("segments")).get("measurements"))
    measured_count = int(_object(quality.get("segments")).get("measured_count") or len(measurements))
    if cues and measured_count and len(cues) != measured_count:
        issues.append(f"Phụ đề có {len(cues)} câu nhưng audio có {measured_count} segment.")
    overlaps = sum(current.start_ms < previous.end_ms for previous, current in zip(cues, cues[1:]))
    if overlaps:
        issues.append(f"Có {overlaps} mốc phụ đề chồng lấn.")
    duration_seconds = _report_duration(_object(quality.get("duration")).get("output_seconds"), "duration.output_seconds", issues)
    subtitle_seconds = cues[-1].end_ms / 1000 if cues else 0
    if duration_seconds and subtitle_seconds > duration_seconds + 1:
        issues.append("Phụ đề kết thúc sau audio.")
    checks_passed = sum(value is True for value in checks.values())
    checks_total = len(checks)
    if checks_passed != checks_total:
        issues.append(f"{checks_total - checks_passed} phép kiểm tra chất lượng chưa đạt.")
    elif quality and not checks:
        issues.append("Chưa có dữ liệu kiểm tra chất lượng.")
    passed = quality.get("passed") is True and bool(checks) and checks_passed == checks_total
    ready = bool(handoff and quality and cues and passed and not issues and all(row["exists"] and row["size_matches"] for row in artifact_rows))
    return {
        "ready": ready,
        "passed": passed,
        "cue_count": len(cues),
        "segment_count": measured_count,
        "duration_seconds": duration_seconds or subtitle_seconds,
        "subtitle_seconds": subtitle_seconds,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "issues": issues,
        "artifacts": artifact_rows,
        "measurements": measurements,
        "handoff_created_at": handoff.get("created_at"),
    }


def verify_artifact_hashes(rows: Sequence[Mapping[str, Any]]) -> dict[str, bool]:
    results: dict[str, bool] = {}
    for row in rows:
        path, expected = row.get("path"), str(row.get("sha256") or "")
        if not isinstance(path, Path) or not path.is_file() or not expected:
            results[str(row.get("key"))] = False
            continue
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        results[str(row.get("key"))] = digest.hexdigest().lower() == expected.lower()
    return results


def _loudness_range_status(measured: Any, target: Any) -> str:
    try:
        if isinstance(measured, bool) or isinstance(target, bool):
            return "Chưa xác minh"
        actual, limit = float(measured), float(target)
        if not math.isfinite(actual) or not math.isfinite(limit) or min(actual, limit) < 0:
            return "Chưa xác minh"
        return "Đạt" if actual <= limit else "Không đạt"
    except (TypeError, ValueError, OverflowError):
        return "Chưa xác minh"


def _quality_rows(quality: Mapping[str, Any]) -> list[dict[str, Any]]:
    target, measured, stream = (_object(quality.get(key)) for key in ("target", "measured", "stream"))
    checks = _object(quality.get("checks"))
    return [
        {"Chỉ số": "Integrated loudness", "Đo được": f"{measured.get('integrated_lufs', '—')} LUFS", "Mục tiêu": f"{target.get('integrated_lufs', '—')} LUFS", "Kết quả": "Đạt" if checks.get("integrated_loudness") else "Không đạt"},
        {"Chỉ số": "True peak", "Đo được": f"{measured.get('true_peak_dbtp', '—')} dBTP", "Mục tiêu": f"≤ {target.get('true_peak_dbtp', '—')} dBTP", "Kết quả": "Đạt" if checks.get("true_peak") else "Không đạt"},
        {"Chỉ số": "Loudness range", "Đo được": f"{measured.get('loudness_range_lu', '—')} LU", "Mục tiêu": f"≤ {target.get('loudness_range_lu', '—')} LU", "Kết quả": _loudness_range_status(measured.get("loudness_range_lu"), target.get("loudness_range_lu"))},
        {"Chỉ số": "Sample rate", "Đo được": f"{stream.get('sample_rate', '—')} Hz", "Mục tiêu": "48,000 Hz", "Kết quả": "Đạt" if checks.get("sample_rate") else "Không đạt"},
        {"Chỉ số": "Kênh", "Đo được": str(stream.get("channel_layout") or stream.get("channels") or "—"), "Mục tiêu": "Stereo", "Kết quả": "Đạt" if checks.get("channels") else "Không đạt"},
    ]


def _delivery_result_text(quality: Mapping[str, Any], passed: bool) -> str:
    if not quality:
        return "Chưa kiểm định"
    return "Đạt" if passed else "Không đạt"


def render_audio_delivery(data: Mapping[str, Any], directory: Path) -> None:
    import streamlit as st

    quality = _object(data.get("audio_quality"))
    subtitle = data.get("subtitle")
    cues: list[SubtitleCue] = subtitle if isinstance(subtitle, list) else []
    summary = inspect_audio_delivery(data, directory)
    tab_overview, tab_quality, tab_subtitles, tab_handoff = st.tabs(
        ["Tổng quan", "Chất lượng Audio", "Phụ đề", "Bàn giao Video"]
    )
    with tab_overview:
        if summary["ready"]:
            st.success("**Sẵn sàng chuyển sang Video Studio** · Audio đạt chất lượng, phụ đề hợp lệ và tài nguyên bàn giao đầy đủ.")
        elif summary["issues"]:
            st.warning("**Cần kiểm tra trước khi bàn giao** · " + " ".join(summary["issues"]))
        else:
            st.info("Chưa đủ dữ liệu để kết luận trạng thái bàn giao.")
        cols = st.columns(6)
        stream, duration = _object(quality.get("stream")), _object(quality.get("duration"))
        result_text = _delivery_result_text(quality, summary["passed"])
        values = [
            ("Kết quả", result_text),
            ("Thời lượng", format_duration(summary["duration_seconds"])),
            ("Profile", quality.get("profile", "—")),
            ("Codec", stream.get("codec_name", "—")),
            ("Sample rate", f"{stream.get('sample_rate', '—')} Hz"),
            ("Phụ đề", f"{summary['cue_count']:,} câu"),
        ]
        for column, (label, value) in zip(cols, values):
            column.metric(label, value)
        audio_path = next((row["path"] for row in summary["artifacts"] if row["key"] == "audio" and row["exists"]), None)
        if audio_path:
            st.audio(str(audio_path))
        st.caption(f"Nguồn {duration.get('source_seconds', '—')} giây · Đầu ra {duration.get('output_seconds', '—')} giây")

    with tab_quality:
        if not quality:
            st.info(f"Chưa có `{PRODUCTION_FILES['audio_quality']}`.")
        else:
            st.dataframe(_quality_rows(quality), width="stretch", hide_index=True)
            measurements = summary["measurements"]
            if measurements:
                chart_rows = [{"Segment": index + 1, "LUFS": item.get("integrated_lufs")} for index, item in enumerate(measurements)]
                st.subheader("Loudness theo segment")
                st.line_chart(chart_rows, x="Segment", y="LUFS")
                median = _object(quality.get("segments")).get("median_lufs")
                st.caption(f"{len(measurements):,} segment · Median {median if median is not None else '—'} LUFS")
            failed = [name.replace("_", " ") for name, passed in _object(quality.get("checks")).items() if not passed]
            if failed:
                st.error("Kiểm tra chưa đạt: " + ", ".join(failed))
            else:
                st.success(f"Đạt {summary['checks_passed']}/{summary['checks_total']} phép kiểm tra.")

    with tab_subtitles:
        if not cues:
            st.info(f"Chưa có `{PRODUCTION_FILES['subtitle']}` hợp lệ.")
        else:
            query = st.text_input("Tìm trong phụ đề", placeholder="Nhập từ hoặc cụm từ…", key="story_audio_subtitle_search")
            filtered = [cue for cue in cues if query.casefold() in cue.text.casefold()]
            page_size = st.selectbox("Số câu mỗi trang", [25, 50, 100], index=0, key="story_audio_subtitle_page_size")
            page_count = max(1, (len(filtered) + page_size - 1) // page_size)
            page = st.number_input("Trang", min_value=1, max_value=page_count, value=1, step=1, key="story_audio_subtitle_page")
            start = (int(page) - 1) * page_size
            rows = [{"#": cue.index, "Bắt đầu": format_timestamp(cue.start_ms), "Kết thúc": format_timestamp(cue.end_ms), "Thời lượng": f"{cue.duration_ms / 1000:.1f}s", "Nội dung": cue.text} for cue in filtered[start:start + page_size]]
            st.caption(f"Hiển thị {start + 1 if filtered else 0}–{min(start + page_size, len(filtered))} trong {len(filtered):,} câu")
            st.dataframe(rows, width="stretch", hide_index=True)

    with tab_handoff:
        if not _object(data.get("handoff")):
            st.info(f"Chưa có `{PRODUCTION_FILES['handoff']}`.")
        else:
            created = summary.get("handoff_created_at")
            if created:
                try:
                    created = datetime.fromisoformat(str(created)).astimezone().strftime("%d/%m/%Y %H:%M")
                except ValueError:
                    pass
                st.caption(f"Tạo lúc {created}")
            rows = [{"Tài nguyên": row["label"], "Tệp": row["filename"], "Loại": row["media_type"], "Kích thước": row["size"], "Trạng thái": "Hợp lệ" if row["exists"] and row["size_matches"] else "Cần kiểm tra", "SHA-256": (row["sha256"][:12] + "…") if row["sha256"] else "—"} for row in summary["artifacts"]]
            st.dataframe(rows, width="stretch", hide_index=True)
            if st.button("Xác minh checksum SHA-256", key="verify_story_audio_hashes"):
                with st.spinner("Đang đọc và xác minh các tệp…"):
                    results = verify_artifact_hashes(summary["artifacts"])
                if results and all(results.values()):
                    st.success("Checksum của toàn bộ tài nguyên khớp handoff.")
                else:
                    failed = [key for key, passed in results.items() if not passed]
                    st.error("Checksum không khớp hoặc không thể đọc: " + ", ".join(failed))


__all__ = [
    "PRODUCTION_FILES", "SubtitleCue", "format_bytes", "format_duration",
    "format_timestamp", "inspect_audio_delivery", "load_audio_delivery",
    "parse_srt", "read_audio_delivery_override", "render_audio_delivery",
    "verify_artifact_hashes",
]
