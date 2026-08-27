# Migrating to standalone packages

Version 0.1 separates the repository into `ai-audio`, `ai-video`, and the
`ai-studio-shell` integration package. Existing source imports remain
`audio`, `video`, and `studio`.

Install only the renderer required by an application, or install Audio and
Video before the Studio shell. Integrations should use `audio.app_api` and
`video.app_api`; internal GUI, adapter, and service modules are not stable API.

Story and image generation are no longer shipped. Supply plain-text or canonical
JSON scripts to Audio and external images to Video. Exchange artifacts through
the versioned Audio-to-Video handoff manifest instead of sharing process state.

Before upgrading, run `python scripts/check_public_api.py` and the offline E2E
fixture. Large local models should be moved outside the checkout and referenced
through `AI_AUDIO_MODELS_ROOT`.
