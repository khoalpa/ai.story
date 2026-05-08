from __future__ import annotations

import io
import json
import shutil
import zipfile
import time
from json import JSONDecodeError
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Optional

from audio.app_config import AppConfig
from audio.asset_profile_utils import normalize_profile_root
from audio.profile_config import ProfileConfig
from .config_bundle import GuiConfigBundle
from audio.audio_story_spec import (
    normalize_canonical_authoring_zones,
    render_plain_script,
    validate_canonical_authoring,
)
from audio.raw_to_plain_script import build_min_header, has_script_marker, normalize_raw_lines
from audio.render_audio_app import RenderAudioAppRequest, RenderAudioAppResult
from audio.validate_plain_script import detect_body_only_script
from audio.render_events import RenderEvent

from .constants import DEFAULT_DOWNLOAD_NAME, PHASE_LABELS, PHASE_ORDER
from audio.gui.progress_details import format_duration
from audio.gui.runtime_usage import render_runtime_usage_compact


def find_binary(name: str) -> str:
    resolved = shutil.which(name)
    return resolved or name


def list_asset_profiles(profile_root: str) -> list[str]:
    root = normalize_profile_root(profile_root)
    if not root.exists() or not root.is_dir():
        return []
    return sorted([p.name for p in root.iterdir() if p.is_dir() and (p / "manifest.json").is_file()])


def list_profile_bgm_files(profile_root: str, asset_profile: str) -> list[str]:
    if not asset_profile:
        return []
    bgm_dir = normalize_profile_root(profile_root) / asset_profile / "bgm"
    if not bgm_dir.exists() or not bgm_dir.is_dir():
        return []
    return sorted([p.name for p in bgm_dir.iterdir() if p.is_file() and p.suffix.lower() in {".mp3", ".wav", ".m4a"}])


def read_profile_manifest(profile_root: str, asset_profile: str) -> dict:
    if not asset_profile:
        return {}
    path = normalize_profile_root(profile_root) / asset_profile / "manifest.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError):
        return {}


def read_profile_bgm_config(profile_root: str, asset_profile: str) -> str:
    if not asset_profile:
        return ""
    path = normalize_profile_root(profile_root) / asset_profile / "bgm_config.json"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def convert_canonical_to_plain_text(canonical_text: str) -> str:
    try:
        data = json.loads(canonical_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Canonical JSON is invalid: {exc}") from exc

    data = normalize_canonical_authoring_zones(data)
    errors = validate_canonical_authoring(data)
    if errors:
        raise ValueError("Canonical authoring is invalid:\n- " + "\n- ".join(errors))
    return render_plain_script(data)


def convert_raw_to_plain_text(raw_text: str, title: str, default_voice: str, default_lang: str, include_header: bool) -> str:
    lines = raw_text.splitlines()
    normalized = normalize_raw_lines(lines, default_voice=default_voice, default_lang=default_lang)
    final_text = "\n".join(normalized)
    if include_header and not has_script_marker(lines):
        final_text = build_min_header(title) + final_text
    return final_text


def _normalize_payload_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path) or hasattr(value, "__fspath__"):
        return str(value)
    if is_dataclass(value):
        return _normalize_payload_value(asdict(value))
    if isinstance(value, dict):
        return {str(k): _normalize_payload_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_payload_value(v) for v in value]
    if hasattr(value, "__dict__"):
        return {str(k): _normalize_payload_value(v) for k, v in vars(value).items()}
    return str(value)


def normalize_payload(payload: dict) -> dict:
    return {str(key): _normalize_payload_value(value) for key, value in payload.items()}


