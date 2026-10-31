"""Unit tests for the PlaybackMonitor (no browser or Amazon account needed)."""

from __future__ import annotations

import pytest

from amazon_music_desktop.browser.playback_monitor import (
    PLAYBACK_MONITOR_JS,
    PlaybackMonitor,
    PlaybackState,
)


def transitions(events: list[str]) -> PlaybackMonitor:
    monitor = PlaybackMonitor()
    for name in events:
        monitor.handle_event(name)
    return monitor


def test_loadstart_and_metadata_load():
    monitor = transitions(["loadstart", "loadedmetadata"])
    assert monitor.state == PlaybackState.LOADING


def test_play_and_playing_advance():
    # 'play' alone is only a request (BUFFERING); 'playing' confirms output.
    monitor = transitions(["play"])
    assert monitor.state == PlaybackState.BUFFERING
    monitor.handle_event("playing")
    assert monitor.state == PlaybackState.PLAYING


def test_play_alone_never_reports_playing():
    monitor = transitions(["play"])
    assert monitor.state != PlaybackState.PLAYING
    assert monitor.state == PlaybackState.BUFFERING


def test_canplay_from_loading_buffers():
    monitor = transitions(["loadstart", "canplay"])
    assert monitor.state == PlaybackState.BUFFERING


def test_waiting_buffers():
    monitor = transitions(["playing", "waiting"])
    assert monitor.state == PlaybackState.BUFFERING


def test_stalled_event_maps_to_stalled():
    monitor = transitions(["playing", "stalled"])
    assert monitor.state == PlaybackState.STALLED


def test_pause_maps_to_paused():
    monitor = transitions(["playing", "pause"])
    assert monitor.state == PlaybackState.PAUSED


def test_ended_maps_to_ended():
    monitor = transitions(["playing", "ended"])
    assert monitor.state == PlaybackState.ENDED


def test_error_maps_to_error_with_message():
    monitor = transitions(["playing", "error"])
    assert monitor.state == PlaybackState.ERROR
    assert monitor.last_error == "media error"
    payload = monitor.publish_state()
    assert payload["last_error"] == "media error"


def test_unknown_event_does_not_change_state_or_error():
    monitor = transitions(["play", "playing"])
    assert monitor.state == PlaybackState.PLAYING
    assert monitor.handle_event("totally-unknown") == PlaybackState.PLAYING
    assert monitor.last_error is None


def test_encrypted_from_idle_loads():
    monitor = transitions(["encrypted"])
    assert monitor.state == PlaybackState.LOADING


def test_timeupdate_promotes_buffering_to_playing():
    monitor = transitions(["play", "waiting"])
    monitor.handle_event("timeupdate")
    assert monitor.state == PlaybackState.PLAYING


def test_error_payload_on_non_error_event_is_evidence():
    monitor = PlaybackMonitor()
    monitor.handle_event("waiting", error="decoder failure")
    assert monitor.state == PlaybackState.ERROR
    assert monitor.last_error == "decoder failure"


def test_events_recorded_with_timestamps():
    monitor = PlaybackMonitor()
    monitor.handle_event("play", timestamp=100.0)
    monitor.handle_event("pause", timestamp=105.0)
    assert [e.name for e in monitor.events] == ["play", "pause"]
    assert monitor.events[0].timestamp == 100.0
    assert monitor.last_event_time == 105.0


def test_position_updates():
    monitor = PlaybackMonitor()
    monitor.update_position(12.5, 180.0)
    assert monitor.position == pytest.approx(12.5)
    assert monitor.duration == pytest.approx(180.0)
    assert monitor.normalized_state.position == pytest.approx(12.5)


def test_non_numeric_position_ignored():
    monitor = PlaybackMonitor()
    monitor.update_position("not-a-number", None)
    assert monitor.position == 0.0
    assert monitor.duration == 0.0


def test_detect_stalled_after_timeout():
    monitor = PlaybackMonitor(stall_timeout=5.0)
    monitor.handle_event("playing", timestamp=100.0)
    monitor.update_position(10.0, timestamp=100.0)
    assert monitor.detect_stalled(now=104.0) is False
    assert monitor.detect_stalled(now=105.5) is True
    assert monitor.state == PlaybackState.STALLED


def test_detect_stalled_false_when_paused():
    monitor = PlaybackMonitor(stall_timeout=1.0)
    monitor.handle_event("pause", timestamp=100.0)
    assert monitor.detect_stalled(now=200.0) is False
    assert monitor.state == PlaybackState.PAUSED


def test_detect_stalled_false_when_progressing():
    monitor = PlaybackMonitor(stall_timeout=5.0)
    monitor.handle_event("playing", timestamp=100.0)
    monitor.update_position(10.0, timestamp=100.0)
    monitor.update_position(11.0, timestamp=101.0)
    assert monitor.detect_stalled(now=103.0) is False


def test_reset_clears_everything():
    monitor = transitions(["play", "error"])
    monitor.update_position(5.0, 120.0)
    monitor.set_media_session({"title": "Song"})
    monitor.reset()
    assert monitor.state == PlaybackState.IDLE
    assert monitor.position == 0.0
    assert monitor.duration == 0.0
    assert monitor.events == []
    assert monitor.last_error is None
    assert monitor.media_session == {}


