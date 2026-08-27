from __future__ import annotations

import importlib


def test_voice_speed_master_updates_all_six_voice_speeds() -> None:
    settings = importlib.import_module("audio.gui.settings")
    state = {settings.VOICE_SPEED_MASTER_KEY: 35}

    settings._apply_voice_speed_master(state)

    assert len(settings.VOICE_SPEED_KEYS) == 6
    assert {state[key] for key in settings.VOICE_SPEED_KEYS} == {35}


def test_voice_speed_master_clamps_invalid_range() -> None:
    settings = importlib.import_module("audio.gui.settings")
    state = {settings.VOICE_SPEED_MASTER_KEY: 150}

    settings._apply_voice_speed_master(state)

    assert state[settings.VOICE_SPEED_MASTER_KEY] == 100
    assert {state[key] for key in settings.VOICE_SPEED_KEYS} == {100}
