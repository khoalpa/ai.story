from __future__ import annotations

from audio.bgm_config_schema import normalize_env_key
from audio.bgm_config_utils import load_bgm_runtime_config
from audio.paths import ASSETS_ROOT
from studio.story_environments import CANONICAL_STORY_ENVIRONMENT_SET


def test_default_bgm_config_is_valid() -> None:
    config = load_bgm_runtime_config(ASSETS_ROOT / "bgm_config.json")

    assert config is not None
    assert config.intro_clip is not None
    assert config.intro_clip["gain_db"] == 12
    assert "cafe_soft" in config.env_ambience_map
    assert "rain_soft" in config.env_ambience_map
    assert "cafe" not in config.env_ambience_map
    assert "rain" not in config.env_ambience_map


def test_legacy_audio_environment_aliases_normalize_to_story_contract() -> None:
    assert normalize_env_key("cafe") == "cafe_soft"
    assert normalize_env_key("rain") == "rain_soft"
    assert normalize_env_key("cafe_soft") == "cafe_soft"
    assert normalize_env_key("rain_soft") == "rain_soft"
    assert set(load_bgm_runtime_config(ASSETS_ROOT / "bgm_config.json").env_ambience_map) == (
        CANONICAL_STORY_ENVIRONMENT_SET - {"none"}
    )
