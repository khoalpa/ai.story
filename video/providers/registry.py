from __future__ import annotations

from importlib import import_module

from video.provider_catalog import get_provider_choice_group
from video.providers.base import VideoProviderDescriptor, normalize_provider_token

_CHOICES = get_provider_choice_group("video")
DEFAULT_VIDEO_PROVIDER = _CHOICES.default_provider_id


def _discover_provider_descriptors() -> dict[str, VideoProviderDescriptor]:
    import video.providers as providers_pkg

    descriptors: dict[str, VideoProviderDescriptor] = {}
    for name in _CHOICES.provider_ids:
        module = import_module(f"{providers_pkg.__name__}.{name}")
        descriptor = getattr(module, "DESCRIPTOR", None)
        if isinstance(descriptor, VideoProviderDescriptor):
            descriptors[descriptor.provider_id] = descriptor
    return dict(sorted(descriptors.items(), key=lambda item: (_CHOICES.sort_index(item[0]), item[1].sort_order, item[0])))


def get_video_provider_descriptors() -> dict[str, VideoProviderDescriptor]:
    return _discover_provider_descriptors()


def get_video_provider_choices() -> list[str]:
    return list(get_video_provider_descriptors())


def normalize_video_provider(value: object) -> str:
    descriptors = get_video_provider_descriptors()
    if not descriptors:
        raise RuntimeError("No video providers were discovered in video.providers.")

    aliases: dict[str, str] = {}
    for provider_id, descriptor in descriptors.items():
        aliases[normalize_provider_token(provider_id)] = provider_id
        aliases[normalize_provider_token(descriptor.label)] = provider_id
        for alias in descriptor.aliases:
            aliases[normalize_provider_token(alias)] = provider_id

    normalized = normalize_provider_token(value or DEFAULT_VIDEO_PROVIDER)
    fallback = DEFAULT_VIDEO_PROVIDER if DEFAULT_VIDEO_PROVIDER in descriptors else next(iter(descriptors))
    return aliases.get(normalized, fallback)


def get_video_provider_descriptor(provider: object) -> VideoProviderDescriptor:
    descriptors = get_video_provider_descriptors()
    return descriptors[normalize_video_provider(provider)]
