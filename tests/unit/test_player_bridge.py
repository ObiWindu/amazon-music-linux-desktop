import json

import amazon_music_desktop.browser.player_bridge as bridge
from amazon_music_desktop.browser.player_bridge import (
    NOW_PLAYING_PROBE_JS,
    parse_probe_result,
    player_action_js,
    seek_js,
    track_progress_percent,
    volume_js,
)


def test_bridge_does_not_mutate_page_player_dom():
    # Regression guard: player-bar suppression must stay at the widget level
    # (main_window._BrowserHost docks it out of view). CSS/JS that touches the
    # page player broke Amazon's PlaybackAdapter and coincided with ~1s
    # playback teardowns.
    for attr in ("PLAYER_BAR_STYLE", "MINIMIZE_BAR_JS", "MINIMIZED_BAR_CLASS"):
        assert not hasattr(bridge, attr)


def test_player_action_known():
    js = player_action_js("next")
    assert "click()" in js
    assert "return ''" in js


def test_geometry_fallback_docks_to_strip():
    js = player_action_js("next", dock_px=110)
    assert "var dock=110" in js
    assert "window.innerHeight-dock-8" in js
    assert "window.innerHeight+2" in js


def test_play_drives_media_first():
    js = player_action_js("play")
    assert "querySelectorAll('audio,video')" in js
    assert ".play()" in js
    assert ".pause()" in js


def test_play_fallback_still_mentions_playing_labels():
    js = player_action_js("play")
    assert "Écouter" in js
    assert "Pause" in js


def test_controls_match_french_labels():
    assert "Précédent" in player_action_js("previous")
    assert "Suivant" in player_action_js("next")
    assert "aléatoire" in player_action_js("shuffle")
    assert "Répéter" in player_action_js("repeat")


def test_controls_exclude_carousel_pagers():
    # "Voir l'élément suivant/précédent dans ..." pages a shelf, not a track;
    # "*_PreviousPageButton"/"*_NextPageButton" are carousel controls.
    for action in ("previous", "next"):
        js = player_action_js(action)
        assert "voir l'" in js
        assert "pagebutton" in js


def test_click_dispatch_fires_pointer_events():
    # React-style handlers listen for pointer events; a bare .click() is
    # often ignored. Every strategy must pass through the shared click body.
    for action in ("previous", "play", "next", "shuffle", "repeat"):
        js = player_action_js(action)
        assert "PointerEvent('pointerdown'" in js
        assert "MouseEvent('mouseup'" in js


def test_player_action_unknown():
    assert player_action_js("dance") == ""


def test_player_actions_all_covered():
    for action in ("previous", "play", "next", "shuffle", "repeat"):
        assert player_action_js(action) != ""


def test_offset_map_addresses_transport_cluster():
    js = player_action_js("next")
    assert '"next": 1' in js or '"next":1' in js
    assert '"previous": -1' in js or '"previous":-1' in js


def test_probe_js_reads_audio_element_with_volume():
    assert "querySelector('audio')" in NOW_PLAYING_PROBE_JS
    assert "currentTime" in NOW_PLAYING_PROBE_JS
    assert "paused" in NOW_PLAYING_PROBE_JS
    assert "vol:a?a.volume:1" in NOW_PLAYING_PROBE_JS
    assert "muted:a?a.muted:false" in NOW_PLAYING_PROBE_JS
    # Real track identity comes from mediaSession when available; the page
    # keeps the *playlist* name in document.title while browsing.
    assert "mediaSession" in NOW_PLAYING_PROBE_JS
    assert "md.title" in NOW_PLAYING_PROBE_JS
    assert "md.artist" in NOW_PLAYING_PROBE_JS
    assert "document.title" in NOW_PLAYING_PROBE_JS
    # QtWebEngine 6.11 delivers object results as ''; probes must stringify.
    assert "JSON.stringify" in NOW_PLAYING_PROBE_JS


def test_parse_probe_result_accepts_json_string():
    state = parse_probe_result(
        json.dumps(
            {
                "title": "Song",
                "artist": "Performer",
                "cur": 30,
                "dur": 120,
                "paused": False,
                "vol": 0.7,
                "muted": True,
            }
        )
    )
    assert state["title"] == "Song"
    assert state["artist"] == "Performer"
    assert state["cur"] == 30.0
    assert state["dur"] == 120.0
    assert state["paused"] is False
    assert state["volume"] == 0.7
    assert state["muted"] is True
    assert parse_probe_result("not json") is None
    assert parse_probe_result("") is None


def test_parse_probe_result_valid():
    state = parse_probe_result({"title": "Song", "cur": 30, "dur": 120, "paused": False})
    assert state == {
        "title": "Song",
        "artist": "",
        "cur": 30.0,
        "dur": 120.0,
        "paused": False,
        "volume": 1.0,
        "muted": False,
    }


def test_parse_probe_result_clamps_volume():
    state = parse_probe_result({"title": "", "cur": "x", "dur": None, "paused": 0, "vol": 4.2, "muted": 1, "artist": 3})
    assert state["volume"] == 1.0
    assert state["muted"] is True
    assert state["artist"] == ""
    assert state["cur"] == 0.0
    assert state["dur"] == 0.0


def test_parse_probe_result_invalid():
    assert parse_probe_result(None) is None
    assert parse_probe_result("Song") is None


def test_track_progress_percent():
    assert track_progress_percent(30, 120) == 25
    assert track_progress_percent(0, 0) is None
    assert track_progress_percent(200, 100) == 100


def test_seek_js_clamps():
    js = seek_js(999999.0)
    assert "Math.max(0,Math.min(a.duration,999999.0))" in js
    assert "Math.max(0,Math.min(a.duration,0.0))" in seek_js(-3.0)
    assert "duration<=0" in seek_js(5)


def test_volume_js_sets_both():
    js = volume_js(0.5, True)
    assert "a.volume=0.5" in js
    assert "a.muted=true" in js
    assert volume_js(None, None) == ""
    assert "a.muted=false" in volume_js(None, False)


def test_queue_probe_targets_queue_rows():
    from amazon_music_desktop.browser.player_bridge import QUEUE_PROBE_JS

    assert 'data-testid*="queueItem"' in QUEUE_PROBE_JS
    assert "up-next" in QUEUE_PROBE_JS
    assert "JSON.stringify" in QUEUE_PROBE_JS


def test_parse_queue_result_valid_and_invalid():
    from amazon_music_desktop.browser.player_bridge import QUEUE_PROBE_JS, parse_queue_result

    songs = parse_queue_result(json.dumps({"items": ["1. Track A", "2. Track B"]}))
    assert songs == ["1. Track A", "2. Track B"]
    assert parse_queue_result(json.dumps({"items": []})) == []
    assert parse_queue_result(json.dumps({"items": [3, "x", None]})) == ["x"]
    assert parse_queue_result(None) is None
    assert parse_queue_result("not json") is None
    assert parse_queue_result({"no": "items"}) is None
    # The JS must return a JSON *string* (QtWebEngine drops objects).
    assert QUEUE_PROBE_JS.endswith("})()")
