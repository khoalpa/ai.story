from __future__ import annotations

import argparse
from typing import Sequence

from audio.render_audio_app import create_app_request_from_args, create_default_app_request, run_render_audio_app
from audio.render_batch_runner import RenderBatchRunner
from audio.render_observers import build_cli_observer_bundle

from audio.adapters.ffmpeg_audio_mixer import (
    POST_FX_PRESET_NONE,
    POST_FX_PRESET_STORYTELLING_VI,
)
from audio.services.render_runtime import (
    DEFAULT_EN_VOICE_FEMALE,
    DEFAULT_EN_VOICE_MALE,
    DEFAULT_EN_VOICE_NARRATOR,
    DEFAULT_PROFILE_ROOT,
    DEFAULT_VOICE_FEMALE,
    DEFAULT_VOICE_MALE,
    DEFAULT_VOICE_NARRATOR,
)
from audio.paths import ASSETS_ROOT, DEFAULT_BGM_DIR
from audio.tts_provider import get_tts_provider_choices, DEFAULT_TTS_PROVIDER

DEFAULT_ABBR_MAP_FILE = str(ASSETS_ROOT / "abbreviation_map.json")
DEFAULT_BGM_DIR_STR = str(DEFAULT_BGM_DIR)


def build_render_audio_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render audio from a renderer plain script with edge-tts + BGM runtime. Defaults to a WAV master.",
    )
    parser.add_argument("-i", "--input", type=str, default=None, help="File renderer plain script .txt")
    parser.add_argument("-o", "--output", type=str, default=None, help="Audio/subtitle output directory")
    parser.add_argument(
        "--batch-manifest",
        type=str,
        default=None,
        help="Run batch jobs from a JSON/YAML manifest instead of rendering one file.",
    )
    parser.add_argument(
        "--continue-on-batch-error",
        action="store_true",
        help="In batch mode, continue running remaining jobs if one job fails.",
    )
    parser.add_argument(
        "--asset-profile",
        type=str,
        default=None,
        help=(
            "Runtime asset profile name, for example: calm or trend. "
            "The audio renderer resolves manifest.json to read bgm_config/BGM dir/default voices when available."
        ),
    )
    parser.add_argument(
        "--profile-root",
        type=str,
        default=DEFAULT_PROFILE_ROOT,
        help=f"Root directory containing asset profiles (default: {DEFAULT_PROFILE_ROOT})",
    )
    parser.add_argument("--bgm", type=str, default=None, help="Default BGM fallback for the full audio (file name inside the BGM directory)")
    parser.add_argument("--bgmdir", type=str, default=DEFAULT_BGM_DIR_STR, help="Directory containing BGM files when not resolved from an asset profile")
    parser.add_argument("--voice-narrator", type=str, default=DEFAULT_VOICE_NARRATOR, help="Narrator voice")
    parser.add_argument("--voice-female", type=str, default=DEFAULT_VOICE_FEMALE, help="Female voice")
    parser.add_argument("--voice-male", type=str, default=DEFAULT_VOICE_MALE, help="Male voice")
    parser.add_argument(
        "--voice-en-narrator",
        type=str,
        default=DEFAULT_EN_VOICE_NARRATOR,
        help="English narrator voice (when using the [EN] tag)",
    )
    parser.add_argument(
        "--voice-en-female",
        type=str,
        default=DEFAULT_EN_VOICE_FEMALE,
        help="English female voice (when using the [EN] tag)",
    )
    parser.add_argument(
        "--voice-en-male",
        type=str,
        default=DEFAULT_EN_VOICE_MALE,
        help="English male voice (when using the [EN] tag)",
    )
    parser.add_argument(
        "--abbr-map",
        type=str,
        default=DEFAULT_ABBR_MAP_FILE,
        help="JSON file mapping English abbreviations to spoken text (default: abbreviation_map.json)",
    )
    parser.add_argument(
        "--bgm-config",
        type=str,
        default=None,
        help=(
            "BGM config file (JSON or YAML) for env_bgm_map + automatic zone BGM. "
            "By default, the CLI does not force a local file; it prefers asset profile resolution when available. "
            "Volume uses gain_db (dB) through config or the [BGM_DB=...] tag."
        ),
    )
    parser.add_argument(
        "--sentiment-tone",
        action="store_true",
        help="Enable light speed/emotion tuning based on dialogue sentiment.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the renderer plain script and exit without rendering audio.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Do not render audio; only parse the renderer plain script and save debug segments JSON.",
    )
    parser.add_argument(
        "--auto-en-lines",
        action="store_true",
        help="Automatically detect English lines (when they do not have [EN]) and use voice_map_en.",
    )
    parser.add_argument(
        "--post-fx-preset",
        type=str,
        choices=[POST_FX_PRESET_NONE, POST_FX_PRESET_STORYTELLING_VI],
        default=POST_FX_PRESET_NONE,
        help=(
            "Post-processing preset applied after the full audio mix. "
            "storytelling_vi applies a light chain: noise reduction, EQ, compressor, de-esser, reverb, normalize."
        ),
    )
    parser.add_argument(
        "--tts-provider",
        type=str,
        choices=get_tts_provider_choices(),
        default=DEFAULT_TTS_PROVIDER,
        help="Choose TTS engine: edge = cloud Edge TTS; vieneu = VieNeu TTS core (headless/local or remote API).",
    )
    parser.add_argument(
        "--max-concurrent-tts",
        type=int,
        default=8,
        help="Maximum number of parallel edge-tts requests (default: 8).",
    )
    parser.add_argument(
        "--audio-format",
        type=str,
        choices=["wav", "mp3"],
        default="wav",
        help="Output audio format. Defaults to wav for the master; choose mp3 to keep the older publishing workflow.",
    )
    return parser


