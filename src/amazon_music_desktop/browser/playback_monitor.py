"""Playback monitoring for Amazon Music web player media elements.

The monitor consumes browser-side media lifecycle events and publishes a
normalized playback state. It never injects privileged Python objects into the
webpage; browser instrumentation is limited to reading media element state and
reporting events through Qt's normal JavaScript evaluation channel.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PlaybackState(str, Enum):
    IDLE = "IDLE"
    LOADING = "LOADING"
    BUFFERING = "BUFFERING"
    PLAYING = "PLAYING"
    PAUSED = "PAUSED"
    STALLED = "STALLED"
    ERROR = "ERROR"
    ENDED = "ENDED"


# Backwards/alternative names used by callers and tests.
PlaybackStatus = PlaybackState


MEDIA_EVENTS: tuple[str, ...] = (
    "loadstart",
    "loadedmetadata",
    "canplay",
    "play",
    "playing",
    "waiting",
    "stalled",
    "pause",
    "ended",
    "error",
    "encrypted",
    "timeupdate",
    "progress",
)


@dataclass
class MediaEvent:
    name: str
    timestamp: float
    element_id: str | None = None
    position: float | None = None
    duration: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedPlaybackState:
    state: PlaybackState = PlaybackState.IDLE
    position: float = 0.0
    duration: float = 0.0
    last_event: str | None = None
    last_event_time: float | None = None
    last_error: str | None = None
    media_session: dict[str, Any] = field(default_factory=dict)
    events: list[MediaEvent] = field(default_factory=list)


# Browser-side, read-only instrumentation. It attaches listeners to media
# elements and stores the latest event/position on a dedicated global object.
# No Python objects are injected into the page.
PLAYBACK_MONITOR_JS = (
    "(function(){"
    "window.__amdPlaybackMonitor = window.__amdPlaybackMonitor || {"
    "events:[], state:'IDLE', position:0, duration:0, lastEvent:null, "
    "lastEventTime:0, mediaSession:null, error:null};"
    "var m=window.__amdPlaybackMonitor;"
    "function record(name, el){"
    "var now=Date.now()/1000;"
    "m.lastEvent=name; m.lastEventTime=now;"
    "if(el){m.position=Number.isFinite(el.currentTime)?el.currentTime:0;"
    "m.duration=Number.isFinite(el.duration)?el.duration:0;}"
    "m.events.push({name:name, time:now, position:m.position, duration:m.duration});"
    "if(m.events.length>200)m.events=m.events.slice(-200);"
    "}"
    "function attach(el){"
    "if(!el||el.__amdMonitored)return; el.__amdMonitored=true;"
    "['loadstart','loadedmetadata','canplay','play','playing','waiting','stalled',"
    "'pause','ended','error','encrypted','timeupdate'].forEach(function(ev){"
    "el.addEventListener(ev,function(){record(ev,el);},true);});"
    "}"
    "function scan(){document.querySelectorAll('audio,video').forEach(attach);}"
    "scan();"
    "if(!window.__amdPlaybackMonitorObserver){"
    "window.__amdPlaybackMonitorObserver=new MutationObserver(scan);"
    "if(document.documentElement)window.__amdPlaybackMonitorObserver.observe("
    "document.documentElement,{childList:true,subtree:true});"
    "}"
    "if(navigator.mediaSession){"
    "var md=navigator.mediaSession.metadata;"
    "var art=(md&&md.artwork&&md.artwork.length>0)?md.artwork[0].src:null;"
    "m.mediaSession={title:md&&md.title,artist:md&&md.artist,album:md&&md.album,"
    "artwork:art,playbackState:navigator.mediaSession.playbackState};"
    "}"
    "return JSON.stringify(m);"
    "})()"
)

MEDIA_EVENT_INSTRUMENTATION_JS = PLAYBACK_MONITOR_JS
PLAYBACK_MONITOR_INJECTION_JS = PLAYBACK_MONITOR_JS


class PlaybackMonitor:
    """Normalize browser media events into a small state machine."""

    def __init__(
        self,
        on_state_changed: Callable[[PlaybackState], None] | None = None,
        stall_timeout: float = 5.0,
        page: Any = None,
    ) -> None:
        self._state = PlaybackState.IDLE
        self._position = 0.0
        self._duration = 0.0
        self._last_event: str | None = None
        self._last_event_time: float | None = None
        self._last_progress_time: float | None = None
        self._last_progress_position: float | None = None
        self._last_error: str | None = None
        self._media_session: dict[str, Any] = {}
        self._events: list[MediaEvent] = []
        self._media_elements: list[Any] = []
        self._on_state_changed = on_state_changed
        self._stall_timeout = float(stall_timeout)
        self._page = page
        self._known_states = set(PlaybackState)
        self._browser_cursor = 0.0

    @property
    def state(self) -> PlaybackState:
        return self._state

    @property
    def current_state(self) -> PlaybackState:
        return self._state

    @property
    def position(self) -> float:
        return self._position

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def last_event(self) -> str | None:
        return self._last_event

    @property
    def last_event_time(self) -> float | None:
        return self._last_event_time

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def media_session(self) -> dict[str, Any]:
        return dict(self._media_session)

    @property
    def events(self) -> list[MediaEvent]:
        return list(self._events)

    @property
    def media_elements(self) -> list[Any]:
        return list(self._media_elements)

    @property
    def normalized_state(self) -> NormalizedPlaybackState:
        return NormalizedPlaybackState(
            state=self._state,
            position=self._position,
            duration=self._duration,
            last_event=self._last_event,
            last_event_time=self._last_event_time,
            last_error=self._last_error,
            media_session=dict(self._media_session),
            events=list(self._events),
        )

    def observe_media_elements(self, elements: Any) -> None:
        if elements is None:
            elements = []
        if isinstance(elements, (list, tuple, set)):
            self._media_elements = list(elements)
        else:
            self._media_elements = [elements]

    def set_media_elements(self, elements: Any) -> None:
        self.observe_media_elements(elements)

    def set_media_session(self, metadata: Any) -> None:
        if isinstance(metadata, dict):
            self._media_session = dict(metadata)
        elif metadata is None:
            self._media_session = {}
        else:
            self._media_session = {"value": metadata}

    def capture_media_session(self, metadata: Any) -> None:
        self.set_media_session(metadata)

    def update_position(self, position: Any = None, duration: Any = None, timestamp: float | None = None) -> None:
        try:
            if position is not None:
                self._position = float(position)
        except (TypeError, ValueError):
            pass
        try:
            if duration is not None:
                self._duration = float(duration)
        except (TypeError, ValueError):
            pass
        now = time.time() if timestamp is None else float(timestamp)
        self._last_progress_time = now
        self._last_progress_position = self._position

    def set_position(self, position: Any, duration: Any = None) -> None:
        self.update_position(position, duration)

    def record_event(self, event: Any, **kwargs: Any) -> None:
        self.handle_event(event, **kwargs)

    def process_event(self, event: Any, **kwargs: Any) -> None:
        self.handle_event(event, **kwargs)

    def on_event(self, event: Any, **kwargs: Any) -> None:
        self.handle_event(event, **kwargs)

    def handle_media_event(self, event: Any, **kwargs: Any) -> None:
        self.handle_event(event, **kwargs)

    def handle_event(
        self,
        event: Any,
        *,
        timestamp: float | None = None,
        element_id: str | None = None,
        position: Any = None,
        duration: Any = None,
        error: str | None = None,
        media_session: Any = None,
        details: dict[str, Any] | None = None,
    ) -> PlaybackState:
        name = str(event).strip().lower() if event is not None else ""
        # Accept either an event name or a dict payload.
        if isinstance(event, dict):
            payload = event
            name = str(payload.get("name") or payload.get("event") or payload.get("type") or "").strip().lower()
            timestamp = payload.get("timestamp", timestamp)
            element_id = payload.get("element_id", payload.get("id", element_id))
            position = payload.get("position", payload.get("currentTime", position))
            duration = payload.get("duration", duration)
            error = payload.get("error", error)
            media_session = payload.get("media_session", payload.get("mediaSession", media_session))
            details = payload.get("details", details)

        now = time.time() if timestamp is None else float(timestamp)
        if position is not None or duration is not None:
            self.update_position(position, duration, timestamp=now)

        if media_session is not None:
            self.set_media_session(media_session)

        media_event = MediaEvent(
            name=name,
            timestamp=now,
            element_id=element_id,
            position=self._position if position is not None else None,
            duration=self._duration if duration is not None else None,
            details=dict(details or {}),
        )
        self._events.append(media_event)
        if len(self._events) > 1000:
            self._events = self._events[-1000:]
        self._last_event = name or self._last_event
        self._last_event_time = now

        previous = self._state
        if name == "loadstart":
            self._state = PlaybackState.LOADING
        elif name in ("loadedmetadata", "loadeddata"):
            if self._state not in (PlaybackState.PLAYING, PlaybackState.PAUSED, PlaybackState.ENDED):
                self._state = PlaybackState.LOADING
        elif name == "canplay":
            if self._state in (PlaybackState.LOADING, PlaybackState.BUFFERING, PlaybackState.IDLE):
                self._state = PlaybackState.BUFFERING
        elif name in ("play",) or name in ("playing",):
            self._state = PlaybackState.PLAYING
        elif name in ("waiting", "stalled"):
            if name == "stalled":
                self._state = PlaybackState.STALLED
            else:
                self._state = PlaybackState.BUFFERING
        elif name == "pause":
            self._state = PlaybackState.PAUSED
        elif name == "ended":
            self._state = PlaybackState.ENDED
        elif name == "error":
            self._state = PlaybackState.ERROR
            self._last_error = error or "media error"
        elif name == "encrypted":
            if self._state == PlaybackState.IDLE:
                self._state = PlaybackState.LOADING
        elif name in ("timeupdate", "progress"):
            if self._state in (PlaybackState.BUFFERING, PlaybackState.LOADING):
                self._state = PlaybackState.PLAYING
            self._last_progress_time = now
            self._last_progress_position = self._position
        # unknown events do not change state and are not errors

        if error and name != "error":
            # A reported error payload is evidence of failure.
            self._state = PlaybackState.ERROR
            self._last_error = error

        if self._state != previous and self._on_state_changed is not None:
            try:
                self._on_state_changed(self._state)
            except Exception:
                pass
        return self._state

    def detect_stalled(self, now: float | None = None, timeout: float | None = None) -> bool:
        current = time.time() if now is None else float(now)
        wait = self._stall_timeout if timeout is None else float(timeout)
        if self._state != PlaybackState.PLAYING:
            return False
        if self._last_progress_time is None:
            self._last_progress_time = current
            return False
        if current - self._last_progress_time > wait:
            self._state = PlaybackState.STALLED
            self._last_error = self._last_error or "playback stalled"
            if self._on_state_changed is not None:
                try:
                    self._on_state_changed(self._state)
                except Exception:
                    pass
            return True
        return False

    def is_stalled(self, now: float | None = None, timeout: float | None = None) -> bool:
        return self.detect_stalled(now, timeout)

    def reset(self) -> None:
        self._state = PlaybackState.IDLE
        self._position = 0.0
        self._duration = 0.0
        self._last_event = None
        self._last_event_time = None
        self._last_progress_time = None
        self._last_progress_position = None
        self._last_error = None
        self._media_session = {}
        self._events = []
        self._media_elements = []
        self._browser_cursor = 0.0

    def publish_state(self, callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
        payload = {
            "state": self._state.value,
            "position": self._position,
            "duration": self._duration,
            "last_event": self._last_event,
            "last_event_time": self._last_event_time,
            "last_error": self._last_error,
            "media_session": dict(self._media_session),
        }
        if callback is not None:
            try:
                callback(payload)
            except Exception:
                pass
        return payload

    def to_dict(self) -> dict[str, Any]:
        return self.publish_state()

    # Common aliases expected by integrations.
    def update_from_browser(self, state: Any) -> None:
        """Adopt browser-side evidence from the monitor read-back payload.

        Python owns the normalized state machine: the payload's event list is
        replayed through handle_event in order (deduplicated by timestamp),
        while payload['state'] is ignored — the browser-side instrumentation
        stores events and positions only, it does not compute a state.
        """
        if not isinstance(state, dict):
            return
        events = state.get("events")
        if isinstance(events, list):
            for item in events:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip().lower()
                if not name:
                    continue
                try:
                    ts = float(item.get("time") or 0.0)
                except (TypeError, ValueError):
                    continue
                if ts <= self._browser_cursor:
                    continue  # already replayed
                self._browser_cursor = ts
                self.handle_event(
                    name,
                    timestamp=ts,
                    position=item.get("position"),
                    duration=item.get("duration"),
                    error=item.get("error"),
                )
        session = state.get("mediaSession")
        if session is not None:
            self.set_media_session(session)
        position = state.get("position")
        duration = state.get("duration")
        if position is not None or duration is not None:
            # the payload's element state is evidence too, independent of the
            # event stream: adopt it so polling keeps the position current
            self.update_position(position, duration)
        error = state.get("error")
        if error:
            self._last_error = str(error)

    def start(self, page: Any = None) -> None:
        if page is not None:
            self._page = page
        self.reset()

    def stop(self) -> None:
        self.reset()

    def attach_page(self, page: Any) -> None:
        self._page = page


# Backwards-compatible alias.
PlaybackMonitorComponent = PlaybackMonitor
MediaPlaybackMonitor = PlaybackMonitor
PlaybackStateMonitor = PlaybackMonitor
