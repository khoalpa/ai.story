#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

"""
Render audio từ plain audio-story script bằng edge-tts.

Entrypoint này giữ đúng vai trò mỏng:
- setup stdio / warning runtime
- delegate CLI parsing + orchestration cho app layer
"""

from pathlib import Path
from typing import Sequence

from audio.cli_utils import setup_stdio
from audio.adapters.edge_tts import warn_if_edge_tts_looks_outdated
from audio.runtime_binaries import get_ffmpeg_exe, get_ffprobe_exe
from audio.render_audio_app import validate_only_script
from audio.render_cli_adapter import run_cli as run_cli_entrypoint, run_cli_args
from audio.render_reporting import RenderReporter
from audio.services.subtitle import seconds_to_srt_timestamp

def validate_only_mode(input_path: Path) -> int:
    exit_code, errors, warnings_count = validate_only_script(input_path)
    RenderReporter().report_validation_result(input_path, exit_code, errors, warnings_count)
    return exit_code


def run_cli(args) -> None:
    run_cli_args(args, ffmpeg_exe=get_ffmpeg_exe(), ffprobe_exe=get_ffprobe_exe())


def main(argv: Sequence[str] | None = None) -> None:
    setup_stdio()
    warn_if_edge_tts_looks_outdated()
    run_cli_entrypoint(argv, ffmpeg_exe=get_ffmpeg_exe(), ffprobe_exe=get_ffprobe_exe())


if __name__ == "__main__":
    main()
