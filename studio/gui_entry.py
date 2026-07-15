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
        from image.app_api import render_image_workspace
        from story.app_api import render_story_workspace
        from studio.project_tools import render_project_tools_workspace
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

    app_title = "AI Story Studio"

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

        /* Expander is a Streamlit block rather than an element container, so
           it has no data-stale attribute. Hide expanders only while a rerun is
           active; the current page's expanders return as soon as it finishes. */
        body:has(
            [data-testid="stStatusWidgetRunningIcon"],
            [data-testid="stStatusWidgetRunningManIcon"]
        ) [data-testid="stExpander"] {
            display: none !important;
        }
        </style>
        """
    )

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

    st.set_page_config(page_title=app_title, page_icon=":material/movie:", layout="wide")
    st.title(app_title)
    st.caption("Unified workspace for the Story -> Audio / Image -> Video pipeline.")
    selected = st.sidebar.radio(
        "Workspace", ["Overview", "Story", "Audio", "Image", "Video", "Project Tools"]
    )
    renderers = {
        "Overview": render_overview,
        "Story": lambda: render_story_workspace(embedded=True),
        "Audio": lambda: render_audio_workspace(embedded=True),
        "Image": lambda: render_image_workspace(embedded=True),
        "Video": lambda: render_video_workspace(embedded=True),
        "Project Tools": lambda: render_project_tools_workspace(embedded=True),
    }
    renderers[selected]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
