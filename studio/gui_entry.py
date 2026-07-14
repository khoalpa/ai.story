from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[1]
    project_root_text = str(project_root)
    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)

from studio._shared.launcher_utils import build_missing_streamlit_message


def main() -> int:
    try:
        import streamlit as st
        from studio._shared.gui import render_project_tools_workspace, render_workspace_shell
        from audio.gui.app import render_audio_workspace
        from image.gui.app import render_image_workspace
        from story.gui.app import render_story_workspace
        from video.gui.app import render_video_workspace
    except ModuleNotFoundError as exc:
        if exc.name == "streamlit":
            print(build_missing_streamlit_message("studio.gui_entry"), file=sys.stderr)
            return 1
        raise

    app_title = "AI Story Studio"

    def render_overview() -> None:
        st.subheader("Recommended workflow")
        st.markdown(
            """
            - Open **Story** to create the plain script and image handoff bundle.
            - Switch to **Audio** to render narration and subtitles.
            - Switch to **Image** to render cover/scenes from the prompt bundle.
            - Switch to **Video** to combine audio and images into an MP4.
            - Track handoff status in the sidebar to see the latest output from each step.
            """
        )

        st.subheader("Unified workspace")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.info("""**1. Story**

Create brief -> canonical -> plain script + prompts.""")
        with col2:
            st.info("""**2. Audio**

Render plain script -> WAV/MP3 + subtitle.""")
        with col3:
            st.info("""**3. Image**

Render Story handoff -> cover/scenes.""")
        with col4:
            st.info("""**4. Video**

Render audio/subtitle + cover/scenes -> MP4.""")

    render_workspace_shell(
        title=app_title,
        caption="Unified workspace for the Story -> Audio / Image -> Video pipeline in one interface.",
        overview_renderer=render_overview,
        app_renderers={
            "Story": lambda: render_story_workspace(embedded=True),
            "Audio": lambda: render_audio_workspace(embedded=True),
            "Image": lambda: render_image_workspace(embedded=True),
            "Video": lambda: render_video_workspace(embedded=True),
            "Project Tools": lambda: render_project_tools_workspace(embedded=True),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
