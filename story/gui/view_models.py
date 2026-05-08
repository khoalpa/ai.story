from __future__ import annotations

from typing import Any

from story.gui.view_model_utils import pick_mapping_values


_STORY_SETTINGS_FIELDS = (
    'mode',
    'mode_label',
    'base_mode',
    'chunked',
    'chunk_size',
    'temperature',
)


def build_story_run_summary(settings: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    summary = pick_mapping_values(settings, _STORY_SETTINGS_FIELDS)
    project = (brief.get('project') or {}) if isinstance(brief, dict) else {}
    goals = (brief.get('goals') or {}) if isinstance(brief, dict) else {}
    summary.update({
        'title': project.get('title'),
        'language': project.get('language_primary'),
        'target_duration_min': goals.get('target_duration_min'),
    })
    return summary
