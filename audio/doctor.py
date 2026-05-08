from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Sequence

from audio.paths import ASSETS_ROOT
from audio.runtime_binaries import get_ffmpeg_exe, get_ffprobe_exe
from audio.runtime_checks import collect_runtime_diagnostics, runtime_diagnostics_to_lines


DEFAULT_PROFILE_ROOT = (ASSETS_ROOT / "profiles").resolve()
DEFAULT_BGM_DIR = (ASSETS_ROOT / "bgm").resolve()
DEFAULT_EXAMPLE = (Path(__file__).resolve().parent.parent / "examples" / "plain_script_smoke.txt").resolve()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect runtime health for Render Audio.")
    parser.add_argument("--ffmpeg", default=get_ffmpeg_exe(), help="FFmpeg executable or path")
    parser.add_argument("--ffprobe", default=get_ffprobe_exe(), help="FFprobe executable or path")
    parser.add_argument("--profile-root", default=str(DEFAULT_PROFILE_ROOT), help="Asset profile root directory")
    parser.add_argument("--bgm-dir", default=str(DEFAULT_BGM_DIR), help="Background music directory")
    parser.add_argument("--example-script", default=str(DEFAULT_EXAMPLE), help="Example script for smoke validation")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    diagnostics = collect_runtime_diagnostics(args.ffmpeg, args.ffprobe)

    print("== Runtime diagnostics ==")
    for line in runtime_diagnostics_to_lines(diagnostics):
        print(f"- {line}")

    profile_root = Path(args.profile_root)
    bgm_dir = Path(args.bgm_dir)
    example_script = Path(args.example_script)

    print("== Project assets ==")
    print(f"- Profile root: {profile_root.resolve()} | {'OK' if profile_root.is_dir() else 'missing'}")
    demo_profile = profile_root / "demo"
    demo_manifest = demo_profile / "manifest.json"
    print(f"- Demo profile manifest: {demo_manifest.resolve()} | {'OK' if demo_manifest.is_file() else 'missing'}")
    print(f"- BGM dir: {bgm_dir.resolve()} | {'OK' if bgm_dir.is_dir() else 'missing'}")
    default_bgm = bgm_dir / "bgm_lofi.mp3"
    print(f"- Default BGM fallback: {default_bgm.resolve()} | {'OK' if default_bgm.is_file() else 'missing'}")
    print(f"- Example smoke script: {example_script.resolve()} | {'OK' if example_script.is_file() else 'missing'}")

    ffmpeg_tool = diagnostics.tool('ffmpeg')
    ffprobe_tool = diagnostics.tool('ffprobe')
    edge_tts_dep = diagnostics.dependency('edge_tts')
    has_errors = not (ffmpeg_tool and ffmpeg_tool.available) or not (ffprobe_tool and ffprobe_tool.available) or not (edge_tts_dep and edge_tts_dep.available)
    if has_errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
