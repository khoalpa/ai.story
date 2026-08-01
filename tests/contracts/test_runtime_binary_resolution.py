from pathlib import Path

from audio import runtime_binaries as audio_runtime
from audio.runtime_checks import validate_runtime_executables
from video import runtime_tools as video_runtime


def _assert_chocolatey_shim_is_bypassed(monkeypatch, module) -> None:
    fallback = Path(
        r"C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin\ffmpeg.exe"
    )
    monkeypatch.delenv("FFMPEG_EXE", raising=False)
    monkeypatch.setattr(module.shutil, "which", lambda _name: r"C:\ProgramData\chocolatey\bin\ffmpeg.exe")
    monkeypatch.setattr(module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(Path, "is_file", lambda self: self == fallback)

    assert module.resolve_tool_path("FFMPEG_EXE", "ffmpeg", fallback) == str(fallback)


def test_video_runtime_bypasses_chocolatey_shim(monkeypatch) -> None:
    _assert_chocolatey_shim_is_bypassed(monkeypatch, video_runtime)


def test_audio_runtime_bypasses_chocolatey_shim(monkeypatch) -> None:
    _assert_chocolatey_shim_is_bypassed(monkeypatch, audio_runtime)


def test_explicit_environment_override_still_wins(monkeypatch) -> None:
    explicit = r"D:\approved-tools\ffmpeg.exe"
    monkeypatch.setenv("FFMPEG_EXE", explicit)
    monkeypatch.setattr(
        video_runtime.shutil,
        "which",
        lambda _name: r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
    )

    assert (
        video_runtime.resolve_tool_path(
            "FFMPEG_EXE",
            "ffmpeg",
            video_runtime.DEFAULT_WINDOWS_FFMPEG,
        )
        == explicit
    )


def test_audio_validation_normalizes_explicit_chocolatey_shims(monkeypatch) -> None:
    ffmpeg_fallback = audio_runtime.DEFAULT_WINDOWS_FFMPEG
    ffprobe_fallback = audio_runtime.DEFAULT_WINDOWS_FFPROBE
    monkeypatch.setattr(audio_runtime.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda self: self in {ffmpeg_fallback, ffprobe_fallback},
    )

    resolved = validate_runtime_executables(
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
        r"C:\ProgramData\chocolatey\bin\ffprobe.exe",
    )

    assert resolved.ffmpeg_exe == str(ffmpeg_fallback)
    assert resolved.ffprobe_exe == str(ffprobe_fallback)
