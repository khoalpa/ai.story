from __future__ import annotations

import logging

from common.logging_utils import configure_logging as _configure_logging
from common.logging_utils import get_logger as _get_logger


def configure_logging(level: str | None = None, *, force: bool = False) -> None:
    _configure_logging(
        level=level,
        env_keys=("RENDER_VIDEO_LOG_LEVEL", "AUDIO_STORY_LOG_LEVEL"),
        force=force,
    )


def get_logger(name: str) -> logging.Logger:
    return _get_logger(name, env_keys=("RENDER_VIDEO_LOG_LEVEL", "AUDIO_STORY_LOG_LEVEL"))
