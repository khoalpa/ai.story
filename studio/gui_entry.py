from __future__ import annotations

import hashlib
import os
import sys
import tempfile
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

    from studio.prompt_contract import (
        PROMPT_FILE_ENV,
        PROMPT_FILENAME,
        canonical_prompt_path,
        load_prompt_contract,
    )

    selected_prompt = str(st.session_state.get("studio_prompt_file") or "").strip()
    if selected_prompt:
        os.environ[PROMPT_FILE_ENV] = selected_prompt

    try:
        active_prompt = canonical_prompt_path()
        load_prompt_contract(active_prompt)
    except (FileNotFoundError, OSError, UnicodeError, ValueError) as exc:
        os.environ.pop(PROMPT_FILE_ENV, None)
        st.warning("Không tìm thấy hoặc không thể đọc prompt chuẩn của dự án.")
        st.caption(str(exc))
        st.markdown("Chọn một tệp `ChatGPT_prompt_vX.Y.Z.txt` để tiếp tục.")

        prompt_path = st.text_input(
            "Đường dẫn tệp prompt",
            key="studio_prompt_path_input",
            placeholder=r"D:\prompts\ChatGPT_prompt_v3.11.14.txt",
        )
        uploaded_prompt = st.file_uploader(
            "Hoặc tải tệp prompt lên",
            type=["txt"],
            key="studio_prompt_upload",
        )

        candidate: Path | None = None
        if uploaded_prompt is not None:
            if not PROMPT_FILENAME.match(uploaded_prompt.name):
                st.error("Tên tệp phải có dạng ChatGPT_prompt_vX.Y.Z.txt (có thể có tiền tố số).")
            else:
                raw = uploaded_prompt.getvalue()
                digest = hashlib.sha256(raw).hexdigest()
                upload_dir = Path(tempfile.gettempdir()) / "ai-story-prompts" / digest
                upload_dir.mkdir(parents=True, exist_ok=True)
                candidate = upload_dir / uploaded_prompt.name
                if not candidate.is_file() or candidate.read_bytes() != raw:
                    candidate.write_bytes(raw)
        elif prompt_path.strip():
            candidate = Path(prompt_path.strip().strip('"')).expanduser()

        if candidate is not None and st.button("Dùng tệp prompt này", type="primary"):
            try:
                resolved = candidate.resolve()
                load_prompt_contract(resolved)
            except (FileNotFoundError, OSError, UnicodeError, ValueError) as select_exc:
                st.error(f"Không thể dùng tệp đã chọn: {select_exc}")
            else:
                st.session_state["studio_prompt_file"] = str(resolved)
                os.environ[PROMPT_FILE_ENV] = str(resolved)
                st.rerun()
        return 0

    st.sidebar.caption(f"Prompt · `{active_prompt.name}`")

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
    # Give each top-level workspace a stable delta-tree slot. This prevents
    # expanders/dataframes from the previous workspace surviving navigation.
    workspace_slots = {name: st.empty() for name in renderers}
    with workspace_slots[selected].container():
        renderers[selected]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
