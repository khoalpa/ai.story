from __future__ import annotations

import threading
from typing import Any, Callable, Hashable


class VieneuEngineLifecycle:
    """Thread-safe owner of initialized VieNeu engine instances."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.cache: dict[Hashable, Any] = {}

    def get_or_create(self, key: Hashable, factory: Callable[[], Any]) -> Any:
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        with self.lock:
            cached = self.cache.get(key)
            if cached is not None:
                return cached
            engine = factory()
            self.cache[key] = engine
            return engine

    def clear(self) -> None:
        with self.lock:
            self.cache.clear()