def parse_render_audio_args(argv: Sequence[str] | None = None):
    return build_render_audio_arg_parser().parse_args(argv)


def _validate_cli_mode_args(args) -> None:
    batch_manifest = getattr(args, "batch_manifest", None)
    has_input = bool(getattr(args, "input", None))
    has_output = bool(getattr(args, "output", None))

    if batch_manifest:
        if has_input or has_output:
            raise SystemExit("--batch-manifest cannot be combined with --input/--output")
        return

    if not has_input or not has_output:
        raise SystemExit("single render mode requires both --input and --output")


def _build_template_request_from_args(args):
    template = create_default_app_request(input_path="__batch__.txt", output_dir="__batch_out__")
    payload = template.to_payload()
    payload.update(
        {
            "asset_profile": getattr(args, "asset_profile", None),
            "profile_root": getattr(args, "profile_root", template.profile_root),
            "bgm": getattr(args, "bgm", None),
            "bgmdir": getattr(args, "bgmdir", template.bgmdir),
            "voice_narrator": getattr(args, "voice_narrator", template.voice_narrator),
            "voice_female": getattr(args, "voice_female", template.voice_female),
            "voice_male": getattr(args, "voice_male", template.voice_male),
            "voice_en_narrator": getattr(args, "voice_en_narrator", template.voice_en_narrator),
            "voice_en_female": getattr(args, "voice_en_female", template.voice_en_female),
            "voice_en_male": getattr(args, "voice_en_male", template.voice_en_male),
            "abbr_map": getattr(args, "abbr_map", template.abbr_map),
            "bgm_config": getattr(args, "bgm_config", None),
            "sentiment_tone": bool(getattr(args, "sentiment_tone", False)),
            "validate_only": bool(getattr(args, "validate_only", False)),
            "debug": bool(getattr(args, "debug", False)),
            "auto_en_lines": bool(getattr(args, "auto_en_lines", False)),
            "post_fx_preset": getattr(args, "post_fx_preset", template.post_fx_preset),
            "max_concurrent_tts": int(getattr(args, "max_concurrent_tts", template.max_concurrent_tts)),
            "tts_provider": str(getattr(args, "tts_provider", template.tts_provider)).lower(),
            "audio_format": str(getattr(args, "audio_format", template.audio_format)).lower(),
        }
    )
    return template.__class__.from_mapping(payload)


def run_cli_args(args, *, ffmpeg_exe: str, ffprobe_exe: str):
    _validate_cli_mode_args(args)
    observers = build_cli_observer_bundle()
    reporter = observers.reporter
    event_bus = observers.bus

    batch_manifest = getattr(args, "batch_manifest", None)
    if batch_manifest:
        runner = RenderBatchRunner(observers.repository)
        template = _build_template_request_from_args(args)
        batch_result = runner.run_manifest(
            batch_manifest,
            ffmpeg_exe=ffmpeg_exe,
            ffprobe_exe=ffprobe_exe,
            template=template,
            event_sink=event_bus,
            continue_on_error=bool(getattr(args, "continue_on_batch_error", False)),
        )
        reporter.report_batch_summary(batch_manifest, total=batch_result.total, succeeded=batch_result.succeeded, failed=batch_result.failed)
        reporter.print_used_files_summary()
        if batch_result.failed:
            raise SystemExit(1)
        return batch_result

    request = create_app_request_from_args(args)
    result = run_render_audio_app(
        request,
        ffmpeg_exe=ffmpeg_exe,
        ffprobe_exe=ffprobe_exe,
        event_sink=event_bus,
    )

    if result.mode == "validate_only":
        raise SystemExit(result.validate_exit_code or 0)

    reporter.print_used_files_summary()
    return result


def run_cli(argv: Sequence[str] | None = None, *, ffmpeg_exe: str, ffprobe_exe: str):
    args = build_render_audio_arg_parser().parse_args(argv)
    return run_cli_args(args, ffmpeg_exe=ffmpeg_exe, ffprobe_exe=ffprobe_exe)
