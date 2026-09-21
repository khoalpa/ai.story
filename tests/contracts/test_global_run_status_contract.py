from __future__ import annotations

import pytest

from audio.gui.global_run_monitor import global_run_monitor_state as audio_monitor
from video.gui.global_run_monitor import global_run_monitor_state as video_monitor


@pytest.mark.parametrize("factory", [audio_monitor, video_monitor])
def test_run_status_is_normalized_and_progress_is_clamped(factory) -> None:
    state: dict[str, object] = {}
    monitor = factory(state)
    monitor.status = "success"
    monitor.progress = 140
    assert monitor.status == "completed"
    assert monitor.progress == 100

    monitor.status = "unexpected"
    monitor.progress = -5
    assert monitor.status == "warning"
    assert monitor.progress == 0
