from __future__ import annotations

import logging
import os

_DEFAULT_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_CONFIGURED_KEYS: set[tuple[str, str]] = set()


def resolve_level_name(*env_keys: str, level: str | None = None, default: str = "INFO") -> str:
    candidates = [level, *(os.getenv(key) for key in env_keys), os.getenv("AUDIO_STORY_LOG_LEVEL"), default]
    for candidate in candidates:
        raw = str(candidate or "").strip().upper()
        if raw:
            return raw
    return default


def configure_logging(
    *,
    level: str | None = None,
    env_keys: tuple[str, ...] = (),
    format_env_key: str | None = None,
    force: bool = False,
) -> None:
    key = ("|".join(env_keys), format_env_key or "")
    if key in _CONFIGURED_KEYS and not force:
        return
    level_name = resolve_level_name(*env_keys, level=level)
    log_format = os.getenv(format_env_key, _DEFAULT_FORMAT) if format_env_key else _DEFAULT_FORMAT
    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format=log_format,
        force=force,
    )
    _CONFIGURED_KEYS.add(key)


def get_logger(
    name: str,
    *,
    env_keys: tuple[str, ...] = (),
    format_env_key: str | None = None,
) -> logging.Logger:
    configure_logging(env_keys=env_keys, format_env_key=format_env_key)
    return logging.getLogger(name)
