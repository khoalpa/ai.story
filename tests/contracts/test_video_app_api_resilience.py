from __future__ import annotations

import contextlib
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from video import app_api


def _static_request(tmp_path: Path) -> app_api.RenderVideoRequest:
    return app_api.RenderVideoRequest(
        audio=tmp_path / "audio.wav",
        output=tmp_path / "video.mp4",
        mode="static",
        aspect="16x9",
        duration_per_image=1.0,
        cover=tmp_path / "cover.png",
    )


def test_execute_render_request_serializes_process_wide_overrides(monkeypatch, tmp_path: Path) -> None:
    active = 0
    max_active = 0
    state_lock = threading.Lock()

    def fake_execute(_request, progress_callback=None):
        nonlocal active, max_active
        with state_lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.03)
        with state_lock:
            active -= 1
        return {"status": "ok"}

    monkeypatch.setattr(app_api, "_execute_render_request_unlocked", fake_execute)
    request = _static_request(tmp_path)
    threads = [threading.Thread(target=app_api.execute_render_request, args=(request,)) for _ in range(3)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert max_active == 1


def test_unexpected_exception_is_preserved_and_recorded_as_error(monkeypatch, tmp_path: Path) -> None:
    request = _static_request(tmp_path)
    history_entries = []

    monkeypatch.setattr(app_api, "inspect_video_image_readiness", lambda **_kwargs: SimpleNamespace(errors=[]))
    monkeypatch.setattr(app_api, "format_runtime_diagnostics", lambda *_args: "ready")
    monkeypatch.setattr(app_api, "ensure_tools", lambda: (_ for _ in ()).throw(KeyError("boom")))
    monkeypatch.setattr(app_api, "_runtime_tool_env", lambda *_args: contextlib.nullcontext())
    monkeypatch.setattr(app_api, "_render_runtime_overrides", lambda *_args: contextlib.nullcontext())
    monkeypatch.setattr(app_api, "write_run_log", lambda **_kwargs: tmp_path / "render.log")

    def capture_history(entry):
        history_entries.append(entry)
        return tmp_path / "history.jsonl"

    monkeypatch.setattr(app_api, "append_run_history", capture_history)

    with pytest.raises(KeyError, match="boom"):
        app_api._execute_render_request_unlocked(request)

    assert history_entries[0]["status"] == "error"


def test_history_failure_does_not_mask_render_failure(monkeypatch, tmp_path: Path) -> None:
    request = _static_request(tmp_path)
    monkeypatch.setattr(app_api, "inspect_video_image_readiness", lambda **_kwargs: SimpleNamespace(errors=[]))
    monkeypatch.setattr(app_api, "format_runtime_diagnostics", lambda *_args: "ready")
    monkeypatch.setattr(app_api, "ensure_tools", lambda: (_ for _ in ()).throw(KeyError("render failed")))
    monkeypatch.setattr(app_api, "_runtime_tool_env", lambda *_args: contextlib.nullcontext())
    monkeypatch.setattr(app_api, "_render_runtime_overrides", lambda *_args: contextlib.nullcontext())
    monkeypatch.setattr(
        app_api,
        "write_run_log",
        lambda **_kwargs: (_ for _ in ()).throw(OSError("history unavailable")),
    )

    with pytest.raises(KeyError, match="render failed"):
        app_api._execute_render_request_unlocked(request)
