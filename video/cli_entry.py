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

DESCRIPTION = "Render video MP4 từ audio đã hoàn tất + cover image hoặc slideshow scenes."




def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument(
        "--audio", type=str, required=True, help="Đường dẫn file audio đầu vào (vd: output/story.mp3)."
    )
    parser.add_argument(
        "--output", type=str, required=True, help="Đường dẫn file MP4 đầu ra (vd: output/video.mp4)."
    )
    parser.add_argument(
        "--asset-profile",
        type=str,
        default=None,
        help="Tên asset profile runtime, ví dụ: calm hoặc trend. Video renderer sẽ resolve manifest.json để lấy default_cover/default_scenes_dir nếu có.",
    )
    parser.add_argument(
        "--profile-root",
        type=str,
        default=DEFAULT_PROFILE_ROOT,
        help=f"Thư mục gốc chứa asset profiles (mặc định: {DEFAULT_PROFILE_ROOT})",
    )
    parser.add_argument(
        "--cover",
        type=str,
        default=None,
        help="Ảnh bìa cho mode static (vd: cover/cover_story.jpg).",
    )
    parser.add_argument(
        "--scenes-dir", type=str, default=None, help="Thư mục chứa scene images cho mode slideshow."
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["static", "slideshow"],
        required=True,
        help="Kiểu render video: static (1 ảnh) hoặc slideshow (nhiều ảnh).",
    )
    parser.add_argument(
        "--aspect",
        type=str,
        choices=["9x16", "16x9"],
        default="9x16",
        help="Tỉ lệ khung hình: 9x16 (TikTok) hoặc 16x9 (YouTube).",
    )
    parser.add_argument(
        "--duration-per-image",
        type=float,
        default=60.0,
        help="Thời lượng mỗi ảnh trong slideshow (giây). Mặc định 60.0",
    )
    parser.add_argument(
        "--subtitle",
        type=str,
        default=None,
        help="Optional: file subtitle (SRT/ASS) để burn vào MP4.",
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
        raise FileNotFoundError(f"Không tìm thấy subtitle: {request.subtitle}")
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

    print(f"Đã tạo file video: {request.output}")
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
