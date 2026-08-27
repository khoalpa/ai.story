from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[1]
    project_root_text = str(project_root)
    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)

def main() -> int:
    try:
        import streamlit as st

        from audio.app_api import render_audio_workspace
        from studio.overview import render_overview
        from studio.story_studio import render_story_studio_workspace
        from video.app_api import render_video_workspace
    except ModuleNotFoundError as exc:
        if exc.name == "streamlit":
            print(
                "Streamlit is required for studio.gui_entry. "
                "Install the project GUI dependencies and try again.",
                file=sys.stderr,
            )
            return 1
        raise

    app_title = "AI Audio & Video Studio"

    st.set_page_config(page_title=app_title, page_icon=":material/movie:", layout="wide")

    # Streamlit keeps elements from the previous rerun in the DOM with the
    # ``data-stale="true"`` attribute until their replacements arrive.  That transition is
    # useful for small widget updates, but it leaves a faded copy of a taller
    # workspace visible when the user navigates to a shorter one.
    st.html(
        """
        <style>
        [data-testid="stElementContainer"][data-stale="true"] {
            display: none !important;
        }

        </style>
        """
    )

    st.title(app_title)

    selected = st.sidebar.radio(
        "Workspace",
        ["Overview", "Story Studio", "Audio Studio", "Video Studio"],
        key="studio_workspace",
    )
    renderers = {
        "Overview": render_overview,
        "Story Studio": lambda: render_story_studio_workspace(embedded=True),
        "Audio Studio": lambda: render_audio_workspace(embedded=True),
        "Video Studio": lambda: render_video_workspace(embedded=True),
    }
    renderers[selected]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
