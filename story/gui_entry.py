from __future__ import annotations

import sys

from story.launcher_utils import build_missing_streamlit_message


def main() -> int:
    try:
        from story.gui.app import main as streamlit_main
    except ModuleNotFoundError as exc:
        if exc.name == "streamlit":
            print(build_missing_streamlit_message("story.gui_entry"), file=sys.stderr)
            return 1
        raise
    streamlit_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
