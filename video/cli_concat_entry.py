from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from video.app_api import ConcatClipsRequest, execute_concat_request
from video.encoding_profiles import PROFILE_CHOICES
from video.error_handling import USER_FACING_EXCEPTIONS, format_user_facing_error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Join numbered video clips into one MP4 file."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--clips-dir", help="Directory containing clip_0001.mp4, clip_0002.mp4, ..."
    )
    source.add_argument(
        "--clip", action="append", dest="clips", help="Input clip in the desired order; repeat as needed."
    )
    parser.add_argument("--pattern", default="clip_*", help="Glob used with --clips-dir.")
    parser.add_argument("--output", required=True, help="Output MP4 path.")
    parser.add_argument(
        "--strategy", choices=["auto", "copy", "normalize"], default="auto"
    )
    parser.add_argument("--audio-mode", choices=["keep", "mute"], default="keep")
    parser.add_argument("--aspect", choices=["9x16", "16x9"], default="16x9")
    parser.add_argument("--encoding-profile", choices=PROFILE_CHOICES, default="auto")
    parser.add_argument("--ffmpeg-exe", default=None)
    parser.add_argument("--ffprobe-exe", default=None)
    parser.add_argument("--keep-concat-list", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    request = ConcatClipsRequest(
        clips=tuple(Path(value) for value in (args.clips or [])),
        clips_dir=Path(args.clips_dir) if args.clips_dir else None,
        pattern=args.pattern,
        output=Path(args.output),
        strategy=args.strategy,
        audio_mode=args.audio_mode,
        aspect=args.aspect,
        encoding_profile=args.encoding_profile,
        ffmpeg_exe=args.ffmpeg_exe,
        ffprobe_exe=args.ffprobe_exe,
        keep_concat_list=args.keep_concat_list,
    )
    try:
        result = execute_concat_request(request)
    except USER_FACING_EXCEPTIONS as exc:
        raise SystemExit(format_user_facing_error(exc)) from exc
    print(f"Created: {result.output}")
    print(f"Clips: {len(result.clips)}")
    print(f"Strategy: {result.strategy_used}")
    print(f"Expected duration: {result.duration_seconds:.3f}s")
