from __future__ import annotations

import sys

from common.launcher_utils import build_missing_streamlit_message


def main() -> int:
    try:
        from image.gui.app import main as image_main
    except ModuleNotFoundError as exc:
        if exc.name == "streamlit":
            print(build_missing_streamlit_message("image.gui_entry"), file=sys.stderr)
            return 1
        raise
    return int(image_main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())

