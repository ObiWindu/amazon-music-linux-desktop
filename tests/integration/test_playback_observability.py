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
    window.monitor.handle_event("playing")
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


def test_player_action_success_strategy_is_recorded(window):
    window._on_action_result("next", "geom:512:Next")
    matches = [
        e for e in window.playback_diagnostics.events if e.kind == "player_action"
    ]
    assert len(matches) == 1
    assert matches[0].details == {"action": "next", "strategy": "geom:512:Next"}
    # dispatch observability never claims playback state either
    assert window.monitor.state is PlaybackState.IDLE


def test_decoding_verified_only_with_duration_evidence(window):
    window.monitor.handle_event("playing", position=4.0, duration=200.0)
    window._on_playback_state_changed(PlaybackState.PLAYING)
    summary = window.playback_diagnostics.pipeline.summary()
    assert summary["media_decoding_started"] == "VERIFIED"
    assert summary["audio_output_started"] == "VERIFIED"


def test_playing_without_duration_marks_nothing(window):
    window.monitor.handle_event("playing")  # no position/duration evidence
    window._on_playback_state_changed(PlaybackState.PLAYING)
    summary = window.playback_diagnostics.pipeline.summary()
    assert summary["media_decoding_started"] == "UNKNOWN"
    assert summary["audio_output_started"] == "UNKNOWN"


def test_apply_player_seek_runs_page_js_and_emits_seeked():
    from types import SimpleNamespace

    from amazon_music_desktop.main_window import MainWindow

    calls: dict = {}
    page = SimpleNamespace(runJavaScript=lambda js, *a: calls.setdefault("js", js))
    view = SimpleNamespace(page=lambda: page)
    mpris = SimpleNamespace(emit_seeked=lambda seconds: calls.setdefault("seeked", seconds))
    self = SimpleNamespace(_last_dur=200.0, view=view, mpris=mpris)
    MainWindow._apply_player_seek(self, 0.5)
    assert "currentTime" in calls["js"]
    assert calls["seeked"] == pytest.approx(100.0)


def test_apply_player_seek_ignored_without_duration():
    from types import SimpleNamespace

    from amazon_music_desktop.main_window import MainWindow

    calls: dict = {}
    page = SimpleNamespace(runJavaScript=lambda js, *a: calls.setdefault("js", js))
    view = SimpleNamespace(page=lambda: page)
    mpris = SimpleNamespace(emit_seeked=lambda seconds: calls.setdefault("seeked", seconds))
    self = SimpleNamespace(_last_dur=0.0, view=view, mpris=mpris)
    MainWindow._apply_player_seek(self, 0.5)
    assert calls == {}


def test_load_started_resets_stale_page_evidence(window):
    window.monitor.handle_event("playing", position=4.0, duration=200.0)
    window.playback_diagnostics.note_track_selected()
    assert window.monitor.state is PlaybackState.PLAYING
    window._on_load_started()
    assert window.monitor.state is PlaybackState.IDLE
    assert window.monitor.events == []
    summary = window.playback_diagnostics.pipeline.summary()
    assert summary["track_selection_initiated"] == "UNKNOWN"
    assert any(e.kind == "navigation" for e in window.playback_diagnostics.events)


def test_media_session_snapshot_recorded_once_per_change(window):
    payload = (
        '{"events": [], "mediaSession": '
        '{"title": "Song", "artist": "Me", "playbackState": "playing"}}'
    )
    window._on_monitor_state(payload)
    window._on_monitor_state(payload)  # same snapshot: no duplicate event
    snapshots = [
        e for e in window.playback_diagnostics.events if e.kind == "media_session"
    ]
    assert len(snapshots) == 1
    assert snapshots[0].details == {"playback_state": "playing", "has_metadata": True}


def test_instrumentation_runs_in_iframe_context(window, qtbot):
    import json

    from amazon_music_desktop.browser.playback_monitor import PLAYBACK_MONITOR_JS

    html = (
        "<html><body>"
        "<audio id='top' src='song.mp3'></audio>"
        "<iframe srcdoc=\"<audio id='inner' src='ad.mp3'></audio>\"></iframe>"
        "</body></html>"
    )
    window.view.setHtml(html, window.view.url())
    assert window.view.page() is not None
    seen: dict = {}

    def collect(result):
        seen["result"] = result

    window.view.page().runJavaScript(PLAYBACK_MONITOR_JS, collect)
    qtbot.waitUntil(lambda: "result" in seen, timeout=10000)
    payload = json.loads(seen["result"])
    # instrumentation ran without throwing on the framed document
    assert isinstance(payload.get("events"), list)
    assert payload.get("position") == 0


def test_diagnostics_verdict_unknown_without_mapped_cdm(window):
    from amazon_music_desktop.ui.diagnostics_dialog import DiagnosticsDialog

    dialog = DiagnosticsDialog(window, playback_diagnostics=window.playback_diagnostics)
    text = dialog.text.toPlainText()
    # the three values are labeled as what they are — selection is never
    # presented as proof of loading
    assert "CDM selected by Aurora" in text
    assert "Engine default CDM path" in text
    assert "Observed mapped CDM" in text
    assert "Selection vs loaded verdict" in text
    # no CDM is mapped into test processes: verdict must be UNKNOWN, never MATCH
    assert "verdict: UNKNOWN" in text
    assert "verdict: MATCH" not in text
