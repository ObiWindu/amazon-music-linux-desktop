from amazon_music_desktop.browser.player_bridge import (
    MINIMIZE_BAR_JS,
    NOW_PLAYING_PROBE_JS,
    PLAYER_BAR_STYLE,
    parse_probe_result,
    player_action_js,
    track_progress_percent,
)


def test_style_has_no_display_none():
    assert "display" not in PLAYER_BAR_STYLE
    assert "visibility" not in PLAYER_BAR_STYLE


def test_style_preserves_layout():
    assert "max-height" in PLAYER_BAR_STYLE
    assert "pointer-events" in PLAYER_BAR_STYLE


def test_minimize_js_skips_media_containers():
    assert "audio,video" in MINIMIZE_BAR_JS


def test_minimize_js_is_idempotent():
    assert "classList.contains" in MINIMIZE_BAR_JS


def test_minimize_js_never_removes_nodes():
    assert "remove()" not in MINIMIZE_BAR_JS
    assert "display" not in MINIMIZE_BAR_JS


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
