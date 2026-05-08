from __future__ import annotations

import streamlit as st

from audio.render_job_repository import JobQuery, JobRepository
from audio.gui.user_messages import show_empty_result


def render_run_history(repository: JobRepository) -> None:
    st.subheader("Job history")
    query = JobQuery(limit=50, newest_first=True)
    rows = []
    for record in repository.query(query):
        rows.append(
            {
                "job_id": record.job_id,
                "status": record.status,
                "input": str(record.input_path) if record.input_path else "",
                "output": str(record.output_dir) if record.output_dir else "",
                "events": record.total_events,
                "rendered_audio": str(record.rendered_audio) if record.rendered_audio else "",
                "rendered_subtitle": str(record.rendered_subtitle) if record.rendered_subtitle else "",
                "validation_exit_code": record.validation_exit_code,
                "warnings": record.validation_warnings_count,
            }
        )
    if not rows:
        show_empty_result(
            "audio job history",
            actions=["Run an Audio job to create history entries.", "Return to this tab after new results are available."],
        )
        return
    st.dataframe(rows, width="stretch", height=360)

    retry_candidates = repository.list_retry_candidates(limit=20)
    if retry_candidates:
        st.caption(f"There are {len(retry_candidates)} job(s) available for retry.")
