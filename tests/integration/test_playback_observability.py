"""Integration tests: playback observability wiring in the real window.

Runs offscreen; no Amazon account, no DRM playback, no live session bus.
"""

import json

import pytest
from PySide6.QtWebEngineCore import QWebEnginePage

from amazon_music_desktop.browser.playback_monitor import PlaybackState
from amazon_music_desktop.browser.profile import ProfileManager
from amazon_music_desktop.main_window import MainWindow
from amazon_music_desktop.services.configuration import ConfigService


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from amazon_music_desktop import main_window as mw
    from amazon_music_desktop.integrations.mpris import MprisService

    # keep tests off the developer's real session bus
    monkeypatch.setattr(MprisService, "register", lambda self: False)
    # renderer-termination handling must not block on a modal dialog
    monkeypatch.setattr(mw.QMessageBox, "warning", lambda *a, **k: None)

    svc = ConfigService(config_file=tmp_path / "cfg.json")
    svc.load()
    pm = ProfileManager(profile_dir=tmp_path / "profile_root")
    profile = pm.create_profile()
    w = MainWindow(svc, pm, profile)
    qtbot.addWidget(w)
    return w


def test_persistent_profile_points_into_managed_dir(window, tmp_path):
    pm = window.profile_manager
    assert pm.profile_path == tmp_path / "profile_root" / "profile"
    assert window.profile.persistentStoragePath() == str(pm.profile_path)
    assert pm.profile_permissions_ok()


def test_vmp_console_error_marks_license_stage_failed(window):
    diagnostics = window.playback_diagnostics
    window.page.javaScriptConsoleMessage(
        QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel,
        "denialReason: VMP_VALIDATION_FAILED"
        " (UNVERIFIED request not eligible for LD content)",
        1,
        "https://music.amazon.fr/",
    )
    assert diagnostics.pipeline.summary()["license_acquisition_attempted"] == "FAILED"
    assert diagnostics.failure_code.value == "LICENSE_FAILED"


def test_plain_console_error_recorded_without_license_stage(window):
    diagnostics = window.playback_diagnostics
    window.page.javaScriptConsoleMessage(
        QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel,
        "uncaught TypeError: x is undefined",
        3,
        "https://music.amazon.fr/app.js",
    )
    assert [e.kind for e in diagnostics.events] == ["console_error"]
    assert diagnostics.pipeline.summary()["license_acquisition_attempted"] == "UNKNOWN"


def test_renderer_termination_is_reported(window):
    diagnostics = window.playback_diagnostics
    window._on_render_terminated("Crashed", 11)
    assert diagnostics.events[0].kind == "renderer_terminated"
    assert diagnostics.events[0].details == {"status": "Crashed", "code": 11}


def test_monitor_payload_propagates_to_state_and_pipeline(window):
    payload = json.dumps(
        {
            "events": [
                {"name": "play", "time": 10.0},
                {"name": "playing", "time": 10.4, "position": 0.5, "duration": 212.0},
            ],
            "mediaSession": {"title": "Song", "artist": "Artist"},
        }
    )
    window._on_monitor_state(payload)
    assert window.monitor.state is PlaybackState.PLAYING
    assert window.monitor.media_session["title"] == "Song"

    encrypted = json.dumps({"events": [{"name": "encrypted", "time": 11.0}]})
    window._on_monitor_state(encrypted)
    assert (
        window.playback_diagnostics.pipeline.summary()["encrypted_media_detected"]
        == "VERIFIED"
    )


def test_invalid_monitor_payload_is_ignored(window):
    window.monitor.handle_event("play")
    window._on_monitor_state("")
    window._on_monitor_state("not-json{")
    window._on_monitor_state(None)
    assert window.monitor.state is PlaybackState.PLAYING


def test_player_action_miss_is_observable_without_false_success(window):
    window._on_action_result("next", "")
    assert any(
        e.kind == "player_action_missed" for e in window.playback_diagnostics.events
    )
    # a missed action never claims playback state
    assert window.monitor.state is PlaybackState.IDLE
