from __future__ import annotations


def test_provider_choices_are_managed_from_common_catalog() -> None:
    from image.provider_catalog import get_provider_choice_group
    from audio.tts_provider import DEFAULT_TTS_PROVIDER, get_tts_provider_choices
    from image.providers import list_sd_provider_ids
    from story.llm_providers import DEFAULT_PROVIDER_ID, list_provider_ids
    from video.providers.registry import DEFAULT_VIDEO_PROVIDER, get_video_provider_choices

    audio_choices = get_provider_choice_group("audio_tts")
    image_choices = get_provider_choice_group("image_sd")
    story_choices = get_provider_choice_group("story_llm")
    video_choices = get_provider_choice_group("video")

    assert DEFAULT_TTS_PROVIDER == audio_choices.default_provider_id
    assert get_tts_provider_choices() == list(audio_choices.provider_ids)

    assert list_sd_provider_ids() == list(image_choices.provider_ids)

    assert DEFAULT_PROVIDER_ID == story_choices.default_provider_id
    assert list_provider_ids() == list(story_choices.provider_ids)

    assert DEFAULT_VIDEO_PROVIDER == video_choices.default_provider_id
    assert get_video_provider_choices() == list(video_choices.provider_ids)