class ProgressCollector:
    def __init__(self, status_slot, progress_slot, event_slot, log_slot) -> None:
        self.status_slot = status_slot
        self.progress_slot = progress_slot
        self.event_slot = event_slot
        self.log_slot = log_slot
        self.events: list[dict] = []
        self.completed: set[str] = set()
        self.current_phase: Optional[str] = None
        self.phase_progress: dict[str, dict] = {}
        self.phase_started_at: dict[str, float] = {}
        self.started_at = time.monotonic()
        self.last_progress_at = self.started_at
        self.preview_ready = False
        self.progress_slot.progress(0.0, text=self._progress_text(0.0, "Not started yet"))
        render_runtime_usage_compact()

    def __call__(self, event: RenderEvent) -> None:
        payload = normalize_payload(dict(event.payload))
        self.events.append({"event": event.name, "message": event.message, "payload": payload})

        if event.name in {"app.phase.started", "render.phase.started"}:
            self.current_phase = str(payload.get("phase", ""))
            if self.current_phase:
                self.phase_started_at[self.current_phase] = time.monotonic()
            self._update()
        elif event.name in {"app.phase.completed", "render.phase.completed"}:
            phase = str(payload.get("phase", ""))
            if phase:
                self.completed.add(phase)
            self.current_phase = phase
            self._update()
        elif event.name == "render.phase.progress":
            phase = str(payload.get("phase", ""))
            if phase:
                self.phase_progress[phase] = payload
                self.current_phase = phase
                self.last_progress_at = time.monotonic()
            self._update()
        elif event.name == "app.preview.ready":
            self.preview_ready = True
            self._update(extra_text="Preview segment available")
        elif event.name == "app.render.completed":
            self.completed.update({"tts", "mix", "subtitle"})
            self.current_phase = "subtitle"
            self._update(extra_text="Render completed")
        elif event.name == "app.validation.completed":
            exit_code = payload.get("exit_code", 0)
            self.progress_slot.progress(1.0, text=self._progress_text(1.0, "Validation completed"))
            if exit_code:
                self.status_slot.error("Validation failed")
            else:
                self.status_slot.success("Validation passed")

        if len(self.events) <= 50:
            self.log_slot.code(json.dumps(self.events[-min(12, len(self.events)):], ensure_ascii=False, indent=2), language="json")
        self.event_slot.caption(f"Latest event: {event.name}")
        render_runtime_usage_compact()

    def _update(self, extra_text: str | None = None) -> None:
        total = len(PHASE_ORDER)
        done = len([p for p in PHASE_ORDER if p in self.completed])
        fraction = done / total if total else 0.0
        if self.current_phase and self.current_phase not in self.completed:
            phase_meta = self.phase_progress.get(self.current_phase, {})
            sub_fraction = 0.08
            raw_total = phase_meta.get("total")
            raw_completed = phase_meta.get("completed")
            try:
                if raw_total not in (None, "", 0):
                    sub_fraction = max(0.0, min(0.999, float(raw_completed or 0) / float(raw_total)))
                elif phase_meta.get("total_seconds") not in (None, "", 0):
                    sub_fraction = max(0.0, min(0.999, float(phase_meta.get("seconds") or 0) / float(phase_meta.get("total_seconds"))))
            except (TypeError, ValueError, ZeroDivisionError):
                sub_fraction = 0.08
            fraction = min(0.98, (done + sub_fraction) / total)
        text = self._phase_text()
        if extra_text:
            text = f"{text} - {extra_text}"
        self.progress_slot.progress(fraction, text=self._progress_text(fraction, text))
        self.status_slot.info(self._progress_text(fraction, text))

    def _progress_percent(self, fraction: float) -> int:
        bounded = max(0.0, min(1.0, fraction))
        return int(round(bounded * 100))

    def _progress_text(self, fraction: float, base_text: str) -> str:
        eta_text = self._eta_text(fraction)
        details = [f"elapsed {format_duration(time.monotonic() - self.started_at)}"]
        if self.current_phase:
            details.append(f"phase {self.current_phase}")
        detail_text = " - " + " | ".join(details) if details else ""
        return f"{self._progress_percent(fraction)}% - {base_text}{eta_text}{detail_text}"

    def _eta_text(self, fraction: float) -> str:
        eta_seconds = self._estimate_eta_seconds(fraction)
        if eta_seconds is None:
            return ""
        if eta_seconds <= 0.5:
            return " - <1s remaining"
        return f" - about {self._format_eta(eta_seconds)} remaining"

    def _estimate_eta_seconds(self, fraction: float) -> float | None:
        bounded = max(0.0, min(1.0, float(fraction or 0.0)))
        now = time.monotonic()
        if bounded >= 0.999:
            return 0.0

        phase_eta = self._estimate_phase_eta_seconds(now)
        if phase_eta is not None:
            remaining_phases = len([p for p in PHASE_ORDER if p not in self.completed and p != self.current_phase])
            if remaining_phases <= 0:
                return max(0.0, phase_eta)
            avg_phase_seconds = max(phase_eta, (now - self.started_at) / max(1, len(self.completed) + 1))
            return max(0.0, phase_eta + remaining_phases * avg_phase_seconds)

        elapsed = max(0.0, now - self.started_at)
        if elapsed < 1.0 or bounded <= 0.01:
            return None
        remaining = elapsed * (1.0 - bounded) / bounded
        return max(0.0, remaining)

    def _estimate_phase_eta_seconds(self, now: float) -> float | None:
        if not self.current_phase or self.current_phase in self.completed:
            return None
        meta = self.phase_progress.get(self.current_phase, {})
        started_at = self.phase_started_at.get(self.current_phase, self.started_at)
        elapsed = max(0.0, now - started_at)
        if elapsed < 1.0:
            return None

        progress = None
        raw_total = meta.get("total")
        raw_completed = meta.get("completed")
        try:
            if raw_total not in (None, "", 0):
                progress = float(raw_completed or 0) / float(raw_total)
            elif meta.get("total_seconds") not in (None, "", 0):
                progress = float(meta.get("seconds") or 0) / float(meta.get("total_seconds"))
        except (TypeError, ValueError, ZeroDivisionError):
            progress = None

        if progress is None:
            return None
        progress = max(0.0, min(0.999, progress))
        if progress <= 0.01:
            return None
        return max(0.0, elapsed * (1.0 - progress) / progress)

    def _format_eta(self, seconds: float) -> str:
        seconds = max(0, int(round(seconds)))
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h > 0:
            return f"{h}h {m:02d}m"
        if m > 0:
            return f"{m}m {s:02d}s"
        return f"{s}s"

    def _format_hms(self, seconds: float) -> str:
        seconds = max(0.0, float(seconds or 0.0))
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:d}:{m:02d}:{s:02d}" if h > 0 else f"{m:d}:{s:02d}"

    def _phase_text(self) -> str:
        if not self.current_phase:
            return "Initializing"
        label = PHASE_LABELS.get(self.current_phase, self.current_phase)
        done = len([p for p in PHASE_ORDER if p in self.completed])
        meta = self.phase_progress.get(self.current_phase or "", {})
        detail = ""
        if meta.get("unit") == "segments" and meta.get("total") not in (None, "", 0):
            detail = f" - {int(meta.get('completed', 0))}/{int(meta.get('total', 0))} segments"
        elif meta.get("stage") == "segments" and meta.get("total") not in (None, "", 0):
            detail = f" - {int(meta.get('completed', 0))}/{int(meta.get('total', 0))} segments"
        elif meta.get("total_seconds") not in (None, "", 0):
            current = float(meta.get("seconds") or 0)
            total_seconds = float(meta.get("total_seconds") or 0)
            detail = f" - {self._format_hms(current)}/{self._format_hms(total_seconds)}"
            if meta.get("stage") == "assemble":
                detail += " assemble"
            elif meta.get("stage") == "post_fx":
                detail += " post-FX"
        return f"{label} ({done}/{len(PHASE_ORDER)} phases completed){detail}"


