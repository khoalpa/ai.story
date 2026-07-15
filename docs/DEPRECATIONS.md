# Deprecation policy

All five distributions use the repository `VERSION` value and are released as
one compatible set. Filesystem handoff schemas have an independent integer
`schema_version`.

## Supported during 0.1.x

- `render_story_studio`, `render_audio_studio`, `render_image_studio`, and
  `render_video_studio` remain supported integration aliases.
- String-valued artifact paths in handoff schema version 1 remain readable.
- The legacy `ai-studio` aggregate wheel remains buildable.

## Planned for 0.2.0

- Artifact descriptors with `path`, `media_type`, `size_bytes`, and `sha256`
  become the only format written by producers.
- Legacy aggregate-wheel documentation is removed after the standalone wheel
  release has been verified.

Public aliases require at least one minor release of documentation before
removal. Internal wrappers with no callers may be removed immediately.
