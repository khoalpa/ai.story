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
        from studio.prompt_library import render_prompt_library_workspace
        from studio.story_studio import (
            render_story_studio_navigation,
            render_story_studio_workspace,
        )
        from studio.ui_style import render_studio_style
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

    render_studio_style()

    st.title(app_title)

    selected = st.sidebar.radio(
        "Workspace",
        ["Overview", "Story Studio", "Audio Studio", "Video Studio", "Prompt Info"],
        key="studio_workspace",
    )
    if selected == "Story Studio":
        render_story_studio_navigation()
    renderers = {
        "Overview": render_overview,
        "Story Studio": lambda: render_story_studio_workspace(embedded=True, show_navigation=False),
        "Audio Studio": lambda: render_audio_workspace(embedded=True),
        "Video Studio": lambda: render_video_workspace(embedded=True),
        "Prompt Info": lambda: render_prompt_library_workspace(embedded=True),
    }
    renderers[selected]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
