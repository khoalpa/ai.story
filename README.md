# AI Audio & Video Studio

AI Audio & Video Studio is a pair of standalone Python applications plus a unified Streamlit shell:

- **Audio** converts an external plain-text or canonical JSON script into narration, subtitles, quality reports, and an Audio-to-Video handoff manifest.
- **Video** combines audio, optional subtitles, and externally supplied cover/scene images into a validated MP4.

Story generation and image generation are intentionally outside this repository. Scripts and visual assets can come from any authoring or image-generation tool.

Canonical authoring references live in `prompts/`, named `ChatGPT_prompt_vX.Y.Z.txt`
with an optional numeric prefix such as `01-`. Runtime
tooling selects the newest semantic version, projects its deterministic constants,
and reports the selected version plus SHA-256. Older prompt files may be retained
for comparison, but their presence is optional and they are never authoritative
while a newer version is present.

## Requirements

- Python 3.10, 3.11, or 3.12
- FFmpeg and FFprobe for rendering

Large local Audio models may be stored outside the checkout by setting
`AI_AUDIO_MODELS_ROOT`. See [docs/EXTERNAL_ASSETS.md](docs/EXTERNAL_ASSETS.md).

Install the project:

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
```

For development, install `requirements-dev.txt` instead. The supported Python
range is `>=3.10,<3.13`; CI exercises Python 3.10, 3.11, and 3.12.

## Entry points

```bash
render-audio --help
render-audio-gui
render-video --help
render-video-gui
ai-studio-gui
ai-story-audit --help
```

The unified Studio contains `Overview`, `Audio`, `Video`, and `Story Studio` workspaces.
`Story Studio` discovers the story, validation, package-quality, and series-anchor JSON
reports in one output directory and combines their content, verdicts, continuity data,
technical details, and repository QA tools.

## Workflow

1. Supply Audio with a plain-text or canonical JSON script.
2. Render narration and subtitles. Audio can write an `audio.video-handoff` manifest.
3. Supply Video with the audio file or Audio handoff, plus a cover image or scene-image directory.
4. Render the MP4 and review its result and quality manifests.

Video does not generate images. Pillow remains a runtime dependency because Video validates image dimensions, formats, and slideshow readiness.

## Audio pacing

Narration pacing is adaptive: the mixer measures leading and trailing silence from each synthesized segment and inserts only the amount needed to reach the selected acoustic gap. The default `natural` preset targets 550 ms between sentences, 650 ms on voice/language changes, 800 ms at paragraph breaks, and 1200 ms at zone changes. Explicit `[PAUSE]` and `[SILENCE]` tags take precedence. The `compact`, `dramatic`, and `off` presets are also available.

## Development and verification

```bash
ruff check .
mypy
pytest -q
python scripts/run_audio_to_video_e2e.py --fixture --report e2e-report.json
python scripts/check_public_api.py
python scripts/check_dependency_direction.py
python scripts/check_standalone_architecture.py
python scripts/check_module_size_budget.py
python scripts/check_wheel_contents.py
python scripts/check_independent_wheels.py
python scripts/release_smoke.py
```

See [Troubleshooting](docs/TROUBLESHOOTING.md),
[standalone-package migration](docs/MIGRATION_STANDALONE_PACKAGES.md), and
[deprecations](docs/DEPRECATIONS.md) for operational details. The maintenance
workflow for future prompt versions is documented in
[Prompt–runtime synchronization](docs/PROMPT_SYNC.md).

Independent wheels are defined under `packages/audio`, `packages/video`, and `packages/studio`.

## Prompt conformance

Run a deterministic audit against the newest prompt in `prompts/`:

```bash
ai-story-audit output
ai-story-audit output/story.zip
```

The audit checks strict JSON parsing, current schema projections, artifact bindings,
archive file sets, CRC, PNG format, and canonical image dimensions. Gates that need
OCR, generator provenance, semantic review, or an external safety adapter are reported
as `NOT_VERIFIED`; deterministic checks never promote those gates to `PASS`.
