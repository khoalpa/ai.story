# Refactor change scope

This migration deliberately leaves pre-existing user and runtime-content edits
outside the architecture change set.

## Pre-existing user/domain edits

- `audio/app_config.py`
- `audio/gui/settings.py`
- `audio/gui/state.py`
- `audio/profile_config.py`
- `audio/services/render_runtime.py`
- `images_tiktok.txt`
- `images_youtube.txt`
- `input/story.json`

Review these files separately before creating an architecture commit.

## Architecture migration

- standalone feature-package runtimes and GUI helpers
- stable `app_api` modules
- removal of `common` and `studio/_shared`
- package-owned assets and manifests
- dependency, wheel, smoke-test, and documentation updates

## Recommended commit split

1. Standalone package architecture and tests.
2. Asset ownership and removed duplicate binaries.
3. Pre-existing Audio behavior changes, after independent review.
4. Local input/prompt data only if it is intentionally versioned.
