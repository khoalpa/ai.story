# Troubleshooting

## FFmpeg or FFprobe is unavailable

Run the application's diagnostics and verify both executables are on `PATH`.
On Windows, the runtime resolves Chocolatey shims to their real executables when
application-control policy blocks the shim.

## Type checking fails inside a dependency

Use Python 3.10-3.12, install `requirements-dev.txt`, and run mypy from the project
root. The configuration intentionally ignores third-party site-package stubs and
checks the shipped source tree.

## VieNeu model cannot load

Check the selected core, backend, local target, and model cache from runtime
diagnostics. Keep large models outside the repository with
`AI_AUDIO_MODELS_ROOT`. Network-backed providers may require a separate download
before offline rendering.

## Rendering stops or produces a partial artifact

Inspect the run log, quality report, and handoff/result manifest together. Verify
checksums before reusing artifacts. Re-run with the fixture E2E to distinguish an
installation problem from provider or input-media failure.

## Release verification

Run pytest, Ruff, mypy, the architecture scripts, wheel checks, release smoke,
and the offline Audio-to-Video fixture listed in the README. A fixture pass does
not replace a real provider render before a public release.
