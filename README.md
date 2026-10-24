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

## Editing and production review

- `open_app.bat` checks the selected interpreter against the Python and Streamlit
  requirements in `pyproject.toml` before starting the interface.
- In Audio's **Canonical JSON** tab, **Chỉnh từng câu thoại** edits a selected
  line's speaker, text, emotion, speed, pause, and ambience. IDs, zones, scenes,
  order, and the existing closed schema are preserved. Edits remain a session
  draft, survive workspace navigation, and can be downloaded as `story.draft.json`.
  The source package and its validation reports are never overwritten; changed
  content needs review before replacing a published package.
- Video prepares a separate display SRT when a cue contains several sentences.
  Display timing is estimated from text length within the original cue. Scene
  transitions and environment effects continue to use the original SRT, including
  when subtitle display is disabled. Styled and very short cues remain intact.
- Story Studio's **Âm thanh & phụ đề → Tổng quan → Audio theo phần truyện**
  summarizes script counts and source-subtitle timing by zone or scene, with CSV
  export. Timing is withheld when text/order does not match or cues overlap.
  Part timing does not imply that per-part audio quality has been verified.
- In **Tài nguyên → Lịch sử kiểm tra ảnh**, record a local inspection to track
  image revisions, the latest inspection result, notes, and the content fingerprint
  observed with each revision. Rechecking unchanged bytes does not increment the
  revision or rebind the image to changed story content. History is stored in
  `.render_audio_gui/story_asset_history_*.json`, outside the canonical package.
  These observations are separate from image-generation provenance and semantic QA.

These tools retain the four-stage package format, source JSON schemas, and
Audio-to-Video handoff contract.

## Audio pacing

Narration pacing is adaptive: the mixer measures leading and trailing silence from each synthesized segment and inserts only the amount needed to reach the selected acoustic gap. The default `natural` preset targets 550 ms between sentences, 650 ms on voice/language changes, 800 ms at paragraph breaks, and 1200 ms at zone changes. Explicit `[PAUSE]` and `[SILENCE]` tags take precedence. The `compact`, `dramatic`, and `off` presets are also available.

## Development and verification

The four canonical reference archives live in `samples/Tiem_Sua_Nhung_Loi_Hua/`.
Their exact bytes are pinned in the adjacent `SHA256SUMS` file and tracked by Git.
Studio's sample tabs and the test fixtures use the shared definitions in
`studio/reference_samples.py`; neither requires a populated `output/` directory.

Tests that need extracted files receive a fresh temporary project from the
fixtures in `conftest.py`. Archives are verified before extraction, and edits in
one test cannot modify the reference files or another test's project. Missing or
changed samples fail explicitly instead of skipping package validation.

CI runs `python scripts/check_reference_samples.py --require-tracked` before
testing. When intentionally replacing a reference archive, review its contents,
update its pinned checksum, and rerun the existing contract tests. The loader
never updates checksums automatically. Only the four ZIP files and their checksum
list are required; generated audio, video and manually extracted sample folders
are not test inputs. Reference data stays outside the Audio/Video wheels.

```bash
python scripts/check_reference_samples.py --require-tracked
ruff check .
mypy
pytest -q --cov=audio --cov=video --cov=studio --cov-report=term-missing:skip-covered --cov-report=xml
python scripts/run_audio_to_video_e2e.py --fixture --report e2e-report.json
python scripts/check_public_api.py
python scripts/check_dependency_direction.py
python scripts/check_standalone_architecture.py
python scripts/check_module_size_budget.py
python scripts/check_wheel_contents.py
python scripts/check_independent_wheels.py
python scripts/release_smoke.py
```

The full-suite coverage command measures branches in the three shipped packages
and fails below the threshold configured in `pyproject.toml`. Targeted test runs do
not apply the global threshold, so they remain useful during development.

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

Story Studio can export a structurally valid canonical `video_prompts.json` into
target-specific Veo, Flow, or Generic prompt artifacts. Available formats are one
bound JSON document, copy-friendly text, and a deterministic ZIP containing per-clip
jobs, reference mapping, generation order, capability warnings, and source digests.
Exports are disposable views; they never replace or modify the canonical source.