def save_uploaded_text(uploaded_file) -> str:
    return uploaded_file.getvalue().decode("utf-8")


def write_plain_script_to_temp(plain_text: str, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / "story.txt"
    path.write_text(plain_text, encoding="utf-8")
    return path


def normalize_plain_script_text(plain_text: str) -> tuple[str, bool]:
    text = plain_text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return text, False

    lines = text.split("\n")
    if has_script_marker(lines):
        return text, False

    if detect_body_only_script(lines):
        normalized = "SCRIPT:\n" + text.lstrip("\n")
        return normalized, True

    return text, False


def _normalize_audio_format(value: object) -> str:
    normalized = str(value or "wav").strip().lower()
    return normalized if normalized in {"wav", "mp3"} else "wav"


def make_request(input_path: Path, output_dir: Path, settings: dict | AppConfig | GuiConfigBundle) -> RenderAudioAppRequest:
    if isinstance(settings, GuiConfigBundle):
        app_config = settings.app
        profile_config = settings.profile
    elif isinstance(settings, AppConfig):
        app_config = settings
        profile_config = ProfileConfig.from_mapping({})
    else:
        app_config = AppConfig.from_mapping(settings)
        profile_config = ProfileConfig.from_mapping(settings)
    request = app_config.to_request(input_path, profile_config)
    if request.output_dir != Path(output_dir):
        payload = request.to_payload(serialize_paths=False)
        payload["output_dir"] = output_dir
        request = RenderAudioAppRequest.from_mapping(payload)
    return request


def summarize_result(result: RenderAudioAppResult) -> dict:
    preview_segments = result.preview.segments if result.preview else []
    out_file = str(result.render_artifacts.out_file) if result.render_artifacts and result.render_artifacts.out_file else None
    out_file_name = Path(out_file).name if out_file else None
    out_ext = Path(out_file).suffix.lower() if out_file else ""
    output_format = out_ext.lstrip(".") if out_ext else _normalize_audio_format(getattr(result.request, "audio_format", "wav"))

    return {
        "mode": result.mode,
        "audio_format": output_format,
        "estimated_duration": getattr(result.preview, "estimated_duration_hms", None)
        or getattr(result.render_artifacts, "estimated_duration_hms", None),
        "segment_count": len(preview_segments),
        "debug_json": str(result.preview.debug_json) if result.preview and result.preview.debug_json else None,
        "out_file": out_file,
        "out_file_name": out_file_name,
        "srt_path": str(result.render_artifacts.srt_path) if result.render_artifacts and result.render_artifacts.srt_path else None,
        "wav_dir": str(result.render_artifacts.wav_dir) if result.render_artifacts and result.render_artifacts.wav_dir else None,
        "job_paths": {
            "out_dir": str(result.job_paths.out_dir),
            "wav_dir": str(result.job_paths.wav_dir),
            "out_file": str(result.job_paths.out_file),
            "srt_path": str(result.job_paths.srt_path),
            "debug_json": str(result.job_paths.debug_json),
        },
        "validate_exit_code": result.validate_exit_code,
        "validate_errors": list(result.validate_errors),
        "validate_warnings_count": result.validate_warnings_count,
    }


def build_output_zip(summary: dict) -> bytes | None:
    candidates = []
    for key in ("out_file", "srt_path", "debug_json"):
        raw = summary.get(key)
        if raw and Path(raw).is_file():
            candidates.append(Path(raw))
    if not candidates:
        return None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in candidates:
            zf.write(path, arcname=path.name)
    buf.seek(0)
    return buf.getvalue()


def manifest_preview_rows(manifest) -> list[dict]:
    return [{"defaults": manifest.defaults, "jobs": [asdict(job) for job in manifest.jobs]}]


def output_download_name() -> str:
    return DEFAULT_DOWNLOAD_NAME
