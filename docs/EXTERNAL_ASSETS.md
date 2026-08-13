# External assets

Large model files and retired Story/Image assets are intentionally stored outside this source checkout.

## Active Audio models

- Location: `D:\ai-models\audio`
- Configure: set `AI_AUDIO_MODELS_ROOT=D:\ai-models\audio`
- The application falls back to `audio/models` when the variable is not set.

## Retired module archive

- Location: `D:\ai-model-archive`
- `story-models` and `image-models` contain the retired local model stores.
- `story-assets` contains the retired framework and prompt material.

The archive is not required by Audio or Video at runtime and may be deleted after recovery is no longer needed.
