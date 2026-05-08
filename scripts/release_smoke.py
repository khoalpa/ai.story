from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINTS = [
    ("generator-story", "help"),
    ("generator-story-gui", "missing-streamlit"),
    ("render-audio", "help"),
    ("render-audio-gui", "missing-streamlit"),
    ("render-image-gui", "missing-streamlit"),
    ("render-video", "help"),
    ("render-video-gui", "missing-streamlit"),
    ("ai-studio-gui", "missing-streamlit"),
]


@dataclass
class StepResult:
    name: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


class SmokeFailure(RuntimeError):
    pass


DEFAULT_TIMEOUT_SECONDS = 120


def offline_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    env.setdefault("PIP_NO_INPUT", "1")
    env.setdefault("PIP_DEFAULT_TIMEOUT", "15")
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if overrides:
        env.update(overrides)
    return env


def run(
    cmd: Sequence[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    expect: int | None = 0,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> StepResult:
    proc = subprocess.run(
        list(cmd),
        cwd=str(cwd) if cwd else None,
        env=offline_env(env),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
    )
    result = StepResult(
        name=Path(cmd[0]).name,
        command=list(cmd),
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
    if expect is not None and proc.returncode != expect:
        raise SmokeFailure(
            f"Command failed with exit code {proc.returncode} (expected {expect}): {' '.join(cmd)}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return result


def build_wheel() -> Path:
    dist_dir = ROOT / "dist"
    build_dir = ROOT / "build"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    if build_dir.exists():
        shutil.rmtree(build_dir)
    run([sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "--no-build-isolation", "-w", "dist"], cwd=ROOT)
    wheels = sorted(dist_dir.glob("*.whl"))
    if not wheels:
        raise SmokeFailure(f"No wheel built in {dist_dir}")
    return wheels[-1]


def venv_paths(venv_dir: Path) -> tuple[Path, Path]:
    if sys.platform.startswith("win"):
        bindir = venv_dir / "Scripts"
    else:
        bindir = venv_dir / "bin"
    return bindir / ("python.exe" if sys.platform.startswith("win") else "python"), bindir


def assert_help(cmd_path: Path, name: str, *, cwd: Path | None = None) -> None:
    result = run([str(cmd_path), "--help"], expect=0, cwd=cwd)
    merged = (result.stdout + "\n" + result.stderr).lower()
    if "usage" not in merged and name not in merged:
        raise SmokeFailure(f"Help output for {name} does not look valid.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")


def assert_missing_streamlit(cmd_path: Path, name: str, *, cwd: Path | None = None) -> None:
    result = run([str(cmd_path)], expect=1, cwd=cwd)
    merged = (result.stdout + "\n" + result.stderr).lower()
    if "streamlit" not in merged and "missing dependency" not in merged:
        raise SmokeFailure(
            f"GUI launcher for {name} did not fail with expected missing-streamlit message.\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )


def assert_installed_story_assets(vpy: Path, *, cwd: Path | None = None) -> None:
    probe = """
from __future__ import annotations
import json
from story.paths import resolve_assets_root
assets_root = resolve_assets_root()
result = {
    "assets_root": str(assets_root),
    "exists": assets_root.exists(),
    "is_dir": assets_root.is_dir(),
    "provider_modules": (assets_root / "llm" / "lmdeploy.yml").exists(),
    "modes": (assets_root / "modes" / "trong_sinh_brief.yml").exists()
    and (assets_root / "modes" / "trong_sinh_prompt.txt").exists(),
}
print(json.dumps(result))
""".strip()
    result = run([str(vpy), "-c", probe], expect=0, cwd=cwd)
    payload = json.loads(result.stdout.strip())
    if not payload["exists"] or not payload["is_dir"]:
        raise SmokeFailure(f"resolve_assets_root() did not return an existing directory: {payload}")
    if not payload["provider_modules"] or not payload["modes"]:
        raise SmokeFailure(f"Installed wheel assets are incomplete: {payload}")
    print(f"[installed-wheel] story.paths.resolve_assets_root() OK -> {payload['assets_root']}")


def main() -> int:
    print("== Release smoke check ==")
    print(f"Workspace: {ROOT}")
    wheel = build_wheel()
    print(f"Built wheel: {wheel.name}")
    with tempfile.TemporaryDirectory(prefix="smoke-ai-studio-") as tmp:
        tmpdir = Path(tmp)
        venv_dir = tmpdir / "venv"
        run([sys.executable, "-m", "venv", str(venv_dir)])
        vpy, bindir = venv_paths(venv_dir)
        run([str(vpy), "-m", "pip", "install", "--no-deps", str(wheel)], timeout=180, cwd=tmpdir)
        installed = run([str(vpy), "-m", "pip", "show", "ai-studio"], expect=0, cwd=tmpdir)
        if wheel.stem.split("-")[0] not in installed.stdout.lower() and "name: ai-studio" not in installed.stdout.lower():
            raise SmokeFailure(f"Installed wheel metadata not found after install.\nSTDOUT:\n{installed.stdout}\nSTDERR:\n{installed.stderr}")
        print("[installed-wheel] pip show ai-studio OK")
        assert_installed_story_assets(vpy, cwd=tmpdir)

        for entrypoint, mode in ENTRYPOINTS:
            cmd_path = bindir / (entrypoint + (".exe" if sys.platform.startswith("win") else ""))
            if not cmd_path.exists():
                raise SmokeFailure(f"Missing console script: {cmd_path}")
            if mode == "help":
                assert_help(cmd_path, entrypoint, cwd=tmpdir)
                print(f"[{entrypoint}] --help OK")
            elif mode == "missing-streamlit":
                assert_missing_streamlit(cmd_path, entrypoint, cwd=tmpdir)
                print(f"[{entrypoint}] missing-streamlit path OK")
            else:
                raise SmokeFailure(f"Unknown smoke mode: {mode}")
    print("\nSmoke check completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
