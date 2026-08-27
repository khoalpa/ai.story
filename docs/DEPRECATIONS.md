# Deprecations

The following capabilities are outside the supported 0.1 API:

- Story and image-generation packages removed before the 0.1 release candidate.
- Direct imports from renderer internals; use each package's `app_api` module.
- Process-local handoff state; use versioned filesystem manifests.
- Models stored inside `audio/models`; use `AI_AUDIO_MODELS_ROOT`.

Compatibility wrappers may emit `DeprecationWarning`. They can be removed in the
next minor release after a replacement has been documented for one release cycle.
Tests and applications must not introduce new imports from deprecated modules.