def test_state_changed_callback_fires_on_transitions_only():
    seen: list[PlaybackState] = []
    monitor = PlaybackMonitor(on_state_changed=seen.append)
    for name in ("play", "playing", "timeupdate", "pause"):
        monitor.handle_event(name)
    assert seen == [PlaybackState.BUFFERING, PlaybackState.PLAYING, PlaybackState.PAUSED]


def test_update_from_browser_replays_events_once():
    monitor = PlaybackMonitor()
    payload = {
        "events": [
            {"name": "play", "time": 100.0},
            {"name": "playing", "time": 100.5, "position": 1.0, "duration": 180.0},
            {"name": "encrypted", "time": 101.0},
        ]
    }
    monitor.update_from_browser(payload)
    assert monitor.state == PlaybackState.PLAYING
    assert monitor.duration == pytest.approx(180.0)
    assert [e.name for e in monitor.events] == ["play", "playing", "encrypted"]

    # the same payload replays nothing: the cursor dedupes
    monitor.update_from_browser(payload)
    assert len(monitor.events) == 3


def test_update_from_browser_ignores_browser_state_field():
    # Python owns the normalized state machine; the browser instrumentation
    # does not compute one, so its 'state' field is never adopted.
    monitor = PlaybackMonitor()
    monitor.handle_event("playing")
    monitor.update_from_browser({"state": "PAUSED", "position": 3.0, "duration": 9.0})
    assert monitor.state == PlaybackState.PLAYING
    assert monitor.position == pytest.approx(3.0)


def test_update_from_browser_captures_media_session_and_error():
    monitor = PlaybackMonitor()
    monitor.update_from_browser(
        {
            "mediaSession": {"title": "Song", "artist": "Artist", "album": "Album"},
            "error": "EME: license rejected",
        }
    )
    assert monitor.media_session["title"] == "Song"
    assert monitor.last_error == "EME: license rejected"


def test_update_from_browser_rejects_non_dict():
    monitor = PlaybackMonitor()
    monitor.handle_event("playing")
    monitor.update_from_browser(None)
    monitor.update_from_browser("not-json")
    assert monitor.state == PlaybackState.PLAYING


def test_publish_state_payload_shape():
    monitor = PlaybackMonitor()
    monitor.handle_event("playing", position=4.0, duration=200.0)
    payload = monitor.publish_state()
    assert payload["state"] == "PLAYING"
    assert payload["position"] == pytest.approx(4.0)
    assert payload["duration"] == pytest.approx(200.0)
    assert payload["last_event"] == "playing"
    assert payload["last_error"] is None
    assert payload["media_session"] == {}


def test_instrumentation_js_is_read_only():
    # spec 3.1: browser-side instrumentation with an isolated, read-only
    # interface: it stores state on a dedicated marker and returns a string.
    assert "window.__amdPlaybackMonitor" in PLAYBACK_MONITOR_JS
    assert PLAYBACK_MONITOR_JS.startswith("(function(){")
    assert PLAYBACK_MONITOR_JS.rstrip().endswith("return JSON.stringify(m);})()")
    assert "runJavaScript" not in PLAYBACK_MONITOR_JS
    for forbidden in ("qt.webChannelTransport", "python", "PySide"):
        assert forbidden not in PLAYBACK_MONITOR_JS


def test_instrumentation_scans_same_origin_iframes_safely():
    # Amazon may host media inside iframes; cross-origin access must never
    # throw (guarded), and no privileged bridge may appear.
    assert "contentDocument" in PLAYBACK_MONITOR_JS
    assert "iframe" in PLAYBACK_MONITOR_JS
    assert PLAYBACK_MONITOR_JS.count("try{") >= 2 or PLAYBACK_MONITOR_JS.count("try {") >= 2


def test_buffering_promotes_on_advancing_timeupdate():
    # Actual playback progression: a 'play' request alone stays BUFFERING
    # until position evidence (timeupdate) confirms output.
    monitor = PlaybackMonitor()
    monitor.handle_event("play", timestamp=100.0)
    assert monitor.state == PlaybackState.BUFFERING
    monitor.handle_event("timeupdate", timestamp=101.0, position=1.5, duration=200.0)
    assert monitor.state == PlaybackState.PLAYING
    assert monitor.position == pytest.approx(1.5)


def test_playing_without_progression_stalls():
    monitor = PlaybackMonitor(stall_timeout=5.0)
    monitor.handle_event("playing", timestamp=100.0, position=5.0, duration=200.0)
    assert monitor.state == PlaybackState.PLAYING
    # no further position evidence: the monitor must report STALLED, not PLAYING
    assert monitor.detect_stalled(now=106.5) is True
    assert monitor.state == PlaybackState.STALLED


def test_playing_with_advancing_position_does_not_stall():
    monitor = PlaybackMonitor(stall_timeout=5.0)
    monitor.handle_event("playing", timestamp=100.0, position=5.0, duration=200.0)
    monitor.handle_event("timeupdate", timestamp=103.0, position=8.0, duration=200.0)
    assert monitor.detect_stalled(now=106.0) is False
    assert monitor.state == PlaybackState.PLAYING
