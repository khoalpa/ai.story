from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from audio.runtime_diagnostics import (
    RuntimeDiagnosticsReport,
    collect_runtime_diagnostics as _collect_runtime_diagnostics,
    format_runtime_diagnostics,
    resolve_tool_path,
)
from audio.paths import ASSETS_ROOT
from audio.exceptions import (
    AssetProfileError,
    DependencyError,
    FfmpegDependencyError,
    RuntimePathError,
)
from audio.logging_utils import get_logger
from audio.paths import PACKAGE_PROFILE_ROOT

logger = get_logger(__name__)


@dataclass(frozen=True)
class RuntimeExecutables:
    ffmpeg_exe: str
    ffprobe_exe: str


@dataclass(frozen=True)
class ResolvedRuntimePaths:
    input_path: Path
    output_dir: Path
    profile_root: Path
    bgm_dir: Optional[Path]
    abbr_map_path: Path
    bgm_config_path: Optional[Path]


RuntimeDiagnostics = RuntimeDiagnosticsReport


_USER_FACING_LABELS = {
    "ffmpeg": "FFmpeg",
    "ffprobe": "FFprobe",
}


def _resolve_command(executable: str, label: str, exc_type=DependencyError) -> str:
    raw = str(executable or "").strip()
    if not raw:
        raise exc_type(f"{label} executable is not configured")
    if resolve_tool_path(raw):
        return raw
    raise exc_type(
        f"{label} executable not found: {raw}. Install {_USER_FACING_LABELS.get(label, label)} and make sure the binary is in PATH or the configured path is correct."
    )


def collect_runtime_diagnostics(ffmpeg_exe: str, ffprobe_exe: str) -> RuntimeDiagnostics:
    return _collect_runtime_diagnostics(
        tool_configs=(("ffmpeg", ffmpeg_exe), ("ffprobe", ffprobe_exe)),
        dependency_modules=("edge_tts", "streamlit", "vieneu"),
    )


def runtime_diagnostics_to_lines(diagnostics: RuntimeDiagnostics) -> list[str]:
    rendered = []
    for line in format_runtime_diagnostics(diagnostics):
        for raw, display in _USER_FACING_LABELS.items():
            if line.startswith(f"{raw}:"):
                line = line.replace(f"{raw}:", f"{display}:", 1)
        if line.startswith("edge_tts:"):
            line = line.replace("edge_tts:", "edge-tts:", 1)
        if line.startswith("vieneu:"):
            line = line.replace("vieneu:", "VieNeu SDK:", 1)
        rendered.append(line)
    return rendered



def validate_runtime_executables(ffmpeg_exe: str, ffprobe_exe: str) -> RuntimeExecutables:
    return RuntimeExecutables(
        ffmpeg_exe=_resolve_command(ffmpeg_exe, "ffmpeg", FfmpegDependencyError),
        ffprobe_exe=_resolve_command(ffprobe_exe, "ffprobe", FfmpegDependencyError),
    )



def validate_request_paths(request) -> ResolvedRuntimePaths:
    input_path = Path(request.input_path)
    if not input_path.is_file():
        raise RuntimePathError(f"Input file not found: {input_path}")

    output_dir = Path(request.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    profile_root = Path(getattr(request, "profile_root", str(PACKAGE_PROFILE_ROOT)))
    if getattr(request, "asset_profile", None):
        profile_dir = profile_root / str(request.asset_profile)
        manifest_path = profile_dir / "manifest.json"
        if not profile_dir.is_dir():
            raise AssetProfileError(f"Asset profile directory not found: {profile_dir}")
        if not manifest_path.is_file():
            raise AssetProfileError(f"Asset profile manifest not found: {manifest_path}")

    bgm_dir = None
    if getattr(request, "bgmdir", None):
        bgm_dir = Path(request.bgmdir)
    abbr_map_path = Path(getattr(request, "abbr_map", str(ASSETS_ROOT / "abbreviation_map.json")))
    bgm_config = getattr(request, "bgm_config", None)
    bgm_config_path = Path(bgm_config) if bgm_config else None

    logger.debug(
        "Validated request paths",
        extra={
            "input_path": str(input_path),
            "output_dir": str(output_dir),
            "profile_root": str(profile_root),
        },
    )
    return ResolvedRuntimePaths(
        input_path=input_path,
        output_dir=output_dir,
        profile_root=profile_root,
        bgm_dir=bgm_dir,
        abbr_map_path=abbr_map_path,
        bgm_config_path=bgm_config_path,
    )


def collect_runtime_diagnostics_for_settings(ffmpeg_exe: str, ffprobe_exe: str, *, tts_provider: str = "edge", vieneu_mode: str = "turbo") -> RuntimeDiagnostics:
    from audio.tts_provider import get_tts_provider_descriptor, normalize_tts_provider

    provider = normalize_tts_provider(tts_provider)
    descriptor = get_tts_provider_descriptor(provider)
    dependencies = ["edge_tts", "streamlit"]
    if descriptor.optional_dependency:
        dependencies.append(descriptor.optional_dependency)
    return _collect_runtime_diagnostics(
        tool_configs=(("ffmpeg", ffmpeg_exe), ("ffprobe", ffprobe_exe)),
        dependency_modules=tuple(dict.fromkeys(dependencies)),
    )
