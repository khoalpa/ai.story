# Standalone packages

The repository publishes four independent feature distributions and one shell:

| Distribution | Import package | Responsibility |
|---|---|---|
| `ai-story` | `story` | Story generation and Story handoffs |
| `ai-audio` | `audio` | Narration, subtitles, and Audio handoffs |
| `ai-image` | `image` | Prompt rendering and Image handoffs |
| `ai-video` | `video` | Static/slideshow video rendering |
| `ai-studio-shell` | `studio` | Integration through feature `app_api` modules |

Each feature wheel owns its runtime, GUI helpers, provider registry and assets.
Feature packages do not import one another. Studio is the only integration layer.

## Installation

```bash
pip install ./packages/story
pip install ./packages/audio
pip install ./packages/image
pip install ./packages/video
pip install --find-links dist ./packages/studio
```

## Filesystem handoffs

Cross-package data uses JSON manifests rather than Python imports or Streamlit
session state. Every manifest contains `schema_version`, `kind`, `producer`,
`created_at`, and an `artifacts` mapping. Artifact paths should be relative to
the manifest so the bundle remains portable.

Supported version-1 kinds:

- `story.audio-handoff`
- `story.image-handoff`
- `audio.video-handoff`
- `image.video-handoff`

Streamlit session state may cache a manifest path, but it is not the
cross-package data contract.
