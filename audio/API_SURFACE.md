# audio package API surface

## Public modules
- `audio.render_audio_app`
- `audio.app_config`
- `audio.profile_config`
- `audio.tts_provider`
- `audio.voice_catalog`
- `audio.cli`
- `audio.entrypoints`
- `audio.doctor`
- `audio.gui`

## Internal subpackages
- `audio.adapters`
- `audio.models`
- `audio.pipeline`
- `audio.services`

Code outside `audio/` should avoid importing internal subpackages directly unless
there is a deliberate extension point and the dependency is pinned.
