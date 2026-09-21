from __future__ import annotations

from pathlib import Path


def build_clip_concat_cmd(
    *,
    ffmpeg_exe: str,
    concat_list: Path,
    output: Path,
    audio_mode: str,
) -> list[str]:
    command = [
        ffmpeg_exe, "-hide_banner", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list), "-map", "0:v:0",
    ]
    if audio_mode == "keep":
        command.extend(["-map", "0:a:0?"])
    else:
        command.append("-an")
    command.extend(["-c", "copy", "-movflags", "+faststart", str(output)])
    return command


def build_clip_normalize_cmd(
    *,
    ffmpeg_exe: str,
    clip: Path,
    output: Path,
    duration: float,
    has_audio: bool,
    audio_mode: str,
    width: int,
    height: int,
    fps: int,
    video_codec: str,
    preset: str,
    crf: int,
    pixel_format: str,
    audio_codec: str,
    audio_bitrate: str,
) -> list[str]:
    command = [ffmpeg_exe, "-hide_banner", "-y", "-i", str(clip)]
    add_silence = audio_mode == "keep" and not has_audio
    if add_silence:
        command.extend([
            "-f", "lavfi", "-t", f"{duration:.6f}", "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
        ])
    command.extend([
        "-map", "0:v:0", "-vf",
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,fps={fps}",
        "-c:v", video_codec, "-preset", preset, "-crf", str(crf),
        "-pix_fmt", pixel_format, "-fps_mode", "cfr",
    ])
    if audio_mode == "keep":
        command.extend(["-map", "1:a:0" if add_silence else "0:a:0"])
        command.extend([
            "-c:a", audio_codec, "-b:a", audio_bitrate,
            "-ar", "48000", "-ac", "2",
        ])
    else:
        command.append("-an")
    command.extend([
        "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", str(output)
    ])
    return command


def build_static_ffmpeg_cmd(
    *,
    ffmpeg_base: list[str],
    cover: Path,
    audio: Path,
    output: Path,
    vf_filter: str,
    video_codec: str,
    preset: str,
    crf: int,
    tune: str,
    fps: int,
    audio_codec: str,
    audio_bitrate: str,
    movflags: str,
    pixel_format: str = "yuv420p",
    color_primaries: str = "bt709",
    color_transfer: str = "bt709",
    color_space: str = "bt709",
    color_range: str = "tv",
    gop_seconds: float = 2.0,
) -> list[str]:
    gop = max(1, int(round(fps * gop_seconds)))
    return [
        *ffmpeg_base,
        "-y",
        "-framerate",
        str(fps),
        "-loop",
        "1",
        "-i",
        str(cover),
        "-i",
        str(audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-vf",
        vf_filter,
        "-c:v",
        video_codec,
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-tune",
        tune,
        "-fps_mode",
        "cfr",
        "-r",
        str(fps),
        "-g",
        str(gop),
        "-keyint_min",
        str(max(1, fps)),
        "-sc_threshold",
        "40",
        "-force_key_frames",
        f"expr:gte(t,n_forced*{gop_seconds})",
        "-pix_fmt",
        pixel_format,
        "-color_primaries",
        color_primaries,
        "-color_trc",
        color_transfer,
        "-colorspace",
        color_space,
        "-color_range",
        color_range,
        "-c:a",
        audio_codec,
        "-b:a",
        audio_bitrate,
        "-ar",
        "48000",
        "-ac",
        "2",
        "-avoid_negative_ts",
        "make_zero",
        "-max_muxing_queue_size",
        "1024",
        "-movflags",
        movflags,
        "-shortest",
        str(output),
    ]


def build_slideshow_ffmpeg_cmd(
    *,
    ffmpeg_base: list[str],
    concat_list: Path,
    audio: Path,
    output: Path,
    vf_filter: str,
    vf_filter_script: Path | None = None,
    video_codec: str,
    preset: str,
    crf: int,
    tune: str,
    audio_codec: str,
    audio_bitrate: str,
    movflags: str,
    fps: int = 30,
    pixel_format: str = "yuv420p",
    color_primaries: str = "bt709",
    color_transfer: str = "bt709",
    color_space: str = "bt709",
    color_range: str = "tv",
    gop_seconds: float = 2.0,
    force_key_frames: str | None = None,
) -> list[str]:
    gop = max(1, int(round(fps * gop_seconds)))
    command = [
        *ffmpeg_base,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list),
        "-i",
        str(audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-fps_mode",
        "cfr",
        *(
            ["-filter_script:v", str(vf_filter_script)]
            if vf_filter_script
            else ["-vf", vf_filter]
        ),
        "-c:v",
        video_codec,
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-tune",
        tune,
        "-r",
        str(fps),
        "-g",
        str(gop),
        "-keyint_min",
        str(max(1, fps)),
        "-sc_threshold",
        "40",
        "-pix_fmt",
        pixel_format,
        "-color_primaries",
        color_primaries,
        "-color_trc",
        color_transfer,
        "-colorspace",
        color_space,
        "-color_range",
        color_range,
        "-c:a",
        audio_codec,
        "-b:a",
        audio_bitrate,
        "-ar",
        "48000",
        "-ac",
        "2",
        "-avoid_negative_ts",
        "make_zero",
        "-max_muxing_queue_size",
        "1024",
        "-movflags",
        movflags,
        "-shortest",
    ]
    if force_key_frames:
        command.extend(["-force_key_frames", force_key_frames])
    command.append(str(output))
    return command
