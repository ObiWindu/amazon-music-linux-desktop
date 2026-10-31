"""Unit tests for MPRIS state synchronization (no D-Bus session needed).

The browser page remains the authoritative playback source: transport actions
are only forwarded, never claimed; status and metadata mirror the monitor.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from amazon_music_desktop.browser.playback_monitor import PlaybackMonitor, PlaybackState
from amazon_music_desktop.integrations.mpris import (
    MPRIS_OBJECT_PATH,
    MprisService,
    metadata_for,
    playback_status_for,
)


class StubWindow:
    """Stand-in for MainWindow: the MPRIS surface the service relies on."""

    def __init__(self):
        self.monitor = PlaybackMonitor()
        self._track_title = "Song"
        self._track_artist = "Artist"
        self.actions: list[str] = []
        self.seeks: list[float] = []
        self.volumes: list[int] = []
        self.raised = False

    def _player_js(self, action: str) -> None:
        self.actions.append(action)

    def _apply_player_seek(self, fraction: float) -> None:
        self.seeks.append(fraction)

    def _set_player_volume(self, value: int) -> None:
        self.volumes.append(value)

    def show_and_raise(self) -> None:
        self.raised = True


@pytest.fixture()
def window() -> StubWindow:
    return StubWindow()


@pytest.fixture()
def service(window) -> MprisService:
    # constructed without a window so no bus registration is attempted
    s = MprisService(None)
    s._window = window
    return s


def disconnected_connection(sent: list):
    return SimpleNamespace(
        isConnected=lambda: False,
        registerService=lambda name: False,
        unregisterService=lambda name: None,
        registerObject=lambda *a, **k: None,
        unregisterObject=lambda *a, **k: None,
        send=sent.append,
    )


def connected_connection(sent: list):
    return SimpleNamespace(
        isConnected=lambda: True,
        registerService=lambda name: True,
        unregisterService=lambda name: None,
        registerObject=lambda *a, **k: None,
        unregisterObject=lambda *a, **k: None,
        send=sent.append,
    )


def test_playback_status_mapping():
    assert playback_status_for(PlaybackState.PLAYING) == "Playing"
    assert playback_status_for(PlaybackState.PAUSED) == "Paused"
    for state in (
        PlaybackState.IDLE,
        PlaybackState.LOADING,
        PlaybackState.BUFFERING,
        PlaybackState.STALLED,
        PlaybackState.ERROR,
        PlaybackState.ENDED,
    ):
        assert playback_status_for(state) == "Stopped"


def test_metadata_includes_only_evidenced_fields(service):
    service._window.monitor.handle_event("playing", position=30.0, duration=200.0)
    service._window.monitor.set_media_session(
        {"title": "Track", "artist": "Artist", "album": "Album"}
    )
    metadata = service.metadata
    assert metadata["xesam:title"] == "Track"
    assert metadata["xesam:artist"] == ["Artist"]
    assert metadata["xesam:album"] == "Album"
    assert metadata["mpris:length"] == 200_000_000
    assert metadata["mpris:trackid"].startswith(MPRIS_OBJECT_PATH)
    # no artwork evidence: mpris:artUrl must not appear
    assert "mpris:artUrl" not in metadata


def test_metadata_artwork_from_media_session(service):
    service._window.monitor.set_media_session(
        {"title": "Track", "artwork": "https://example/img.jpg"}
    )
    assert service.metadata["mpris:artUrl"] == "https://example/img.jpg"


def test_metadata_artwork_blob_and_data_urls_dropped():
    for junk in ("blob:https://music.amazon.fr/uuid-1", "data:image/jpeg;base64,AAA"):
        metadata = metadata_for({"title": "Song", "art_url": junk}, 0)
        assert "mpris:artUrl" not in metadata
    assert metadata_for({"title": "Song"}, 1)["mpris:trackid"].endswith("/track1")


def test_emit_seeked_noop_without_registration(service):
    service.emit_seeked(10.0)  # must not raise without a bus registration


def test_emit_seeked_and_update_playback_send_when_registered(window):
    from amazon_music_desktop.integrations.mpris import MprisService

    sent: list = []
    service = MprisService(None)
    service._window = window
    service._connection = connected_connection(sent)
    assert service.register() is True
    window.monitor.handle_event("playing", position=4.0, duration=200.0)
    service.update_playback()
    service.emit_seeked(4.0)
    assert sent  # PropertiesChanged + Seeked reached the bus
    service.unregister()


def test_metadata_without_session_uses_probe_fallback(service):
    service._window.monitor.handle_event("playing", position=1.0, duration=100.0)
    metadata = service.metadata
    assert metadata["xesam:title"] == "Song"
    assert metadata["xesam:artist"] == ["Artist"]
    assert "xesam:album" not in metadata


def test_metadata_length_hidden_without_duration(service):
    metadata = service.metadata
    assert "mpris:length" not in metadata


def test_actions_forward_to_page_without_claims(window, service):
    service._player_adaptor.PlayPause()   # IDLE -> play
    service._player_adaptor.Play()        # play
    service._player_adaptor.Pause()       # pause
    service._player_adaptor.PlayPause()   # PLAYING -> pause
    service._player_adaptor.Next()
    service._player_adaptor.Previous()
    assert window.actions == ["play", "play", "pause", "play", "next", "previous"]


def test_actions_without_window_do_nothing():
    service = MprisService(None)
    service._window = None
    service.play_action("play")
    service.seek_by(5.0)
    service.seek_to(10.0)
    service.set_volume(0.5)
    service.raise_application()
    service.quit_application()


def test_playpause_toggle_depends_on_state(window, service):
    window.monitor.handle_event("playing")
    service._player_adaptor.PlayPause()
    window.monitor.handle_event("pause")
    service._player_adaptor.PlayPause()
    assert window.actions == ["pause", "play"]


def test_seek_math(window, service):
    window.monitor.handle_event("playing", position=10.0, duration=100.0)
    service._player_adaptor.Seek(5_000_000)  # +5s
    assert window.seeks == [pytest.approx(0.15)]


def test_setposition_forwarded_for_current_track(window, service):
    window.monitor.handle_event("playing", position=10.0, duration=100.0)
    trackid = f"{MPRIS_OBJECT_PATH}/track{service._trackid}"
    service._player_adaptor.SetPosition(trackid, 20_000_000)
    assert window.seeks == [pytest.approx(0.2)]


def test_setposition_stale_track_ignored(window, service):
    window.monitor.handle_event("playing", position=10.0, duration=100.0)
    service._player_adaptor.SetPosition(f"{MPRIS_OBJECT_PATH}/track999", 20_000_000)
    assert window.seeks == []


def test_seek_requires_duration(window, service):
    service._player_adaptor.Seek(5_000_000)
    service._player_adaptor.SetPosition(f"{MPRIS_OBJECT_PATH}/track0", 5_000_000)
    assert window.seeks == []


def test_volume_round_trip(window, service):
    service._player_adaptor._set_volume(0.5)
    assert window.volumes == [50]
    assert service._player_adaptor.Volume == pytest.approx(0.5)


def test_root_properties(service):
    root = service._root_adaptor
    assert root.CanQuit is True
    assert root.CanRaise is True
    assert root.HasTrackList is False
    assert root.Identity == "Amazon Music Desktop"
    assert root.DesktopEntry == "amazon-music-desktop"
    assert root.SupportedUriSchemes == []
    assert "audio/aac" in root.SupportedMimeTypes


def test_player_properties(window, service):
    player = service._player_adaptor
    assert player.CanControl is True
    assert player.CanPlay is True
    assert player.CanPause is True
    assert player.CanGoNext is True
    assert player.CanGoPrevious is True
    assert player.CanSeek is False  # no duration yet
    assert player.Rate == 1.0
    assert player.MinimumRate == 1.0
    assert player.MaximumRate == 1.0


def test_playback_status_property_follows_monitor(window, service):
    assert service._player_adaptor.PlaybackStatus == "Stopped"
    window.monitor.handle_event("playing")
    assert service._player_adaptor.PlaybackStatus == "Playing"
    window.monitor.handle_event("pause")
    assert service._player_adaptor.PlaybackStatus == "Paused"
    assert service.state == PlaybackState.PAUSED


def test_can_seek_follows_duration(window, service):
    assert service._player_adaptor.CanSeek is False
    window.monitor.handle_event("playing", position=0.0, duration=180.0)
    assert service._player_adaptor.CanSeek is True


def test_update_playback_before_registration_is_noop(service):
    service.update_playback()


def test_advance_track_bumps_trackid_and_metadata(window, service):
    window.monitor.handle_event("playing")
    first = service.metadata["mpris:trackid"]
    service.advance_track()
    assert service.metadata["mpris:trackid"] != first


def test_registration_on_live_bus(window):
    sent: list = []
    service = MprisService(None)
    service._window = window
    service._connection = connected_connection(sent)
    assert service.register() is True
    assert service._registered is True
    service.update_playback()
    service.properties_changed(
        "org.mpris.MediaPlayer2.Player", {"PlaybackStatus": "Playing"}
    )
    service.emit_seeked(1.0)
    assert sent  # PropertiesChanged reached the bus
    service.unregister()
    assert service._registered is False


def test_no_session_bus_is_graceful(window):
    sent: list = []
    service = MprisService(None)
    service._window = window
    service._connection = disconnected_connection(sent)
    assert service.register() is False
    assert service._registered is False
    # updates without a registration must not send anything
    service.update_playback()
    service.properties_changed(
        "org.mpris.MediaPlayer2.Player", {"PlaybackStatus": "Playing"}
    )
    service.emit_seeked(1.0)
    assert sent == []


def test_metadata_for_shape():
    metadata = metadata_for(
        {
            "title": "Song",
            "artist": "Artist",
            "album": "Album",
            "art_url": "https://example/cover.jpg",
            "length": 91.5,
        },
        3,
    )
    assert metadata["mpris:trackid"] == f"{MPRIS_OBJECT_PATH}/track3"
    assert metadata["mpris:length"] == 91_500_000
    assert metadata["mpris:artUrl"] == "https://example/cover.jpg"
    assert metadata["xesam:title"] == "Song"
    assert metadata["xesam:artist"] == ["Artist"]
    assert metadata["xesam:album"] == "Album"


def test_metadata_for_minimal_track():
    metadata = metadata_for({"title": "Song"}, 0)
    assert metadata == {
        "mpris:trackid": f"{MPRIS_OBJECT_PATH}/track0",
        "xesam:title": "Song",
    }
