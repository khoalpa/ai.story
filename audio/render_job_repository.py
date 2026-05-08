from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from audio.render_job_store import JsonFileJobStore, JobRunRecord, JobStore


@dataclass(frozen=True)
class JobQuery:
    statuses: tuple[str, ...] = ()
    input_path: Optional[str] = None
    output_dir: Optional[str] = None
    has_debug_json: Optional[bool] = None
    has_rendered_audio: Optional[bool] = None
    has_rendered_subtitle: Optional[bool] = None
    limit: Optional[int] = None
    newest_first: bool = True


class JobRepository:
    def __init__(self, store: JobStore | str | Path):
        if isinstance(store, (str, Path)):
            store = JsonFileJobStore(Path(store))
        self.store = store

    def get(self, job_id: str) -> Optional[JobRunRecord]:
        return self.store.get(job_id)

    def list_runs(self) -> tuple[JobRunRecord, ...]:
        return self.store.list_runs()

    def query(self, query: JobQuery | None = None) -> tuple[JobRunRecord, ...]:
        query = query or JobQuery()
        records = list(self.store.list_runs())
        if query.newest_first:
            records.reverse()

        filtered: list[JobRunRecord] = []
        for record in records:
            if not _matches_query(record, query):
                continue
            filtered.append(record)
            if query.limit is not None and len(filtered) >= query.limit:
                break
        return tuple(filtered)

    def list_by_status(self, *statuses: str, limit: Optional[int] = None, newest_first: bool = True) -> tuple[JobRunRecord, ...]:
        return self.query(JobQuery(statuses=tuple(statuses), limit=limit, newest_first=newest_first))

    def latest_run(self, *statuses: str) -> Optional[JobRunRecord]:
        matches = self.list_by_status(*statuses, limit=1, newest_first=True) if statuses else self.query(JobQuery(limit=1))
        return matches[0] if matches else None

    def latest_completed_run(self) -> Optional[JobRunRecord]:
        return self.latest_run("completed")

    def latest_failed_validation_run(self) -> Optional[JobRunRecord]:
        return self.latest_run("validation_failed")

    def list_retry_candidates(self, limit: Optional[int] = None) -> tuple[JobRunRecord, ...]:
        return self.query(
            JobQuery(
                statuses=("validation_failed",),
                has_rendered_audio=False,
                limit=limit,
                newest_first=True,
            )
        )


def _matches_query(record: JobRunRecord, query: JobQuery) -> bool:
    if query.statuses and record.status not in query.statuses:
        return False
    if query.input_path is not None and str(record.input_path) != query.input_path:
        return False
    if query.output_dir is not None and str(record.output_dir) != query.output_dir:
        return False
    if query.has_debug_json is not None and ((record.debug_json is not None) != query.has_debug_json):
        return False
    if query.has_rendered_audio is not None and ((record.rendered_audio is not None) != query.has_rendered_audio):
        return False
    if query.has_rendered_subtitle is not None and ((record.rendered_subtitle is not None) != query.has_rendered_subtitle):
        return False
    return True
