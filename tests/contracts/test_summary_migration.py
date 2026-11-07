from __future__ import annotations

import pytest

from studio.summary_migration import normalize_summary_v110_ids
from studio.summary_schema import validate_summary_document
from tests.contracts.test_summary_projection import summary_fixture


def _legacy_shaped_summary() -> dict:
    document = summary_fixture()
    document["meta"]["citation_style"] = "SECTION"
    document["sources"][0]["source_id"] = "source_01"
    document["locators"][0]["locator_id"] = "locator_001"
    document["locators"][0]["source_id"] = "source_01"
    document["sections"][0]["source_id"] = "source_01"
    document["sections"][0]["locator_ids"] = ["locator_001"]
    document["claims"][0]["claim_id"] = "claim_001"
    document["claims"][0]["source_ids"] = ["source_01"]
    document["claims"][0]["locator_ids"] = ["locator_001"]
    document["numeric_facts"][0]["numeric_fact_id"] = "numeric_001"
    document["numeric_facts"][0]["locator_ids"] = ["locator_001"]
    document["glossary"][0]["locator_ids"] = ["locator_001"]
    document["narration"][0]["narration_id"] = "narration_001"
    document["narration"][0]["claim_ids"] = ["claim_001"]
    return document


def test_normalize_summary_v110_ids_updates_entire_reference_graph() -> None:
    source = _legacy_shaped_summary()

    migrated = normalize_summary_v110_ids(source, citation_style="MARKDOWN")

    assert validate_summary_document(migrated) == []
    assert migrated["meta"]["citation_style"] == "MARKDOWN"
    assert migrated["sources"][0]["source_id"] == "src_001"
    assert migrated["locators"][0]["locator_id"] == "loc_0001"
    assert migrated["sections"][0]["locator_ids"] == ["loc_0001"]
    assert migrated["claims"][0]["claim_id"] == "claim_0001"
    assert migrated["numeric_facts"][0]["numeric_fact_id"] == "num_0001"
    assert migrated["narration"][0]["narration_id"] == "narration_0001"
    assert migrated["narration"][0]["claim_ids"] == ["claim_0001"]
    assert source["sources"][0]["source_id"] == "source_01"


def test_normalize_summary_v110_ids_rejects_duplicate_primary_ids() -> None:
    source = _legacy_shaped_summary()
    source["claims"].append(dict(source["claims"][0]))

    with pytest.raises(ValueError, match="claim_id bị trùng"):
        normalize_summary_v110_ids(source)
