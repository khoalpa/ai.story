"""Check the launcher interpreter against this checkout's declared requirements."""
from __future__ import annotations

import importlib.metadata
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def meets_requirement(version: str, requirement: str) -> bool:
    """Evaluate the numeric version bounds used by this project's launcher."""
    if not re.fullmatch(r"\d+(?:\.\d+)*", version):
        return False
    current = tuple(int(part) for part in version.split("."))
    for bound in requirement.split(","):
        match = re.fullmatch(r"\s*(>=|<=|==|!=|>|<)\s*(\d+(?:\.\d+)*)\s*", bound)
        if match is None:
            raise ValueError(f"Unsupported version requirement: {requirement}")
        operator, raw = match.groups()
        target = tuple(int(part) for part in raw.split("."))
        width = max(len(current), len(target))
        left, right = current + (0,) * (width - len(current)), target + (0,) * (width - len(target))
        if not {">=": left >= right, "<=": left <= right, "==": left == right,
                "!=": left != right, ">": left > right, "<": left < right}[operator]:
            return False
    return True


def runtime_requirements(root: Path = ROOT) -> tuple[str, str]:
    # Read just these two simple strings without requiring tomllib on Python 3.10
    # or importing a GUI dependency before checking whether it is installed.
    source = (root / "pyproject.toml").read_text(encoding="utf-8")
    python = re.search(r'^requires-python\s*=\s*"([^"]+)"', source, re.MULTILINE)
    streamlit = re.search(r'^\s*"streamlit([^"\s]+)"', source, re.MULTILINE)
    if python is None or streamlit is None:
        raise ValueError("Cannot read Python/Streamlit requirements from pyproject.toml.")
    return python.group(1), streamlit.group(1)


def main() -> int:
    try:
        python_requirement, streamlit_requirement = runtime_requirements()
        python_version = ".".join(str(part) for part in sys.version_info[:3])
        if not meets_requirement(python_version, python_requirement):
            print(f"Python {python_version} is unsupported. This project requires Python {python_requirement}.")
            print("Select a supported Python interpreter before opening the application.")
            return 1
        try:
            version = importlib.metadata.version("streamlit")
        except importlib.metadata.PackageNotFoundError:
            version = "not installed"
        if not meets_requirement(version, streamlit_requirement):
            print(f"Streamlit is {version}. This project requires streamlit{streamlit_requirement}.")
            print(f'Run: "{sys.executable}" -m pip install -r "{ROOT / "requirements.txt"}"')
            return 1
    except (OSError, ValueError) as exc:
        print(f"Cannot check the application runtime: {exc}")
        return 1
    print(f"Runtime OK: Python {python_version}, Streamlit {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
