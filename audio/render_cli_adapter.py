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
from audio.paths import ASSETS_ROOT
from audio.tts_provider import get_tts_provider_choices, DEFAULT_TTS_PROVIDER

DEFAULT_ABBR_MAP_FILE = str(ASSETS_ROOT / "abbreviation_map.json")


def build_render_audio_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render audio từ renderer plain script bằng edge-tts + BGM runtime. Mặc định xuất WAV master.",
    )
    parser.add_argument("-i", "--input", type=str, default=None, help="File renderer plain script .txt")
    parser.add_argument("-o", "--output", type=str, default=None, help="Thư mục output audio/subtitle")
    parser.add_argument(
        "--batch-manifest",
        type=str,
        default=None,
        help="Chạy batch jobs từ manifest JSON/YAML thay vì render 1 file đơn lẻ.",
    )
    parser.add_argument(
        "--continue-on-batch-error",
        action="store_true",
        help="Ở batch mode, tiếp tục chạy các job còn lại nếu một job lỗi.",
    )
    parser.add_argument(
        "--asset-profile",
        type=str,
        default=None,
        help=(
            "Tên asset profile runtime, ví dụ: calm hoặc trend. "
            "Audio renderer sẽ resolve manifest.json để lấy bgm_config/bgm dir/voice mặc định nếu có."
        ),
    )
    parser.add_argument(
        "--profile-root",
        type=str,
        default=DEFAULT_PROFILE_ROOT,
        help=f"Thư mục gốc chứa asset profiles (mặc định: {DEFAULT_PROFILE_ROOT})",
    )
    parser.add_argument("--bgm", type=str, default=None, help="BGM fallback mặc định cho toàn audio (tên file trong bgm dir)")
    parser.add_argument("--bgmdir", type=str, default="audio/bgm", help="Thư mục chứa file BGM khi không resolve từ asset profile")
    parser.add_argument("--voice-narrator", type=str, default=DEFAULT_VOICE_NARRATOR, help="Giọng narrator (MC)")
    parser.add_argument("--voice-female", type=str, default=DEFAULT_VOICE_FEMALE, help="Giọng nữ")
    parser.add_argument("--voice-male", type=str, default=DEFAULT_VOICE_MALE, help="Giọng nam")
    parser.add_argument(
        "--voice-en-narrator",
        type=str,
        default=DEFAULT_EN_VOICE_NARRATOR,
        help="Giọng English cho narrator (khi dùng tag [EN])",
    )
    parser.add_argument(
        "--voice-en-female",
        type=str,
        default=DEFAULT_EN_VOICE_FEMALE,
        help="Giọng English cho female (khi dùng tag [EN])",
    )
    parser.add_argument(
        "--voice-en-male",
        type=str,
        default=DEFAULT_EN_VOICE_MALE,
        help="Giọng English cho male (khi dùng tag [EN])",
    )
    parser.add_argument(
        "--abbr-map",
        type=str,
        default=DEFAULT_ABBR_MAP_FILE,
        help="File JSON mapping viết tắt tiếng Anh → text đọc (mặc định: abbreviation_map.json)",
    )
    parser.add_argument(
        "--bgm-config",
        type=str,
        default=None,
        help=(
            "File config BGM (JSON hoặc YAML) cho env_bgm_map + auto BGM theo zone. "
            "Mặc định CLI không ép dùng file local nào; ưu tiên resolve từ asset profile nếu có. "
            "Chuẩn âm lượng dùng gain_db (dB) qua config hoặc tag [BGM_DB=...]."
        ),
    )
    parser.add_argument(
        "--sentiment-tone",
        action="store_true",
        help="Bật tinh chỉnh nhẹ tốc độ/emo theo cảm xúc câu thoại.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Chỉ validate renderer plain script rồi thoát, không render audio.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Không render audio; chỉ parse renderer plain script và lưu segments debug JSON.",
    )
    parser.add_argument(
        "--auto-en-lines",
        action="store_true",
        help="Tự nhận diện line tiếng Anh (nếu chưa có tag [EN]) để dùng voice_map_en.",
    )
    parser.add_argument(
        "--post-fx-preset",
        type=str,
        choices=[POST_FX_PRESET_NONE, POST_FX_PRESET_STORYTELLING_VI],
        default=POST_FX_PRESET_NONE,
        help=(
            "Preset hậu kỳ chạy sau khi đã mix toàn bộ audio. "
            "storytelling_vi áp chuỗi xử lý nhẹ: noise reduction, EQ, compressor, de-esser, reverb, normalize."
        ),
    )
    parser.add_argument(
        "--tts-provider",
        type=str,
        choices=get_tts_provider_choices(),
        default=DEFAULT_TTS_PROVIDER,
        help="Chọn engine TTS: edge = cloud Edge TTS; vieneu = VieNeu TTS core (headless/local hoặc remote API).",
    )
    parser.add_argument(
        "--max-concurrent-tts",
        type=int,
        default=8,
        help="Số request edge-tts chạy song song tối đa (mặc định: 8).",
    )
    parser.add_argument(
        "--audio-format",
        type=str,
        choices=["wav", "mp3"],
        default="wav",
        help="Định dạng audio đầu ra. Mặc định wav để lưu master; chọn mp3 để giữ workflow phát hành cũ.",
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
