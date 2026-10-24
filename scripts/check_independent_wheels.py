from __future__ import annotations

import os
import subprocess
import sys
import sysconfig
import tempfile
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("audio", "video")
REQUIRED_SCHEMA = {
    "audio": "audio/assets/schemas/audio-video-handoff-v1.schema.json",
    "video": None,
}

INTEGRATED_GUI_PROBE = r'''
import importlib
import sys
from pathlib import Path

# Reuse third-party dependencies, after the newly installed application packages.
sys.path.append(sys.argv[1])
from streamlit.testing.v1 import AppTest
import audio.app_api
import video.app_api
import studio.video_prompt_projection
from studio.prompt_contract import load_prompt_contract
from studio.themes.python_theme import config, values

prefix = Path(sys.prefix).resolve()
for package in ("audio", "video", "studio"):
    module = importlib.import_module(package)
    assert Path(module.__file__).resolve().is_relative_to(prefix), module.__file__
contract = load_prompt_contract()
assert contract.version_label == "4.1.6"
assert contract.path.resolve().is_relative_to(prefix), contract.path
assert values(config())
for launcher in ("audio.gui_entry", "video.gui_entry", "studio.gui_entry"):
    app = AppTest.from_string(f"from {launcher} import main\nmain()\n", default_timeout=60)
    app.session_state["tts_provider"] = "edge_tts"
    app.run()
    assert not app.exception, (launcher, [item.message for item in app.exception])
    assert any(widget.key == "ai_theme_theme" for widget in app.selectbox), launcher
'''


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(command, cwd=cwd, env=env, text=True, encoding="utf-8", errors="replace",
                            capture_output=True, check=False, timeout=240)
    if result.returncode:
        raise RuntimeError(f"Command failed: {' '.join(command)}\n{result.stdout}\n{result.stderr}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ai-package-matrix-") as raw_temp:
        temp = Path(raw_temp)
        dist = temp / "dist"
        dist.mkdir()
        for package in PACKAGES:
            run(
                [sys.executable, "-m", "pip", "wheel", str(ROOT / "packages" / package),
                 "--no-deps", "--no-build-isolation", "-w", str(dist)],
                cwd=temp,
            )
            wheel = next(dist.glob(f"ai_{package}-*.whl"))
            with zipfile.ZipFile(wheel) as archive:
                members = set(archive.namelist())
            required_schema = REQUIRED_SCHEMA[package]
            if required_schema and required_schema not in members:
                raise RuntimeError(f"{wheel.name} is missing {required_schema}")
            for sibling in PACKAGES:
                if sibling != package and any(name.startswith(f"{sibling}/") for name in members):
                    raise RuntimeError(f"{wheel.name} unexpectedly contains sibling package {sibling}")
            env_dir = temp / f"venv-{package}"
            venv.EnvBuilder(with_pip=True, system_site_packages=True).create(env_dir)
            python = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            run([str(python), "-m", "pip", "install", "--no-deps", str(wheel)], cwd=temp)
            siblings = [name for name in PACKAGES if name != package]
            probe = (
                "import importlib.util; "
                f"import {package}.app_api; "
                f"assert all(importlib.util.find_spec(name) is None for name in {siblings!r})"
            )
            clean_env = os.environ.copy()
            clean_env.pop("PYTHONPATH", None)
            run([str(python), "-c", probe], cwd=temp, env=clean_env)
            print(f"Independent wheel OK: {package}")

        run(
            [sys.executable, "-m", "pip", "wheel", str(ROOT / "packages" / "studio"),
             "--no-deps", "--no-build-isolation", "-w", str(dist)],
            cwd=temp,
        )
        integration_env = temp / "venv-studio"
        venv.EnvBuilder(with_pip=True).create(integration_env)
        integration_python = integration_env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        wheels = [str(next(dist.glob(f"ai_{name}-*.whl"))) for name in PACKAGES]
        wheels.append(str(next(dist.glob("ai_studio_shell-*.whl"))))
        run([str(integration_python), "-m", "pip", "install", "--no-deps", *wheels], cwd=temp)
        clean_env = os.environ.copy()
        clean_env.pop("PYTHONPATH", None)
        clean_env.pop("AI_STUDIO_PROMPT_FILE", None)
        clean_env.pop("AI_STUDIO_PROMPTS_DIR", None)
        run([str(integration_python), "-c", INTEGRATED_GUI_PROBE, sysconfig.get_path("purelib")],
            cwd=temp, env=clean_env)
        print("Integrated Studio wheel set OK")
        print("Installed Audio, Video and Studio launchers, themes and bundled prompt OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
