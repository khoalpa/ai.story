from __future__ import annotations

import importlib


def test_voice_speed_defaults_reset_when_voice_changes() -> None:
    pipeline = importlib.import_module("audio.pipeline.script_pipeline")

    segments = pipeline.plan_segments_from_plain_script(
        "\n".join(
            [
                "SCRIPT:",
                "[NARRATOR] One line.",
                "[FEMALE] Another line.",
            ]
        ),
        voice_rate_map={
            "vi_narrator": "+20%",
            "vi_female": "+5%",
            "vi_male": "+1%",
            "en_narrator": "+8%",
            "en_female": "+9%",
            "en_male": "+10%",
        },
    )

    assert [seg.rate for seg in segments] == ["+20%", "+5%"]


def test_voice_speed_defaults_follow_language_specific_defaults() -> None:
    pipeline = importlib.import_module("audio.pipeline.script_pipeline")

    segments = pipeline.plan_segments_from_plain_script(
        "\n".join(
            [
                "SCRIPT:",
                "[VI][NARRATOR] Xin chao.",
                "[EN][NARRATOR] Hello.",
                "[EN][MALE] Hi.",
            ]
        ),
        voice_rate_map={
            "vi_narrator": "+18%",
            "vi_female": "+14%",
            "vi_male": "+10%",
            "en_narrator": "+7%",
            "en_female": "+9%",
            "en_male": "+11%",
        },
    )

    assert [seg.rate for seg in segments] == ["+18%", "+7%", "+11%"]

