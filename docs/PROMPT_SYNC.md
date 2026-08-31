# Prompt–runtime synchronization

Versioned `ChatGPT_prompt_vX.Y.Z.txt` files in `prompts/` are the normative authoring contract.
An optional numeric prefix such as `01-` is supported; version selection ignores that prefix. The
repository automatically selects the highest semantic version. Older prompts may
remain beside it for comparison.

The runtime intentionally projects only deterministic rules it can verify:

- canonical image basenames and dimensions;
- environment names;
- current story-validation, package-quality, series-anchor, and story-quality
  commitment schema versions;
- strict JSON, hashes, archive membership, CRC, and image format.
- resolved immutable public-schema/enum/config registries;
- workflow package stages, operations, ownership, parent binding, and video prompt controls.

OCR, safety adapters, generator provenance, and semantic or visual judgement are
outside this deterministic projection. The audit reports these as `NOT_VERIFIED`
rather than manufacturing a `PASS`.

## Upgrade procedure

1. Add the new `ChatGPT_prompt_vX.Y.Z.txt` to `prompts/`; do not overwrite an older
   version when its history is still useful.
2. Run `pytest -q tests/contracts/test_prompt_contract.py`. A changed projected
   literal intentionally fails until the corresponding runtime consumer and test
   expectation are reviewed.
3. Run `pytest -q tests/contracts` and `ruff check studio tests/contracts`.
4. Audit a representative output with `ai-story-audit output`.
5. Review every `FAIL` and `NOT_VERIFIED`. Do not weaken deterministic validation
   to make old artifacts pass; add an explicit, bounded compatibility path instead.

Set `AI_STUDIO_PROMPTS_DIR` when prompts live outside the checkout. The CLI also
accepts `--prompt` to audit against one exact prompt version.
