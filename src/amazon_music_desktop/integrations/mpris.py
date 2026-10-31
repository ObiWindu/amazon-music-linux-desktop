"""MPRIS D-Bus integration: expose page playback to the Linux desktop.

The browser page remains the authoritative playback source. Control actions
(Play, Pause, Next, ...) are forwarded to the page player; the adaptor reports
no success of its own — the PlaybackMonitor's next state update is the
confirmation. Status and metadata are mirrored from the monitor, so the
desktop never holds an independent, contradictory playback state.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtDBus import (
    QDBusAbstractAdaptor,
    QDBusConnection,
    QDBusMessage,
)

from ..browser.playback_monitor import PlaybackState
from ..services.logging_service import get_logger

log = get_logger("mpris")

MPRIS_BUS_NAME = "org.mpris.MediaPlayer2.amazon-music-desktop"
MPRIS_OBJECT_PATH = "/org/mpris/MediaPlayer2"
MPRIS_ROOT_INTERFACE = "org.mpris.MediaPlayer2"
MPRIS_PLAYER_INTERFACE = "org.mpris.MediaPlayer2.Player"
PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"

# Microseconds: MPRIS positions and lengths are int64 microseconds.
USEC = 1_000_000

# states for which the page cannot advance: MPRIS clients map these to
# "Stopped"; IDLE/ERROR/STALLED/LOADING/BUFFERING all qualify.
_STOPPED_STATES = (
    PlaybackState.IDLE,
    PlaybackState.ERROR,
    PlaybackState.STALLED,
    PlaybackState.LOADING,
    PlaybackState.BUFFERING,
)


def playback_status_for(state: PlaybackState) -> str:
    """Map a normalized playback state onto an MPRIS PlaybackStatus."""
    if state == PlaybackState.PLAYING:
        return "Playing"
    if state == PlaybackState.PAUSED:
        return "Paused"
    return "Stopped"


def metadata_for(track: dict[str, Any], trackid: int) -> dict[str, Any]:
    """Build an MPRIS Metadata mapping from available track metadata.

    Only fields with evidence are included: title/artist/album/artwork come
    from the page's Media Session, or from the page probe as a fallback.
    Artwork is forwarded only as http(s) URLs — Media Session often exposes
    blob: or data: URLs that are meaningless to other MPRIS clients and must
    not leak into the shared metadata mapping.
    """
    metadata: dict[str, Any] = {"mpris:trackid": f"{MPRIS_OBJECT_PATH}/track{trackid}"}
    length = track.get("length") or 0
    if length > 0:
        metadata["mpris:length"] = int(length * USEC)
    art_url = track.get("art_url")
    if isinstance(art_url, str) and art_url.startswith(("http://", "https://")):
        metadata["mpris:artUrl"] = art_url
    title = track.get("title")
    if title:
        metadata["xesam:title"] = str(title)
    artist = track.get("artist")
    if artist:
        metadata["xesam:artist"] = [str(artist)]
    album = track.get("album")
    if album:
        metadata["xesam:album"] = str(album)
    return metadata


class MprisRootAdaptor(QDBusAbstractAdaptor):
    """org.mpris.MediaPlayer2 (application interface)."""

    def __init__(self, service: MprisService) -> None:
        super().__init__(service)
        self._service = service

    # --- methods ----------------------------------------------------------

    @Slot()
    def Raise(self) -> None:
        self._service.raise_application()

    @Slot()
    def Quit(self) -> None:
        self._service.quit_application()

    # --- properties -------------------------------------------------------

    def _can_quit(self) -> bool:
        return True

    def _can_raise(self) -> bool:
        return True

    def _has_track_list(self) -> bool:
        return False

    def _identity(self) -> str:
        return "Amazon Music Desktop"

    def _desktop_entry(self) -> str:
        return "amazon-music-desktop"

    def _uri_schemes(self) -> list[str]:
        return []

    def _mime_types(self) -> list[str]:
        return ["audio/aac", "audio/mpeg"]
    CanQuit = Property(bool, _can_quit)
    CanRaise = Property(bool, _can_raise)
    HasTrackList = Property(bool, _has_track_list)
    Identity = Property(str, _identity)
    DesktopEntry = Property(str, _desktop_entry)
    # QStringList marshals to the D-Bus 'as' signature MPRIS expects; a bare
    # Python list would marshal to 'av'.
    SupportedUriSchemes = Property("QStringList", _uri_schemes)
    SupportedMimeTypes = Property("QStringList", _mime_types)


class MprisPlayerAdaptor(QDBusAbstractAdaptor):
    """org.mpris.MediaPlayer2.Player interface.

    Stateless: mutable player state (loop status, shuffle, volume) lives on
    the MprisService so getters and attributes never collide.
    """

    Seeked = Signal("qlonglong")

    def __init__(self, service: MprisService) -> None:
        super().__init__(service)
        self._service = service

    # --- methods: forwarded to the page; state confirms later -------------

    @Slot()
    def Next(self) -> None:
        self._service.play_action("next")

    @Slot()
    def Previous(self) -> None:
        self._service.play_action("previous")

    @Slot()
    def Pause(self) -> None:
        self._service.play_action("pause")

    @Slot()
    def Play(self) -> None:
        self._service.play_action("play")

    @Slot()
    def Stop(self) -> None:
        self._service.play_action("pause")

    @Slot()
    def PlayPause(self) -> None:
        # PlayPause toggles: the monitor's state decides which action the
        # page receives, and its next update confirms the result.
        self._service.play_action(
            "pause" if self._service.state == PlaybackState.PLAYING else "play"
        )

    @Slot("qlonglong")
    def Seek(self, offset_us: int) -> None:
        self._service.seek_by(offset_us / USEC)

    @Slot("o", "x")
    def SetPosition(self, trackid: str, position_us: int) -> None:
        self._service.seek_to(position_us / USEC, trackid=trackid)

    @Slot(str)
    def OpenUri(self, uri: str) -> None:
        log.info("MPRIS OpenUri ignored: %s", uri)

    # --- properties -------------------------------------------------------

    def _playback_status(self) -> str:
        return playback_status_for(self._service.state)

    def _loop_status(self) -> str:
        return self._service.loop_status

    def _set_loop_status(self, value: str) -> None:
        if value in ("None", "Track", "Playlist"):
            self._service.loop_status = value
            self._service.properties_changed(
                MPRIS_PLAYER_INTERFACE, {"LoopStatus": value}
            )

    def _rate(self) -> float:
        return 1.0

    def _set_rate(self, value: float) -> None:
        pass  # the page player has no rate control; keep Rate at 1.0

    def _shuffle(self) -> bool:
        return self._service.shuffle

    def _set_shuffle(self, value: bool) -> None:
        self._service.shuffle = bool(value)
        self._service.properties_changed(
            MPRIS_PLAYER_INTERFACE, {"Shuffle": self._service.shuffle}
        )

    def _metadata(self) -> dict[str, Any]:
        return dict(self._service.metadata)

    def _volume(self) -> float:
        return self._service.volume

    def _set_volume(self, value: float) -> None:
        self._service.volume = max(0.0, min(1.0, float(value)))
        self._service.set_volume(self._service.volume)
        self._service.properties_changed(
            MPRIS_PLAYER_INTERFACE, {"Volume": self._service.volume}
        )

    def _position(self) -> int:
        return int(self._service.position * USEC)

    def _minimum_rate(self) -> float:
        return 1.0

    def _maximum_rate(self) -> float:
        return 1.0

    def _can_go_next(self) -> bool:
        return True

    def _can_go_previous(self) -> bool:
        return True

    def _can_play(self) -> bool:
        return True

    def _can_pause(self) -> bool:
        return True

    def _can_seek(self) -> bool:
        return self._service.duration > 0

    def _can_control(self) -> bool:
        return True

    PlaybackStatus = Property(str, _playback_status)
    LoopStatus = Property(str, _loop_status, _set_loop_status)
    Rate = Property(float, _rate, _set_rate)
    Shuffle = Property(bool, _shuffle, _set_shuffle)
    Metadata = Property("QVariantMap", _metadata)
    Volume = Property(float, _volume, _set_volume)
    Position = Property("qlonglong", _position)
    MinimumRate = Property(float, _minimum_rate)
    MaximumRate = Property(float, _maximum_rate)
    CanGoNext = Property(bool, _can_go_next)
    CanGoPrevious = Property(bool, _can_go_previous)
    CanPlay = Property(bool, _can_play)
    CanPause = Property(bool, _can_pause)
    CanSeek = Property(bool, _can_seek)
    CanControl = Property(bool, _can_control)


class MprisService(QObject):
    """Registers the MPRIS interfaces on the session bus and syncs state."""

    def __init__(self, window: Any = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._window = window
        self._registered = False
        self._trackid = 0
        # mutable Player-interface state (written by MPRIS clients)
        self.loop_status = "None"
        self.shuffle = False
        self.volume = 1.0
        self._root_adaptor = MprisRootAdaptor(self)
        self._player_adaptor = MprisPlayerAdaptor(self)
        self._connection = QDBusConnection.sessionBus()
        if window is not None:
            self.register()

    # --- registration -------------------------------------------------------

    def register(self) -> bool:
        """Register on the session bus; False when no bus is available."""
        if self._registered:
            return True
        if not self._connection.isConnected():
            log.info("no D-Bus session bus: MPRIS unavailable")
            return False
        base = MPRIS_BUS_NAME
        self._connection.unregisterService(base)
        ok = self._connection.registerService(base)
        if not ok:
            log.warning("could not register MPRIS bus name %s", base)
            return False
        self._connection.registerObject(
            MPRIS_OBJECT_PATH,
            self,
            QDBusConnection.RegisterOption.ExportAdaptors,
        )
        self._registered = True
        log.info("MPRIS registered as %s", base)
        return True

    def unregister(self) -> None:
        if not self._registered:
            return
        self._connection.unregisterObject(MPRIS_OBJECT_PATH)
        self._connection.unregisterService(MPRIS_BUS_NAME)
        self._registered = False

    # --- state mirror -------------------------------------------------------

    @property
    def state(self) -> PlaybackState:
        monitor = getattr(self._window, "monitor", None)
        return monitor.state if monitor is not None else PlaybackState.IDLE

    @property
    def position(self) -> float:
        monitor = getattr(self._window, "monitor", None)
        return monitor.position if monitor is not None else 0.0

    @property
    def duration(self) -> float:
        monitor = getattr(self._window, "monitor", None)
        return monitor.duration if monitor is not None else 0.0

    @property
    def metadata(self) -> dict[str, Any]:
        track: dict[str, Any] = {}
        session = getattr(getattr(self._window, "monitor", None), "media_session", None)
        if session:
            # adopt only evidenced Media Session fields; an empty session
            # dict must not shadow the page-probe fallback
            for key, mapped in (
                ("title", "title"),
                ("artist", "artist"),
                ("album", "album"),
                ("artwork", "art_url"),
            ):
                value = session.get(key)
                if value:
                    track[mapped] = value
        track.setdefault("title", getattr(self._window, "_track_title", "") or "")
        track.setdefault("artist", getattr(self._window, "_track_artist", "") or "")
        track["length"] = self.duration
        return metadata_for(track, self._trackid)

    # --- desktop callbacks --------------------------------------------------

    def raise_application(self) -> None:
        window = self._window
        if window is not None:
            try:
                window.show_and_raise()
            except Exception as exc:
                log.warning("MPRIS Raise failed: %s", exc)

    def quit_application(self) -> None:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.quit()

    def play_action(self, action: str) -> None:
        """Forward a transport action to the page player. No claims made."""
        window = self._window
        if window is None:
            return
        try:
            window._player_js(action)
        except Exception as exc:
            log.warning("MPRIS action %s failed to send: %s", action, exc)

    def set_volume(self, volume: float) -> None:
        window = self._window
        if window is None:
            return
        try:
            window._set_player_volume(int(max(0.0, min(1.0, volume)) * 100))
        except Exception as exc:
            log.warning("MPRIS volume change failed: %s", exc)

    def seek_by(self, seconds: float) -> None:
        window = self._window
        if window is None:
            return
        total = self.duration
        if total <= 0:
            return
        target = max(0.0, min(total, self.position + seconds))
        try:
            window._apply_player_seek(target / total)
        except Exception as exc:
            log.warning("MPRIS Seek failed: %s", exc)

    def seek_to(self, seconds: float, trackid: str | None = None) -> None:
        window = self._window
        if window is None:
            return
        total = self.duration
        if total <= 0:
            return
        if trackid is not None and f"{MPRIS_OBJECT_PATH}/track{self._trackid}" not in str(trackid):
            log.debug("MPRIS SetPosition for a stale track ignored")
            return
        target = max(0.0, min(total, seconds))
        try:
            window._apply_player_seek(target / total)
        except Exception as exc:
            log.warning("MPRIS SetPosition failed: %s", exc)

    # --- state updates from the Qt side -------------------------------------

    def advance_track(self) -> None:
        self._trackid += 1
        self.properties_changed(
            MPRIS_PLAYER_INTERFACE,
            {"Metadata": self.metadata, "PlaybackStatus": playback_status_for(self.state)},
        )

    def update_playback(self) -> None:
        """Publish current status/position after a monitor state update."""
        if not self._registered:
            return
        self.properties_changed(
            MPRIS_PLAYER_INTERFACE,
            {
                "PlaybackStatus": playback_status_for(self.state),
                "Metadata": self.metadata,
            },
        )
        # Position changes continuously; MPRIS clients poll it, so it is not
        # announced through PropertiesChanged.

    def emit_seeked(self, seconds: float) -> None:
        if self._registered:
            self._player_adaptor.Seeked.emit(int(seconds * USEC))

    def properties_changed(self, interface: str, changed: dict[str, Any]) -> None:
        """Emit org.freedesktop.DBus.Properties.PropertiesChanged."""
        if not self._registered:
            return
        message = QDBusMessage.createSignal(
            MPRIS_OBJECT_PATH, PROPERTIES_INTERFACE, "PropertiesChanged"
        )
        message.setArguments([interface, changed, []])
        self._connection.send(message)
