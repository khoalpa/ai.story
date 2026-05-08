from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass

_DEFAULT_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_CONFIGURED_KEYS: set[tuple[str, str]] = set()


def resolve_level_name(*env_keys: str, level: str | None = None, default: str = "INFO") -> str:
    candidates = [level, *(os.getenv(key) for key in env_keys), os.getenv("AUDIO_STORY_LOG_LEVEL"), default]
    for candidate in candidates:
        raw = str(candidate or "").strip().upper()
        if raw:
            return raw
    return default


def _configure_base_logging(
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


def _get_base_logger(
    name: str,
    *,
    env_keys: tuple[str, ...] = (),
    format_env_key: str | None = None,
) -> logging.Logger:
    _configure_base_logging(env_keys=env_keys, format_env_key=format_env_key)
    return logging.getLogger(name)


@dataclass
class CliProgressRenderer:
    last_len: int = 0
    active_label: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(getattr(sys.stdout, 'isatty', lambda: False)())

    def update(self, label: str, message: str) -> bool:
        if not self.enabled:
            return False
        if self.active_label != label:
            self.finish()
        text = message.rstrip()
        pad = ' ' * max(0, self.last_len - len(text))
        sys.stdout.write('\r' + text + pad)
        sys.stdout.flush()
        self.last_len = len(text)
        self.active_label = label
        return True

    def finish(self) -> None:
        if not self.enabled or self.active_label is None:
            self.last_len = 0
            self.active_label = None
            return
        sys.stdout.write('\n')
        sys.stdout.flush()
        self.last_len = 0
        self.active_label = None


_PROGRESS = CliProgressRenderer()


def configure_logging(level: str | None = None, *, force: bool = False) -> None:
    _configure_base_logging(
        level=level,
        env_keys=("AUDIO_STORY_LOG_LEVEL",),
        format_env_key="AUDIO_STORY_LOG_FORMAT",
        force=force,
    )


def get_logger(name: str) -> logging.Logger:
    return _get_base_logger(
        name,
        env_keys=("AUDIO_STORY_LOG_LEVEL",),
        format_env_key="AUDIO_STORY_LOG_FORMAT",
    )


def set_log_level(level: str) -> None:
    configure_logging(force=True, level=level)


def render_cli_progress(label: str, message: str) -> bool:
    return _PROGRESS.update(label, message)


def finish_cli_progress() -> None:
    _PROGRESS.finish()
