# Changelog

## 0.1.0 release candidate

### Changed

- Split Story, Audio, Image, Video, and Studio into independently buildable distributions.
- Removed the `common` and `studio/_shared` packages.
- Added stable `app_api` integration surfaces.
- Assigned prompts, BGM, workflows, and video profiles to their owning packages.
- Added versioned, portable filesystem handoff manifests with artifact provenance and checksums.
- Added Video CLI and GUI support for Audio and Image handoff manifests.
- Added optional cover-first slideshow rendering with a configurable duration
  that preserves the original audio and MP4 timeline length.
- Added automatic `outro.png` end-screen rendering for the final five seconds,
  with CLI and GUI controls and no change to the original timeline length.

### Quality

- Added independent-wheel and integrated-Studio installation matrices.
- Added architecture, duplicate-asset, schema, and handoff portability checks.
- Added Windows-compatible release smoke probes through `python -m`.

### Migration

See `docs/MIGRATION_STANDALONE_PACKAGES.md` and `docs/DEPRECATIONS.md`.
