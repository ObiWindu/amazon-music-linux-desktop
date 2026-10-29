import amazon_music_desktop.browser.player_bridge as bridge
from amazon_music_desktop.browser.player_bridge import (
    NOW_PLAYING_PROBE_JS,
    parse_probe_result,
    player_action_js,
    track_progress_percent,
)


def test_bridge_does_not_mutate_page_player_dom():
    # Regression guard: player-bar suppression must stay at the widget level
    # (main_window._BrowserHost docks it out of view). CSS/JS that touches the
    # page player broke Amazon's PlaybackAdapter and coincided with ~1s
    # playback teardowns.
    for attr in ("PLAYER_BAR_STYLE", "MINIMIZE_BAR_JS", "MINIMIZED_BAR_CLASS"):
        assert not hasattr(bridge, attr)


def test_player_action_known():
    js = player_action_js("play")
    assert "click()" in js
    assert "return true" in js
    assert "return false" in js


def test_player_action_unknown():
    assert player_action_js("dance") == ""


def test_player_actions_all_covered():
    for action in ("previous", "play", "next", "shuffle", "repeat"):
        assert player_action_js(action) != ""


def test_probe_js_reads_audio_element():
    assert "querySelector('audio')" in NOW_PLAYING_PROBE_JS
    assert "currentTime" in NOW_PLAYING_PROBE_JS
    assert "paused" in NOW_PLAYING_PROBE_JS


def test_parse_probe_result_valid():
    state = parse_probe_result({"title": "Song", "cur": 30, "dur": 120, "paused": False})
    assert state == {"title": "Song", "cur": 30.0, "dur": 120.0, "paused": False}


def test_parse_probe_result_invalid():
    assert parse_probe_result(None) is None
    assert parse_probe_result("Song") is None
    assert parse_probe_result({"title": "", "cur": "x", "dur": None, "paused": 0}) == {
        "title": "",
        "cur": 0.0,
        "dur": 0.0,
        "paused": False,
    }


def test_track_progress_percent():
    assert track_progress_percent(30, 120) == 25
    assert track_progress_percent(0, 0) is None
    assert track_progress_percent(200, 100) == 100
