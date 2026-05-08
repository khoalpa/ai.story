from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional


@dataclass(frozen=True)
class RenderEvent:
    name: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    message: Optional[str] = None


RenderEventSink = Callable[[RenderEvent], None]
RenderEventPredicate = Callable[[RenderEvent], bool]


@dataclass(frozen=True)
class RenderEventSubscription:
    listener: RenderEventSink
    event_names: frozenset[str] | None = None
    event_types: tuple[type[RenderEvent], ...] = ()
    predicate: RenderEventPredicate | None = None

    def matches(self, event: RenderEvent) -> bool:
        if self.event_names is not None and event.name not in self.event_names:
            return False
        if self.event_types and not isinstance(event, self.event_types):
            return False
        if self.predicate is not None and not self.predicate(event):
            return False
        return True


class RenderEventBus:
    def __init__(self) -> None:
        self._subscriptions: list[RenderEventSubscription] = []

    @property
    def subscriptions(self) -> tuple[RenderEventSubscription, ...]:
        return tuple(self._subscriptions)

    def subscribe(
        self,
        listener: RenderEventSink,
        *,
        event_names: str | Iterable[str] | None = None,
        event_types: type[RenderEvent] | tuple[type[RenderEvent], ...] | None = None,
        predicate: RenderEventPredicate | None = None,
    ) -> RenderEventSubscription:
        names = _normalize_event_names(event_names)
        types = _normalize_event_types(event_types)
        subscription = RenderEventSubscription(
            listener=listener,
            event_names=names,
            event_types=types,
            predicate=predicate,
        )
        self._subscriptions.append(subscription)
        return subscription

    def unsubscribe(self, listener: RenderEventSink) -> int:
        before = len(self._subscriptions)
        self._subscriptions = [sub for sub in self._subscriptions if sub.listener is not listener]
        return before - len(self._subscriptions)

    def publish(self, event: RenderEvent) -> None:
        for subscription in tuple(self._subscriptions):
            if subscription.matches(event):
                subscription.listener(event)

    def __call__(self, event: RenderEvent) -> None:
        self.publish(event)


def _normalize_event_names(event_names: str | Iterable[str] | None) -> frozenset[str] | None:
    if event_names is None:
        return None
    if isinstance(event_names, str):
        return frozenset({event_names})
    return frozenset(str(name) for name in event_names)



def _normalize_event_types(
    event_types: type[RenderEvent] | tuple[type[RenderEvent], ...] | None,
) -> tuple[type[RenderEvent], ...]:
    if event_types is None:
        return ()
    if isinstance(event_types, tuple):
        return event_types
    return (event_types,)


@dataclass(frozen=True)
class AppPathsResolvedEvent(RenderEvent):
    name: str = field(default="app.paths.resolved", init=False)
    payload: Mapping[str, Any] = field(default_factory=dict, init=False)
    input_path: Path = Path()
    output_dir: Path = Path()

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", {"input_path": self.input_path, "output_dir": self.output_dir})


@dataclass(frozen=True)
class AppRuntimeResolvedEvent(RenderEvent):
    name: str = field(default="app.runtime.resolved", init=False)
    payload: Mapping[str, Any] = field(default_factory=dict, init=False)
    request: Any = None
    runtime_ctx: Any = None
    voice_maps: Any = None
    voice_rate_map: Any = None
    job_paths: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "payload",
            {
                "request": self.request,
                "runtime_ctx": self.runtime_ctx,
                "voice_maps": self.voice_maps,
                "voice_rate_map": self.voice_rate_map,
                "job_paths": self.job_paths,
            },
        )


@dataclass(frozen=True)
class AppResourcesLoadedEvent(RenderEvent):
    name: str = field(default="app.resources.loaded", init=False)
    payload: Mapping[str, Any] = field(default_factory=dict, init=False)
    abbr_map_path: Path = Path()
    abbr_map: Mapping[str, str] = field(default_factory=dict)
    cli_bgm_config: Optional[Path] = None
    profile_bgm_config: Optional[Path] = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "payload",
            {
                "abbr_map_path": self.abbr_map_path,
                "abbr_map": self.abbr_map,
                "cli_bgm_config": self.cli_bgm_config,
                "profile_bgm_config": self.profile_bgm_config,
            },
        )


@dataclass(frozen=True)
class AppValidationCompletedEvent(RenderEvent):
    name: str = field(default="app.validation.completed", init=False)
    payload: Mapping[str, Any] = field(default_factory=dict, init=False)
    input_path: Path = Path()
    exit_code: int = 0
    errors: tuple[str, ...] = ()
    warnings_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "payload",
            {
                "input_path": self.input_path,
                "exit_code": self.exit_code,
                "errors": self.errors,
                "warnings_count": self.warnings_count,
            },
        )


@dataclass(frozen=True)
class AppPhaseStartedEvent(RenderEvent):
    name: str = field(default="app.phase.started", init=False)
    payload: Mapping[str, Any] = field(default_factory=dict, init=False)
    phase: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        payload = {"phase": self.phase}
        payload.update(dict(self.details))
        object.__setattr__(self, "payload", payload)


@dataclass(frozen=True)
class AppPhaseCompletedEvent(RenderEvent):
    name: str = field(default="app.phase.completed", init=False)
    payload: Mapping[str, Any] = field(default_factory=dict, init=False)
    phase: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        payload = {"phase": self.phase}
        payload.update(dict(self.details))
        object.__setattr__(self, "payload", payload)


@dataclass(frozen=True)
class AppPreviewReadyEvent(RenderEvent):
    name: str = field(default="app.preview.ready", init=False)
    payload: Mapping[str, Any] = field(default_factory=dict, init=False)
    preview: Any = None
    sentiment_tone: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", {"preview": self.preview, "sentiment_tone": self.sentiment_tone})


@dataclass(frozen=True)
class AppDebugSavedEvent(RenderEvent):
    name: str = field(default="app.debug.saved", init=False)
    payload: Mapping[str, Any] = field(default_factory=dict, init=False)
    debug_json: Path = Path()

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", {"debug_json": self.debug_json})


@dataclass(frozen=True)
class AppRenderCompletedEvent(RenderEvent):
    name: str = field(default="app.render.completed", init=False)
    payload: Mapping[str, Any] = field(default_factory=dict, init=False)
    render_artifacts: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", {"render_artifacts": self.render_artifacts})


@dataclass(frozen=True)
class RenderPhaseStartedEvent(RenderEvent):
    name: str = field(default="render.phase.started", init=False)
    payload: Mapping[str, Any] = field(default_factory=dict, init=False)
    phase: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        payload = {"phase": self.phase}
        payload.update(dict(self.details))
        object.__setattr__(self, "payload", payload)


@dataclass(frozen=True)
class RenderPhaseCompletedEvent(RenderEvent):
    name: str = field(default="render.phase.completed", init=False)
    payload: Mapping[str, Any] = field(default_factory=dict, init=False)
    phase: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        payload = {"phase": self.phase}
        payload.update(dict(self.details))
        object.__setattr__(self, "payload", payload)


EventTarget = Optional[RenderEventSink | RenderEventBus]


def emit_event(target: EventTarget, name: str, /, **payload: Any) -> None:
    if target is None:
        return
    emit_render_event(target, RenderEvent(name=name, payload=payload))



def emit_render_event(target: EventTarget, event: RenderEvent) -> None:
    if target is None:
        return
    if isinstance(target, RenderEventBus):
        target.publish(event)
        return
    target(event)
