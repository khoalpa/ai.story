from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from audio.cli_utils import UsedFilesTracker
from audio.render_events import (
    AppDebugSavedEvent,
    AppPathsResolvedEvent,
    AppPreviewReadyEvent,
    AppRenderCompletedEvent,
    AppResourcesLoadedEvent,
    AppRuntimeResolvedEvent,
    AppValidationCompletedEvent,
    RenderEvent,
    RenderPhaseCompletedEvent,
    RenderPhaseStartedEvent,
)
from audio.render_job import RenderJobArtifacts, RuntimeContext


@dataclass
class RenderReporter:
    used_files: UsedFilesTracker = field(default_factory=UsedFilesTracker)

    def handle_event(self, event: RenderEvent) -> None:
        if isinstance(event, AppPathsResolvedEvent) or event.name == "app.paths.resolved":
            self.note_input_output(event.payload["input_path"], event.payload["output_dir"])
            return

        if isinstance(event, AppRuntimeResolvedEvent) or event.name == "app.runtime.resolved":
            self.note_runtime_context(event.payload["request"], event.payload["runtime_ctx"])
            return

        if isinstance(event, AppResourcesLoadedEvent) or event.name == "app.resources.loaded":
            abbr_map_path = event.payload["abbr_map_path"]
            abbr_map = event.payload["abbr_map"]
            self.note_abbreviation_map(abbr_map_path)
            self.note_bgm_config(
                cli_bgm_config=event.payload.get("cli_bgm_config"),
                profile_bgm_config=event.payload.get("profile_bgm_config"),
            )
            self.print_abbreviation_status(abbr_map_path, abbr_map)
            return

        if isinstance(event, AppValidationCompletedEvent) or event.name == "app.validation.completed":
            self.report_validation_result(
                event.payload["input_path"],
                event.payload["exit_code"],
                tuple(event.payload["errors"]),
                int(event.payload["warnings_count"]),
            )
            return

        if isinstance(event, AppPreviewReadyEvent) or event.name == "app.preview.ready":
            self.print_preview_summary(
                event.payload["preview"],
                sentiment_tone=bool(event.payload.get("sentiment_tone", False)),
            )
            return

        if isinstance(event, AppDebugSavedEvent) or event.name == "app.debug.saved":
            self.report_debug_output(event.payload["debug_json"])
            return

        if isinstance(event, AppRenderCompletedEvent) or event.name == "app.render.completed":
            self.report_render_success(event.payload["render_artifacts"])
            return

        if isinstance(event, RenderPhaseStartedEvent) or event.name == "render.phase.started":
            self.report_phase_started(event.payload["phase"])
            return

        if isinstance(event, RenderPhaseCompletedEvent) or event.name == "render.phase.completed":
            self.report_phase_completed(event.payload["phase"])
            return

    def note_input_output(self, input_path: Path, out_dir: Path) -> None:
        self.used_files.add("Input plain script", input_path)
        self.used_files.add("Output directory", out_dir)
        print(f"[PATH] Output directory: {out_dir}")

    def note_runtime_context(self, args, runtime_ctx: RuntimeContext) -> None:
        if getattr(args, "asset_profile", None):
            self.used_files.note("Asset profile", args.asset_profile)
        if runtime_ctx.profile_dir is not None:
            self.used_files.add("Resolved profile directory", runtime_ctx.profile_dir)
        self.used_files.add("Resolved BGM directory", runtime_ctx.bgm_dir)

    def note_abbreviation_map(self, path: Path) -> None:
        self.used_files.add("Abbreviation map", path)

    def note_bgm_config(self, *, cli_bgm_config: Optional[Path], profile_bgm_config: Optional[Path]) -> None:
        if cli_bgm_config is not None:
            self.used_files.add("CLI BGM config", cli_bgm_config)
        elif profile_bgm_config is not None:
            self.used_files.add("Profile BGM config", profile_bgm_config)

    def report_validation_result(self, input_path: Path, exit_code: int, errors: tuple[str, ...], warnings_count: int) -> None:
        if exit_code == 0:
            print(f"[OK] Validation passed: {input_path}")
            print(f"Errors: 0 | Warnings: {warnings_count}")
            return

        print(f"[ERROR] Validation failed: {input_path}")
        for issue in errors[:20]:
            print(f"- {issue}")
        if len(errors) > 20:
            print(f"... and {len(errors) - 20} more errors")

    def print_abbreviation_status(self, abbr_map_path: Path, abbr_map: dict[str, str]) -> None:
        if abbr_map:
            print(f"Loaded {len(abbr_map)} abbreviations from {abbr_map_path}")
        else:
            print(f"abbreviation_map not found or empty at {abbr_map_path}; skipping mapping.")

    def print_preview_summary(self, preview: RenderJobArtifacts, *, sentiment_tone: bool) -> None:
        print(f"Total segments after parsing: {len(preview.segments)}")
        if sentiment_tone:
            print("Analyzing sentiment and adjusting speaking tone/speed...")
        print(f"Estimated audio duration after mixing: ~{preview.estimated_duration_hms} (rough estimate).")

    def report_debug_output(self, debug_json: Path) -> None:
        print(f"Saved debug segments to: {debug_json}")
        self.used_files.add("Debug segments JSON", debug_json)

    def report_phase_started(self, phase: str) -> None:
        print(f"[RUN] {phase} phase started")

    def report_phase_completed(self, phase: str) -> None:
        print(f"[OK] {phase} phase completed")

    def report_render_success(self, artifacts: RenderJobArtifacts) -> None:
        self.used_files.add("Intermediate WAV directory", artifacts.wav_dir)
        print(f"[PATH] Intermediate WAV directory: {artifacts.wav_dir}")
        print(f"[PATH] Final audio file: {artifacts.out_file}")
        print(f"[PATH] Subtitle file: {artifacts.srt_path}")
        print(f"[OK] Created audio file: {artifacts.out_file}")
        self.used_files.add("Rendered audio", artifacts.out_file)
        print(f"[OK] Created subtitle file: {artifacts.srt_path}")
        self.used_files.add("Rendered subtitle", artifacts.srt_path)


    def report_batch_summary(self, manifest_path: str | Path, *, total: int, succeeded: int, failed: int) -> None:
        manifest_path = Path(manifest_path)
        self.used_files.add("Batch manifest", manifest_path)
        print(f"[BATCH] Manifest: {manifest_path}")
        print(f"[BATCH] Total jobs: {total} | Succeeded: {succeeded} | Failed: {failed}")

    def print_used_files_summary(self) -> None:
        self.used_files.print_summary()
