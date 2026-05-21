from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_wheel_contents_checker_covers_packages_assets_and_launchers() -> None:
    content = (ROOT / 'scripts' / 'check_wheel_contents.py').read_text(encoding='utf-8')
    assert "'image/__init__.py'" in content
    assert "'studio/__init__.py'" in content
    assert "'audio/assets/abbreviation_map.json'" in content
    assert "'audio/assets/bgm_config.json'" in content
    assert "'audio/assets/bgm/bgm_lofi.mp3'" in content
    assert "'audio/assets/bgm/zone_opening.mp3'" in content
    assert "'image/assets/workflows/comfyui_minimal_t2i_workflow.json'" in content
    assert "'studio/_shared/assets/llm/lmdeploy.yml'" in content
    assert "'studio/_shared/assets/profiles/demo/manifest.json'" in content
    assert "'studio/_shared/assets/bgm/bgm_lofi.mp3'" in content
    assert "'studio/gui_entry.py'" in content

