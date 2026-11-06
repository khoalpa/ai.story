from __future__ import annotations

from copy import deepcopy

from studio.summary_projection import (
    project_summary_to_story,
    project_summary_to_visual_plan,
)
from studio.summary_visual import build_summary_visual_plan, visual_density
from studio.summary_visual_schema import validate_summary_visual_plan
from tests.contracts.test_summary_projection import summary_fixture


def test_build_summary_visual_plan_is_valid_and_reports_density() -> None:
    summary = summary_fixture()
    plan = build_summary_visual_plan(summary)

    assert validate_summary_visual_plan(plan, summary) == []
    assert visual_density(summary, plan, 2.0)["scene_count"] == len(
        summary["narration"]
    )


def test_data_chart_requires_a_numeric_fact_reference() -> None:
    summary = summary_fixture()
    plan = build_summary_visual_plan(summary)
    plan["scenes"][0]["visual_type"] = "DATA_CHART"

    assert any(
        "DATA_CHART cần numeric_fact_ids" in error
        for error in validate_summary_visual_plan(plan, summary)
    )

    plan["scenes"][0]["numeric_fact_ids"] = [
        summary["numeric_facts"][0]["numeric_fact_id"]
    ]
    assert validate_summary_visual_plan(plan, summary) == []


def test_canonical_scene_prompts_are_used_by_story_projection() -> None:
    summary = summary_fixture()
    plan = deepcopy(build_summary_visual_plan(summary))
    plan["scenes"][0]["brief"] = "Biểu đồ nguồn kiểm chứng"
    plan["scenes"][0]["landscape_prompt"] = "CUSTOM LANDSCAPE"
    plan["scenes"][0]["portrait_prompt"] = "CUSTOM PORTRAIT"

    projected = project_summary_to_visual_plan(
        summary, project_summary_to_story(summary), plan
    )
    first_scene = next(row for row in projected["assets"] if row["role"] == "SCENE")

    assert first_scene["brief"] == "Biểu đồ nguồn kiểm chứng"
    assert first_scene["landscape_prompt"] == "CUSTOM LANDSCAPE"
    assert first_scene["portrait_prompt"] == "CUSTOM PORTRAIT"
