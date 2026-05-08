from __future__ import annotations

"""Public API for the audio package.

Stable public modules live at the package root (for example: render_audio_app,
app_config, profile_config, tts_provider, voice_catalog, cli, doctor, gui).
Implementation details are organized under subpackages:
- audio.adapters
- audio.models
- audio.pipeline
- audio.services

Anything under those subpackages should be treated as internal unless explicitly
re-exported here or documented as public.
"""

__version__ = "0.1.0"

from audio.render_audio_app import (
    RenderAudioAppRequest,
    RenderAudioAppResult,
    create_app_request_from_args,
    create_default_app_request,
    run_render_audio_app,
    validate_only_script,
)

__all__ = [
    "RenderAudioAppRequest",
    "RenderAudioAppResult",
    "create_app_request_from_args",
    "create_default_app_request",
    "run_render_audio_app",
    "validate_only_script",
    "__version__",
]
