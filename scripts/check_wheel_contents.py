from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_MEMBERS = [
    'audio/__init__.py',
    'video/__init__.py',
    'studio/__init__.py',
    'audio/gui_entry.py',
    'video/gui_entry.py',
    'studio/gui_entry.py',
    'studio/video_prompt_projection.py',
    'studio/video_prompt_adapters/registry.py',
    'audio/assets/abbreviation_map.json',
    'audio/assets/bgm_config.json',
    'audio/assets/bgm/bgm_lofi.mp3',
    'audio/assets/bgm/zone_opening.mp3',
]


def build_wheel() -> Path:
    dist_dir = ROOT / 'dist'
    build_dir = ROOT / 'build'
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    if build_dir.exists():
        shutil.rmtree(build_dir)
    subprocess.run([sys.executable, '-m', 'pip', 'wheel', '.', '--no-deps', '--no-build-isolation', '-w', 'dist'], cwd=ROOT, check=True)
    wheels = sorted(dist_dir.glob('*.whl'))
    if not wheels:
        raise SystemExit('No wheel was built.')
    return wheels[-1]


def main() -> int:
    wheel = build_wheel()
    with zipfile.ZipFile(wheel) as zf:
        members = set(zf.namelist())
    missing = [member for member in REQUIRED_MEMBERS if member not in members]
    if missing:
        raise SystemExit('Wheel is missing required files:\n' + '\n'.join(missing))
    print(f'Wheel content check OK: {wheel.name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
