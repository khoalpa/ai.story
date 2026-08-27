from __future__ import annotations

import io
import json

import pytest

from studio.package_quality_report import (
    _format_generated_at,
    _read_report,
    _short_digest,
)


def test_read_report_accepts_utf8_json_object() -> None:
    source = io.BytesIO(json.dumps({"schema_version": "2.0"}).encode("utf-8"))
    assert _read_report(source) == {"schema_version": "2.0"}


def test_read_report_rejects_non_object_json() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        _read_report(io.BytesIO(b"[]"))


def test_short_digest_preserves_context_at_both_ends() -> None:
    digest = "0123456789abcdef0123456789abcdef"
    assert _short_digest(digest) == "01234567…9abcdef"


def test_generated_time_is_human_readable() -> None:
    assert _format_generated_at("2026-08-26T12:04:12Z") != "2026-08-26T12:04:12Z"
