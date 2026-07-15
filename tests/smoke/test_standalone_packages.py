from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ("story", "audio", "image", "video")


def test_retired_shared_packages_are_absent() -> None:
    assert not (ROOT / "common").exists()
    assert not (ROOT / "studio" / "_shared").exists()


def test_each_app_api_imports_from_a_neutral_working_directory() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    with tempfile.TemporaryDirectory() as temp_dir:
        for package in PACKAGES:
            probe = subprocess.run(
                [sys.executable, "-c", f"import {package}.app_api"],
                cwd=temp_dir,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            assert probe.returncode == 0, f"{package}: {probe.stderr}"


def test_package_main_modules_import_without_sibling_packages() -> None:
    for package in PACKAGES:
        source = (ROOT / package / "__main__.py").read_text(encoding="utf-8")
        for sibling in PACKAGES:
            if sibling != package:
                assert f"from {sibling}" not in source
                assert f"import {sibling}" not in source
