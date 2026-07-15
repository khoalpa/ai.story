from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("story", "audio", "image", "video")
REQUIRED_SCHEMA = {
    "story": "story/assets/schemas/story-audio-handoff-v1.schema.json",
    "audio": "audio/assets/schemas/audio-video-handoff-v1.schema.json",
    "image": "image/assets/schemas/image-video-handoff-v1.schema.json",
    "video": None,
}


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=False)
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
        venv.EnvBuilder(with_pip=True, system_site_packages=True).create(integration_env)
        integration_python = integration_env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        wheels = [str(next(dist.glob(f"ai_{name}-*.whl"))) for name in PACKAGES]
        wheels.append(str(next(dist.glob("ai_studio_shell-*.whl"))))
        run([str(integration_python), "-m", "pip", "install", "--no-deps", *wheels], cwd=temp)
        clean_env = os.environ.copy()
        clean_env.pop("PYTHONPATH", None)
        run(
            [str(integration_python), "-c", "import studio.gui_entry; import story.app_api, audio.app_api, image.app_api, video.app_api"],
            cwd=temp,
            env=clean_env,
        )
        print("Integrated Studio wheel set OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
