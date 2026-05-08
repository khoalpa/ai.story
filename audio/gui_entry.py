from __future__ import annotations

import sys

from audio.env_runtime import bootstrap_vieneu_runtime
from audio.launcher_utils import build_missing_streamlit_message


def main() -> int:
    bootstrap_vieneu_runtime()
    try:
        from audio.gui.app import main as streamlit_main
    except ModuleNotFoundError as exc:
        if exc.name == "streamlit":
            print(build_missing_streamlit_message("audio.gui_entry"), file=sys.stderr)
            return 1
        raise
    streamlit_main(None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
