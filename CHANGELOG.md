# Changelog

## 0.1.0 release candidate

This release remains classified as Alpha while the release checklist below is
being completed. The command-line interfaces and filesystem handoff formats are
the supported integration surfaces for the 0.1 series.

### Added

- Added a unified Streamlit shell with Overview, Audio, Video, and Story Studio
  workspaces.
- Added deterministic prompt-contract discovery using the newest semantic prompt
  version and its SHA-256 provenance.
- Added workflow 3.13 package inspection for stage manifests, strict JSON, archive
  security, member digests, ownership, parent binding, and video-prompt projection.
- Added target adapter exports for Veo, Flow, and Generic video prompts, including
  per-clip JSON jobs, copy-friendly text, deterministic ZIP packages, reference maps,
  generation order, capability warnings, and Flow last-frame dependency edges.
- Added adaptive narration pacing, configurable voice speed, TTS caching, and
  delivery-quality reports.
- Added a 45% branch-aware coverage gate for shipped Audio, Video, and Studio
  packages, with the XML report retained as a CI artifact.
- Added a Windows job that runs the complete test suite on Python 3.11.

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
- Added Ruff, mypy, security-policy, public-API, dependency-direction, module-size,
  wheel-content, and independent-wheel gates.
- Verified the current release candidate with 520 passing tests on the development
  environment.

### Compatibility

- Supported Python versions are 3.10, 3.11, and 3.12.
- FFmpeg and FFprobe remain external runtime requirements for media rendering.
- Local VieNeu and codec models are intentionally excluded from source and wheels;
  configure `AI_AUDIO_MODELS_ROOT` for external model storage.
- The integrated wheel includes the bundled BGM catalog, while standalone Audio
  and Video wheels retain only assets owned by their packages.

### Known limitations

- Story and image generation are outside this repository.
- OCR, generator provenance, semantic continuity, visual-quality judgement, and
  external safety adapters can remain `NOT_VERIFIED`; deterministic validators do
  not manufacture a `PASS` for those gates.
- Some GUI and TTS modules remain larger than the preferred maintenance target.
- The project is not considered API-stable beyond the documented CLI commands,
  `app_api` surfaces, and versioned filesystem handoff schemas.

### Release validation

Before tagging 0.1.0, run the commands documented under Development and
verification in `README.md`. A release requires all CI jobs to pass, including the
Linux coverage gate, the Windows full-suite job, independent wheel installation,
and release smoke checks. Wheel checksums must be generated from the final commit.

The Alpha classifier may be removed only after:

- the release candidate passes the supported Python and operating-system matrix;
- coverage remains at or above the configured threshold;
- migration and deprecation notes match the shipped handoff schemas;
- all release wheels install and expose their documented entry points; and
- no deterministic release gate reports `FAIL`.

### Migration

See `docs/MIGRATION_STANDALONE_PACKAGES.md` and `docs/DEPRECATIONS.md`.
