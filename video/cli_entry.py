from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from video.cli_utils import UsedFilesTracker, setup_stdio
from video.config import DEFAULT_PROFILE_ROOT
from video.error_handling import USER_FACING_EXCEPTIONS, format_user_facing_error
from video.ffmpeg_runner import ensure_tools
from video.app_api import execute_render_request, request_from_args

DESCRIPTION = "Render an MP4 video from finished audio plus a cover image or slideshow scenes."




def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument(
        "--audio", type=str, required=True, help="Input audio file path (for example: output/story.mp3)."
    )
    parser.add_argument(
        "--output", type=str, required=True, help="Output MP4 file path (for example: output/video.mp4)."
    )
    parser.add_argument(
        "--asset-profile",
        type=str,
        default=None,
        help="Runtime asset profile name, for example: calm or trend. The video renderer resolves manifest.json to read default_cover/default_scenes_dir when available.",
    )
    parser.add_argument(
        "--profile-root",
        type=str,
        default=DEFAULT_PROFILE_ROOT,
        help=f"Root directory containing asset profiles (default: {DEFAULT_PROFILE_ROOT})",
    )
    parser.add_argument(
        "--cover",
        type=str,
        default=None,
        help="Cover image for static mode (for example: cover/cover_story.jpg).",
    )
    parser.add_argument(
        "--scenes-dir", type=str, default=None, help="Directory containing scene images for slideshow mode."
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["static", "slideshow"],
        required=True,
        help="Video render mode: static (1 image) or slideshow (multiple images).",
    )
    parser.add_argument(
        "--aspect",
        type=str,
        choices=["9x16", "16x9"],
        default="9x16",
        help="Aspect ratio: 9x16 (TikTok) or 16x9 (YouTube).",
    )
    parser.add_argument(
        "--duration-per-image",
        type=float,
        default=60.0,
        help="Duration of each slideshow image in seconds. Default: 60.0",
    )
    parser.add_argument(
        "--subtitle",
        type=str,
        default=None,
        help="Optional subtitle file (SRT/ASS) to burn into the MP4.",
    )
    return parser


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def run_from_args(args: argparse.Namespace) -> Path:
    used_files = UsedFilesTracker()
    request, profile_dir, defaults = request_from_args(args)
    ensure_tools()
    if request.asset_profile:
        used_files.note("Asset profile", request.asset_profile)
    if profile_dir is not None:
        print(f"Using asset profile: {request.asset_profile} ({profile_dir})")
        used_files.add("Resolved profile directory", profile_dir)

    used_files.add("Input audio", request.audio)
    used_files.add("Rendered video", request.output)

    if request.subtitle is not None and not request.subtitle.is_file():
        raise FileNotFoundError(f"Subtitle not found: {request.subtitle}")
    if request.cover is not None:
        used_files.add("Cover image", request.cover)
    elif request.mode == "static" and defaults.get("cover") is not None:
        used_files.add("Default cover from profile", defaults["cover"])
    if request.scenes_dir is not None:
        used_files.add("Scenes directory", request.scenes_dir)
    elif request.mode == "slideshow" and defaults.get("scenes_dir") is not None:
        used_files.add("Default scenes directory from profile", defaults["scenes_dir"])
    if request.subtitle is not None:
        used_files.add("Subtitle file", request.subtitle)

    execute_render_request(request)

    print(f"Created video file: {request.output}")
    used_files.print_summary()
    return request.output


def main(argv: Optional[Sequence[str]] = None) -> None:
    setup_stdio()
    args = parse_args(argv)
    try:
        run_from_args(args)
    except USER_FACING_EXCEPTIONS as exc:
        print(format_user_facing_error(exc), file=sys.stderr)
        raise SystemExit(2) from exc
