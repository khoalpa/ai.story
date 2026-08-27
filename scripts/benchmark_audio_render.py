from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from time import perf_counter

from audio.app_config import AppConfig
from audio.profile_config import ProfileConfig
from audio.render_audio_app import run_render_audio_app
from audio.render_events import RenderEvent
from audio.render_observers import JobTelemetrySubscriber
from audio.runtime_binaries import get_ffmpeg_exe, get_ffprobe_exe


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark the complete Audio render pipeline.")
    parser.add_argument("--input", type=Path, required=True, help="Plain-script input file.")
    parser.add_argument("--output-root", type=Path, required=True, help="Root for isolated run outputs.")
    parser.add_argument("--cache-dir", type=Path, required=True, help="Isolated TTS content cache.")
    parser.add_argument("--runs", type=int, default=2, help="Number of runs; run 1 is cold and later runs are warm.")
    parser.add_argument("--no-quality-gate", action="store_true", help="Disable final quality analysis.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = args.input.resolve()
    output_root = args.output_root.resolve()
    cache_dir = args.cache_dir.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["AUDIO_TTS_CACHE_DIR"] = str(cache_dir)
    profile = ProfileConfig.from_mapping({})
    results: list[dict[str, object]] = []

    for run_number in range(1, max(1, int(args.runs)) + 1):
        output_dir = output_root / f"run_{run_number}"
        config = AppConfig.from_mapping({
            "output_dir": output_dir,
            "quality_gate": not args.no_quality_gate,
        })
        request = config.to_request(input_path, profile)
        telemetry = JobTelemetrySubscriber()
        cache_payload: dict[str, object] = {}

        def handle_event(event: RenderEvent) -> None:
            nonlocal cache_payload
            telemetry.handle_event(event)
            if event.name == "render.tts.cache.resolved":
                cache_payload = dict(event.payload)

        started = perf_counter()
        rendered = run_render_audio_app(
            request,
            ffmpeg_exe=get_ffmpeg_exe(),
            ffprobe_exe=get_ffprobe_exe(),
            event_sink=handle_event,
        )
        wall_seconds = perf_counter() - started
        artifacts = rendered.render_artifacts
        snapshot = telemetry.snapshot
        results.append({
            "run": run_number,
            "cache_state": "cold" if run_number == 1 else "warm",
            "wall_seconds": round(wall_seconds, 3),
            "phase_ms": snapshot.render_phase_durations_ms,
            "realtime_factor": snapshot.render_realtime_factor,
            "cache_hits": int(cache_payload.get("hit_count", 0)),
            "cache_misses": int(cache_payload.get("miss_count", 0)),
            "segments": len(artifacts.segments) if artifacts else 0,
            "estimated_audio_seconds": artifacts.estimated_duration_seconds if artifacts else 0.0,
            "output_audio": str(artifacts.out_file) if artifacts else None,
        })
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)

    print(json.dumps({"benchmark_results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
