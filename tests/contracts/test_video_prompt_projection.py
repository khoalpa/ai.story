from __future__ import annotations

import hashlib
import json

from studio.prompt_contract import load_prompt_contract
from studio.video_prompt_projection import (
    canonical_json_bytes,
    project_video_prompts,
    validate_projection,
)
from studio.video_prompt_validation import (
    canonical_output_digest,
    validate_video_prompt_plan,
)


def test_projection_is_deterministic_and_bound_to_canonical_bytes() -> None:
    contract = load_prompt_contract()
    plan = {"schema_version": contract.video_prompt_schema_version, "project": {"title": "T"}, "global_continuity_lock": {}, "clips": []}
    source = canonical_json_bytes(plan)
    name, first = project_video_prompts(plan, "VEO", source_bytes=source, contract=contract)
    _, second = project_video_prompts(plan, "VEO", source_bytes=source, contract=contract)
    document = json.loads(first)
    assert name == "video_prompts.veo.json"
    assert first == second
    assert document["projection_binding"]["source_digest_sha256"] == hashlib.sha256(source).hexdigest()
    assert validate_projection(document, plan, source_bytes=source, contract=contract)


def test_projection_becomes_stale_when_canonical_bytes_change() -> None:
    plan = {"schema_version": "1.0", "project": {}, "global_continuity_lock": {}, "clips": []}
    source = canonical_json_bytes(plan)
    _, raw = project_video_prompts(plan, "FLOW", source_bytes=source)
    assert not validate_projection(json.loads(raw), plan, source_bytes=source + b" ")


def test_output_digest_uses_null_digest_field() -> None:
    plan = {"validation": {"output_digest_sha256": "placeholder"}}
    expected = hashlib.sha256(canonical_json_bytes({"validation": {"output_digest_sha256": None}})).hexdigest()
    assert canonical_output_digest(plan) == expected


def test_validator_rejects_noncanonical_root() -> None:
    result = validate_video_prompt_plan({"schema_version": "0.9"})
    assert result["status"] == "FAIL"
    assert result["errors"]
