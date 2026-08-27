from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from video.app_api import execute_render_request, request_from_args
from video.cli_utils import UsedFilesTracker, setup_stdio
from video.encoding_profiles import PROFILE_CHOICES
from video.error_handling import USER_FACING_EXCEPTIONS, format_user_facing_error
from video.ffmpeg_runner import ensure_tools
from video.validation import ImageReadinessReport, inspect_video_image_readiness

DESCRIPTION = "Render an MP4 video from finished audio plus a cover image or slideshow scenes."




def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument(
        "--audio", type=str, default=None, help="Input audio file; overrides --audio-handoff."
    )
    parser.add_argument("--audio-handoff", default=None, help="audio.video-handoff manifest path.")
    parser.add_argument(
        "--output", type=str, required=True, help="Output MP4 file path (for example: output/video.mp4)."
    )
    parser.add_argument(
        "--cover",
        type=str,
        default=None,
        help="Cover image for static mode or the opening frame of slideshow mode.",
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
        "--cover-first",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Show the cover at the start of slideshow videos (default: enabled).",
    )
    parser.add_argument(
        "--cover-duration",
        type=float,
        default=3.0,
        help="Seconds to show the opening cover without extending the audio timeline (default: 3.0).",
    )
    parser.add_argument(
        "--outro-last",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use outro.png as the slideshow end screen (default: enabled).",
    )
    parser.add_argument(
        "--outro-duration",
        type=float,
        default=5.0,
        help="Seconds to show outro.png at the end without extending the audio timeline (default: 5.0).",
    )
    parser.add_argument(
        "--encoding-profile",
        choices=PROFILE_CHOICES,
        default="auto",
        help="Encoding profile: auto, balanced, youtube_4k, youtube_1080p, tiktok, master, or master_hevc.",
    )
    parser.add_argument(
        "--loudness-profile",
        choices=["narration", "social_video", "broadcast"],
        default="narration",
        help="Output loudness target used for MP4 audio.",
    )
    parser.add_argument(
        "--quality-gate",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Validate audio, video, sync, subtitle, decode, faststart, and sampled SSIM after render.",
    )
    parser.add_argument(
        "--subtitle",
        type=str,
        default=None,
        help="Optional subtitle file (SRT/ASS) to burn into the MP4.",
    )
    parser.add_argument(
        "--show-subtitles",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Burn subtitles into the MP4 when available (default: enabled).",
    )
    parser.add_argument(
        "--story-json",
        type=str,
        default=None,
        help="Optional timeline JSON file for zone-aware slideshow timing.",
    )
    parser.add_argument(
        "--zone-aware-slideshow",
        action="store_true",
        help="In slideshow mode, time scene images from timeline zones and subtitle timestamps.",
    )
    parser.add_argument(
        "--environment-overlays",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Apply atmosphere overlays from story.json environment fields (default: enabled).",
    )
    parser.add_argument(
        "--environment-overlay-intensity",
        choices=["subtle", "normal", "cinematic"],
        default="normal",
    )
    parser.add_argument("--environment-overlay-fade", type=float, default=0.6)
    parser.add_argument(
        "--environment-allow-lens-effects",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--environment-global-film-grain", type=float, default=0.0)
    parser.add_argument(
        "--check-images",
        action="store_true",
        help="Check cover/scenes readiness and exit without rendering.",
    )
    return parser


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def _print_image_readiness(report: ImageReadinessReport) -> None:
    print("Image readiness: READY" if report.ready else "Image readiness: NOT READY")
    print(f"Expected resolution: {report.expected_width}x{report.expected_height}")
    if report.scene_count:
        print(f"Scene images: {report.scene_count}")
    if report.mapped_zones:
        print("Mapped zones: " + ", ".join(report.mapped_zones))
    if report.errors:
        print("Errors:")
        for message in report.errors:
            print(f"  - {message}")
    if report.warnings:
        print("Warnings:")
        for message in report.warnings:
            print(f"  - {message}")


def run_from_args(args: argparse.Namespace) -> Path:
    used_files = UsedFilesTracker()
    request, _, _ = request_from_args(args)
    image_readiness = inspect_video_image_readiness(
        mode=request.mode,
        aspect=request.aspect,
        cover=request.cover,
        scenes_dir=request.scenes_dir,
        cover_first=request.cover_first,
        outro_last=request.outro_last,
    )
    if getattr(args, "check_images", False):
        _print_image_readiness(image_readiness)
        if image_readiness.errors:
            raise ValueError("Images are not ready for video render.")
        return request.output
    if image_readiness.errors:
        _print_image_readiness(image_readiness)
        raise ValueError("Images are not ready for video render.")
    ensure_tools()
    used_files.add("Input audio", request.audio)
    used_files.add("Rendered video", request.output)

    if request.subtitle is not None and not request.subtitle.is_file():
        raise FileNotFoundError(f"Subtitle not found: {request.subtitle}")
    if request.cover is not None:
        used_files.add("Cover image", request.cover)
    if request.scenes_dir is not None:
        used_files.add("Scenes directory", request.scenes_dir)
    if request.subtitle is not None:
        used_files.add("Subtitle file", request.subtitle)
    if request.story_json is not None:
        if not request.story_json.is_file():
            raise FileNotFoundError(f"story.json not found: {request.story_json}")
        used_files.add("Timeline JSON", request.story_json)

    result = execute_render_request(request)

    print(f"Created video file: {request.output}")
    print(f"Created result manifest: {result['result_manifest_path']}")
    quality_report = Path(result["quality_report_path"])
    print(f"Created video quality report: {quality_report}")
    used_files.add("Video quality report", quality_report)
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
