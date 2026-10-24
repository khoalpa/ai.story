from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping

import pytest

# Prevent the active test session from writing bytecode into the repository,
# which would otherwise make artifact-hygiene checks flaky.
sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")


@pytest.fixture(scope="session")
def sample_package_members() -> Callable[[str], Mapping[str, bytes]]:
    """Cache verified, immutable archive members; never share writable test files."""
    from studio.reference_samples import load_reference_package

    cached: dict[str, Mapping[str, bytes]] = {}

    def load(name: str) -> Mapping[str, bytes]:
        if name not in cached:
            members, _inspection = load_reference_package(name)
            cached[name] = MappingProxyType(members)
        return cached[name]

    return load


@pytest.fixture(scope="session")
def sample_archives_dir(sample_package_members: Callable[[str], Mapping[str, bytes]]) -> Path:
    from studio.reference_samples import (
        REFERENCE_PACKAGE_DIRECTORY,
        REFERENCE_PACKAGE_NAMES,
    )

    for name in REFERENCE_PACKAGE_NAMES:
        sample_package_members(name)
    return REFERENCE_PACKAGE_DIRECTORY


@pytest.fixture(scope="session")
def sample_story_text(sample_package_members: Callable[[str], Mapping[str, bytes]]) -> str:
    return sample_package_members("story_stage1.zip")["story.json"].decode("utf-8")


@pytest.fixture
def extract_sample_package(
    tmp_path: Path, sample_package_members: Callable[[str], Mapping[str, bytes]],
) -> Callable[[str], Path]:
    def extract(name: str) -> Path:
        members = sample_package_members(name)
        destination = Path(tempfile.mkdtemp(prefix="reference-", dir=tmp_path)).resolve()
        for relative, raw in members.items():
            target = (destination / relative).resolve()
            if not target.is_relative_to(destination):
                raise ValueError(f"Unsafe reference package member: {relative}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        return destination

    return extract


@pytest.fixture
def sample_stage1_project(extract_sample_package: Callable[[str], Path]) -> Path:
    return extract_sample_package("story_stage1.zip")


@pytest.fixture
def sample_stage4_project(extract_sample_package: Callable[[str], Path]) -> Path:
    return extract_sample_package("story_video_prompts.zip")
