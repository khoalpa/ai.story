from __future__ import annotations

import pytest

from studio.series_anchor_report import _status_text, _validate_series_anchor


def _minimal_anchor() -> dict:
    return {
        "series": {},
        "canon": {},
        "continuity": {},
        "episode_ledger": [],
        "canon_change_log": [],
    }


def test_series_anchor_contract_accepts_required_sections() -> None:
    _validate_series_anchor(_minimal_anchor())


def test_series_anchor_contract_lists_missing_sections() -> None:
    with pytest.raises(ValueError, match="continuity"):
        _validate_series_anchor({"series": {}})


def test_status_labels_are_human_readable() -> None:
    assert _status_text("active") == "Đang phát triển"
    assert _status_text("custom_state") == "Custom State"
