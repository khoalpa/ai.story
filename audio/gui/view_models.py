from __future__ import annotations

from typing import Any

from audio.gui.view_model_utils import pick_mapping_values


_AUDIO_SETTINGS_FIELDS = (
    'asset_profile',
    'audio_format',
    'tts_provider',
    'bgm',
    'output_dir',
    'validate_only',
    'debug_mode',
    'post_fx_preset',
    'max_concurrent_tts',
)


def build_audio_run_summary(settings: dict[str, Any]) -> dict[str, Any]:
    return pick_mapping_values(settings, _AUDIO_SETTINGS_FIELDS)
