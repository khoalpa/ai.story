from __future__ import annotations

import pytest

from studio.summary_exports import affected_artifacts, export_citations
from tests.contracts.test_summary_projection import summary_fixture


@pytest.mark.parametrize("style", ["MARKDOWN", "APA", "MLA", "CHICAGO", "BIBTEX"])
def test_citation_exports_use_source_metadata(style: str) -> None:
    output = export_citations(summary_fixture(), style)

    assert "Nguồn mẫu" in output
    assert "Tác giả mẫu" in output
    assert "2026" in output


def test_dependency_invalidation_starts_at_correct_layer() -> None:
    assert affected_artifacts(["claim"])[0] == "summary.json"
    narration = affected_artifacts(["narration"])
    assert narration[0] == "summary_narration.txt"
    assert "story.json" in narration and "rendered_media" in narration
    scene = affected_artifacts(["scene"])
    assert scene[0] == "summary_visual_plan.json"
    assert "story.json" not in scene
    assert "summary_render_plan.json" in scene
    assert scene[-1] == "summary_package.zip"


def test_dependency_invalidation_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="không hỗ trợ"):
        affected_artifacts(["unknown"])
