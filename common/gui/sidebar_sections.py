from __future__ import annotations

from enum import Enum


class SidebarSection(str, Enum):
    PROFILES = "Profiles & Assets"
    PROVIDER = "Provider"
    INPUTS_OUTPUTS = "Inputs / Outputs"
    GENERATION = "Generation"
    RENDER = "Render"
    ADVANCED = "Advanced"
    RUNTIME = "Runtime"

    def __str__(self) -> str:
        return self.value
