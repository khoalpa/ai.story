from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Optional

from audio.exceptions import AudioStoryError
from audio.render_audio_app import (
    RenderAudioAppRequest,
    RenderAudioAppResult,
    create_default_app_request,
    run_render_audio_app,
)
from audio.render_batch_manifest import (
    BatchManifest,
    BatchManifestJob,
    build_request_from_manifest_job,
    load_batch_manifest,
)
from audio.render_job_repository import JobRepository
from audio.render_job_store import JobRunRecord




@dataclass(frozen=True)
class BatchManifestItemResult:
    manifest_job: BatchManifestJob
    request: RenderAudioAppRequest
    result: Optional[RenderAudioAppResult] = None
    error: Optional[Exception] = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class BatchManifestRunResult:
    items: tuple[BatchManifestItemResult, ...]

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def succeeded(self) -> int:
        return sum(1 for item in self.items if item.ok)

    @property
    def failed(self) -> int:
        return self.total - self.succeeded


@dataclass(frozen=True)
class BatchRetryPolicy:
    statuses: tuple[str, ...] = ("validation_failed",)
    limit: Optional[int] = None
    newest_first: bool = True
    require_missing_audio: bool = True


@dataclass(frozen=True)
class BatchRetryItemResult:
    source_job: JobRunRecord
    request: RenderAudioAppRequest
    result: Optional[RenderAudioAppResult] = None
    error: Optional[Exception] = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class BatchRetryRunResult:
    items: tuple[BatchRetryItemResult, ...]

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def succeeded(self) -> int:
        return sum(1 for item in self.items if item.ok)

    @property
    def failed(self) -> int:
        return self.total - self.succeeded


class RenderBatchRunner:
    def __init__(
        self,
        repository: JobRepository,
        *,
        app_runner: Callable[..., RenderAudioAppResult] = run_render_audio_app,
    ) -> None:
        self.repository = repository
        self.app_runner = app_runner

    def plan_retries(self, policy: BatchRetryPolicy | None = None) -> tuple[JobRunRecord, ...]:
        policy = policy or BatchRetryPolicy()
        query = self.repository.list_by_status(*policy.statuses, limit=policy.limit, newest_first=policy.newest_first)
        if not policy.require_missing_audio:
            return query
        return tuple(record for record in query if record.rendered_audio is None)

    def build_retry_request(
        self,
        record: JobRunRecord,
        *,
        template: RenderAudioAppRequest | None = None,
        output_dir: Optional[str] = None,
        validate_only: Optional[bool] = None,
        debug: Optional[bool] = None,
    ) -> RenderAudioAppRequest:
        if record.input_path is None or record.output_dir is None and output_dir is None:
            raise ValueError(f"Job {record.job_id} does not have enough path information to retry")

        base = template or create_default_app_request(
            input_path=record.input_path,
            output_dir=record.output_dir if record.output_dir is not None else output_dir,
        )
        target_output_dir = record.output_dir if output_dir is None else type(base.output_dir)(output_dir)
        return replace(
            base,
            input_path=record.input_path,
            output_dir=target_output_dir,
            validate_only=base.validate_only if validate_only is None else validate_only,
            debug=base.debug if debug is None else debug,
        )

    def build_manifest_request(
        self,
        job: BatchManifestJob,
        *,
        manifest_defaults: dict | None = None,
        template: RenderAudioAppRequest | None = None,
    ) -> RenderAudioAppRequest:
        return build_request_from_manifest_job(job, defaults=manifest_defaults, template=template)

    def run_manifest_job(
        self,
        job: BatchManifestJob,
        *,
        ffmpeg_exe: str,
        ffprobe_exe: str,
        manifest_defaults: dict | None = None,
        template: RenderAudioAppRequest | None = None,
        event_sink=None,
    ) -> BatchManifestItemResult:
        request = self.build_manifest_request(job, manifest_defaults=manifest_defaults, template=template)
        try:
            result = self.app_runner(
                request,
                ffmpeg_exe=ffmpeg_exe,
                ffprobe_exe=ffprobe_exe,
                event_sink=event_sink,
            )
            return BatchManifestItemResult(manifest_job=job, request=request, result=result)
        except (AudioStoryError, ValueError, OSError, RuntimeError) as exc:
            return BatchManifestItemResult(manifest_job=job, request=request, error=exc)

    def run_manifest(
        self,
        manifest: BatchManifest | str | Path,
        *,
        ffmpeg_exe: str,
        ffprobe_exe: str,
        template: RenderAudioAppRequest | None = None,
        event_sink=None,
        continue_on_error: bool = True,
    ) -> BatchManifestRunResult:
        loaded = load_batch_manifest(manifest) if isinstance(manifest, (str, Path)) else manifest
        items: list[BatchManifestItemResult] = []
        for job in loaded.jobs:
            item = self.run_manifest_job(
                job,
                ffmpeg_exe=ffmpeg_exe,
                ffprobe_exe=ffprobe_exe,
                manifest_defaults=dict(loaded.defaults),
                template=template,
                event_sink=event_sink,
            )
            items.append(item)
            if item.error is not None and not continue_on_error:
                break
        return BatchManifestRunResult(items=tuple(items))

    def retry_record(
        self,
        record: JobRunRecord,
        *,
        ffmpeg_exe: str,
        ffprobe_exe: str,
        template: RenderAudioAppRequest | None = None,
        event_sink=None,
        output_dir: Optional[str] = None,
        validate_only: Optional[bool] = None,
        debug: Optional[bool] = None,
    ) -> BatchRetryItemResult:
        request = self.build_retry_request(
            record,
            template=template,
            output_dir=output_dir,
            validate_only=validate_only,
            debug=debug,
        )
        try:
            result = self.app_runner(
                request,
                ffmpeg_exe=ffmpeg_exe,
                ffprobe_exe=ffprobe_exe,
                event_sink=event_sink,
            )
            return BatchRetryItemResult(source_job=record, request=request, result=result)
        except (AudioStoryError, ValueError, OSError, RuntimeError) as exc:
            return BatchRetryItemResult(source_job=record, request=request, error=exc)

    def run_retries(
        self,
        *,
        ffmpeg_exe: str,
        ffprobe_exe: str,
        policy: BatchRetryPolicy | None = None,
        template: RenderAudioAppRequest | None = None,
        event_sink=None,
        continue_on_error: bool = True,
        validate_only: Optional[bool] = None,
        debug: Optional[bool] = None,
    ) -> BatchRetryRunResult:
        items: list[BatchRetryItemResult] = []
        for record in self.plan_retries(policy):
            item = self.retry_record(
                record,
                ffmpeg_exe=ffmpeg_exe,
                ffprobe_exe=ffprobe_exe,
                template=template,
                event_sink=event_sink,
                validate_only=validate_only,
                debug=debug,
            )
            items.append(item)
            if item.error is not None and not continue_on_error:
                break
        return BatchRetryRunResult(items=tuple(items))
