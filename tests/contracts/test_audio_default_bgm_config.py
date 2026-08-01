from __future__ import annotations

from audio.bgm_config_utils import load_bgm_runtime_config
from audio.paths import ASSETS_ROOT


def test_default_bgm_config_is_valid() -> None:
    config = load_bgm_runtime_config(ASSETS_ROOT / "bgm_config.json")

    assert config is not None
    assert config.intro_clip is not None
    assert config.intro_clip["gain_db"] == 12
