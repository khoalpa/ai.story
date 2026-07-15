# Migration to standalone packages

## Imports

- `common.*` has been removed. Import the equivalent module from the owning
  feature package.
- `studio._shared.*` has been removed.
- Embedded integrations must use `story.app_api`, `audio.app_api`,
  `image.app_api`, or `video.app_api`.

## Assets

- Story prompts and LLM configuration: `story/assets`.
- Audio BGM and voice profiles: `audio/assets`.
- Image workflows: `image/assets/workflows`.
- Video cover and scenes: `video/assets/profiles`.

## Distribution names

The legacy `ai-studio` wheel remains available during migration. New isolated
installs use `ai-story`, `ai-audio`, `ai-image`, `ai-video`, and
`ai-studio-shell`.

## Handoffs

Do not exchange cross-feature data solely through Streamlit session keys.
Write a versioned filesystem manifest and pass its path to the consumer.
Relative artifact paths replace machine-specific absolute paths.

## Compatibility

The `render_*_studio` integration aliases remain supported for this release.
Internal compatibility wrappers without callers may be removed independently;
public removals require a deprecation cycle.

See [the deprecation policy](DEPRECATIONS.md) for the planned removal window.
