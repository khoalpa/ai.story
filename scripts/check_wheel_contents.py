from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_MEMBERS = [
    'audio/__init__.py',
    'story/__init__.py',
    'image/__init__.py',
    'video/__init__.py',
    'studio/__init__.py',
    'audio/gui_entry.py',
    'story/gui_entry.py',
    'image/gui_entry.py',
    'video/gui_entry.py',
    'studio/gui_entry.py',
    'audio/assets/abbreviation_map.json',
    'audio/assets/bgm_config.json',
    'audio/assets/bgm/bgm_lofi.mp3',
    'audio/assets/bgm/zone_opening.mp3',
    'image/assets/workflows/comfyui_minimal_t2i_workflow.json',
    'video/assets/profiles/demo/manifest.json',
    'studio/_shared/assets/llm/lmdeploy.yml',
    'studio/_shared/assets/llm/lm_studio.yml',
    'studio/_shared/assets/llm/openai_chatgpt.yml',
    'studio/_shared/assets/llm/custom_compatible.yml',
    'studio/_shared/assets/workflows/comfyui_minimal_t2i_workflow.json',
    'studio/_shared/assets/workflows/comfyui_story_cover_9x16_hires_v2_workflow.json',
    'studio/_shared/assets/profiles/demo/manifest.json',
    'studio/_shared/assets/profiles/demo/bgm_config.json',
    'studio/_shared/assets/bgm/bgm_lofi.mp3',
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
