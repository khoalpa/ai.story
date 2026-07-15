from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderChoiceGroup:
    default_provider_id: str
    provider_ids: tuple[str, ...]
    ignored_module_names: tuple[str, ...] = ()

    def sort_index(self, provider_id: str) -> int:
        try:
            return self.provider_ids.index(provider_id)
        except ValueError:
            return len(self.provider_ids)

    def is_enabled(self, provider_id: str) -> bool:
        return provider_id in self.provider_ids


PROVIDER_CHOICE_GROUPS: dict[str, ProviderChoiceGroup] = {
    "audio_tts": ProviderChoiceGroup(
        default_provider_id="vieneu",
        provider_ids=("vieneu", "edge"),
        ignored_module_names=("base", "registry"),
    ),
    "image_sd": ProviderChoiceGroup(
        default_provider_id="stable_diffusion_local",
        provider_ids=(
            "stable_diffusion_local",
            "stable_diffusion_remote",
            "comfyui_local",
            "comfyui_remote",
        ),
        ignored_module_names=("registry",),
    ),
    "story_llm": ProviderChoiceGroup(
        default_provider_id="lmdeploy",
        provider_ids=(
            "lmdeploy",
            "lm_studio",
            "openai_chatgpt",
            "custom_compatible",
        ),
    ),
    "video": ProviderChoiceGroup(
        default_provider_id="ffmpeg_local",
        provider_ids=("ffmpeg_local",),
        ignored_module_names=("base", "registry"),
    ),
}


def get_provider_choice_group(group_id: str) -> ProviderChoiceGroup:
    try:
        return PROVIDER_CHOICE_GROUPS[group_id]
    except KeyError as exc:
        raise KeyError(f"Unknown provider choice group: {group_id}") from exc
