from __future__ import annotations

import tempfile
from dataclasses import asdict
from pathlib import Path

import streamlit as st

from audio.render_batch_manifest import BatchManifestError, load_batch_manifest
from audio.render_batch_runner import RenderBatchRunner
from audio.render_job_repository import JobRepository

from .helpers import make_request, save_uploaded_text
from audio.gui.user_messages import UserMessage, render_user_message, show_empty_result, show_missing_input


def _guess_manifest_suffix(text: str) -> str:
    stripped = (text or "").lstrip()
    if (
        stripped.startswith("defaults:")
        or stripped.startswith("jobs:")
        or "\n-" in stripped
        or stripped.startswith("-")
    ):
        return ".yaml"
    return ".json"


def _build_temp_manifest(text: str) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    tmp = tempfile.TemporaryDirectory(prefix="render_audio_manifest_")
    path = Path(tmp.name) / f"manifest{_guess_manifest_suffix(text)}"
    path.write_text(text, encoding="utf-8")
    return tmp, path


def _build_current_settings_template(settings: dict):
    output_dir = Path(str(settings.get("output_dir") or "__batch_out__"))
    return make_request(input_path=Path("__batch__.txt"), output_dir=output_dir, settings=settings)


def render_batch_tab(settings: dict, repository: JobRepository) -> None:
    batch_tab1, batch_tab2 = st.tabs(["Run manifest", "Retry history"])

    with batch_tab1:
        uploaded_manifest = st.file_uploader(
            "Upload batch manifest (.json/.yml/.yaml)",
            type=["json", "yml", "yaml"],
            key="batch_manifest_upload",
        )

        uploaded_text = ""
        if uploaded_manifest is not None:
            uploaded_text = save_uploaded_text(uploaded_manifest)

        current_text = st.session_state.get("batch_manifest_text", "")
        if uploaded_text and uploaded_text != current_text:
            st.session_state["batch_manifest_text"] = uploaded_text
            current_text = uploaded_text

        manifest_text = st.text_area(
            "Batch manifest",
            value=current_text,
            height=260,
            key="batch_manifest_editor",
            help="Paste JSON or YAML manifest content here, or upload a file above.",
        )

        if manifest_text != st.session_state.get("batch_manifest_text", ""):
            st.session_state["batch_manifest_text"] = manifest_text

        continue_on_error = st.checkbox(
            "Continue on batch error",
            value=True,
            key="batch_continue_on_error",
            help="Continue running later manifest jobs after one job fails.",
        )
        use_current_settings_template = st.checkbox(
            "Use current sidebar settings as manifest defaults",
            value=True,
            key="batch_use_current_settings_template",
            help="Apply the current provider, voices, BGM, format, and render options unless the manifest overrides them.",
        )

        col1, col2 = st.columns(2)

        with col1:
            analyze_clicked = st.button("Analyze manifest", width="stretch")

        with col2:
            run_clicked = st.button("Run batch", type="primary", width="stretch")

        if analyze_clicked:
            text = (st.session_state.get("batch_manifest_text") or "").strip()
            if not text:
                show_missing_input(
                    "batch manifest",
                    hint="Paste JSON/YAML content or upload a manifest file before analyzing.",
                    actions=["Check the Batch manifest area above.", "Try Analyze manifest again after content is available."],
                )
            else:
                tmp_dir = None
                try:
                    tmp_dir, path = _build_temp_manifest(text)
                    manifest = load_batch_manifest(path)
                    st.success("Manifest is valid.")
                    st.json(asdict(manifest))
                    if use_current_settings_template:
                        template = _build_current_settings_template(settings)
                        st.caption("Current sidebar settings will be used as the batch template.")
                        st.json(template.to_payload(serialize_paths=True))
                except BatchManifestError as exc:
                    render_user_message(
                        UserMessage(
                            level="error",
                            title="Invalid manifest",
                            body="Could not analyze the current batch manifest. Open details to inspect syntax or schema issues.",
                            technical_details=str(exc),
                        ),
                        show_details=True,
                    )
                except Exception as exc:
                    render_user_message(
                        UserMessage(
                            level="error",
                            title="Manifest analysis failed",
                            body="An unexpected error occurred while reading the batch manifest.",
                            technical_details=str(exc),
                        ),
                        show_details=True,
                    )
                finally:
                    if tmp_dir is not None:
                        tmp_dir.cleanup()

        if run_clicked:
            text = (st.session_state.get("batch_manifest_text") or "").strip()
            if not text:
                show_missing_input(
                    "batch manifest",
                    hint="Prepare a valid manifest before running the batch job.",
                    actions=["Analyze the manifest first to inspect it again.", "Run the batch again after the manifest is valid."],
                )
            else:
                tmp_dir = None
                try:
                    tmp_dir, path = _build_temp_manifest(text)
                    runner = RenderBatchRunner(repository=repository)
                    template = _build_current_settings_template(settings) if use_current_settings_template else None
                    result = runner.run_manifest(
                        path,
                        ffmpeg_exe=str(settings.get("ffmpeg_exe") or ""),
                        ffprobe_exe=str(settings.get("ffprobe_exe") or ""),
                        template=template,
                        continue_on_error=bool(continue_on_error),
                    )
                    st.success(
                        f"Processed batch: total={result.total}, "
                        f"success={result.succeeded}, failed={result.failed}"
                    )
                except BatchManifestError as exc:
                    render_user_message(
                        UserMessage(
                            level="error",
                            title="Invalid manifest",
                            body="Could not analyze the current batch manifest. Open details to inspect syntax or schema issues.",
                            technical_details=str(exc),
                        ),
                        show_details=True,
                    )
                except Exception as exc:
                    render_user_message(
                        UserMessage(
                            level="error",
                            title="Batch run failed",
                            body="The batch runner could not complete the current request.",
                            technical_details=str(exc),
                        ),
                        show_details=True,
                    )
                finally:
                    if tmp_dir is not None:
                        tmp_dir.cleanup()

    with batch_tab2:
        st.caption("Retry history")
        try:
            history = repository.list_jobs(limit=50)
        except Exception as exc:
            render_user_message(
                UserMessage(
                    level="error",
                    title="Could not load job history",
                    body="Could not read retry history from the current job repository.",
                    technical_details=str(exc),
                ),
                show_details=True,
            )
            history = []

        if not history:
            show_empty_result(
                "batch retry history",
                actions=["Run at least one batch to create retry history.", "Return to this tab after new jobs exist."],
            )
        else:
            for job in history:
                with st.expander(f"{getattr(job, 'job_id', 'unknown')}"):
                    try:
                        st.json(asdict(job))
                    except Exception:
                        st.write(job)
