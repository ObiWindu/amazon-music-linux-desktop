"""Unit tests for the playlist bridge (browser/playlist_bridge.py)."""

import json

from amazon_music_desktop.browser.playlist_bridge import (
    PLAYLIST_SONGS_PROBE_JS,
    PLAYLISTS_PROBE_JS,
    parse_playlist_songs_result,
    parse_playlists_result,
    play_first_song_js,
)


def test_parse_playlists_result_from_json_string():
    payload = json.dumps(
        {"items": [{"name": "Mix", "href": "https://music.amazon.fr/my/playlists/ABC"}]}
    )
    assert parse_playlists_result(payload) == [
        {"name": "Mix", "href": "https://music.amazon.fr/my/playlists/ABC"}
    ]


def test_parse_playlists_result_from_dict():
    assert parse_playlists_result({"items": [{"name": "A", "href": "h"}]}) == [
        {"name": "A", "href": "h"}
    ]


def test_parse_playlists_result_rejects_garbage():
    assert parse_playlists_result("not json") is None
    assert parse_playlists_result("") is None
    assert parse_playlists_result(42) is None
    assert parse_playlists_result({"items": "nope"}) is None
    assert parse_playlists_result(None) is None


def test_parse_playlists_result_skips_bad_entries():
    payload = {"items": [
        {"name": "", "href": "h"},
        {"name": "  ", "href": "h"},
        {"name": "No href"},
        {"href": "h"},
        "junk",
        {"name": "Ok", "href": "  https://x/y  "},
    ]}
    assert parse_playlists_result(payload) == [{"name": "Ok", "href": "https://x/y"}]


def test_parse_playlist_songs_result_from_json_string():
    payload = json.dumps({"items": [{"title": "Song", "artist": "Artist"}]})
    assert parse_playlist_songs_result(payload) == [{"title": "Song", "artist": "Artist"}]


def test_parse_playlist_songs_result_defaults_artist():
    payload = {"items": [{"title": "Song"}, {"title": "T", "artist": None}, {"artist": "x"}]}
    assert parse_playlist_songs_result(payload) == [
        {"title": "Song", "artist": ""},
        {"title": "T", "artist": ""},
    ]


def test_parse_playlist_songs_result_rejects_garbage():
    assert parse_playlist_songs_result("nope") is None
    assert parse_playlist_songs_result({"items": {"a": 1}}) is None
    assert parse_playlist_songs_result(["not", "a", "dict"]) is None


def test_playlists_probe_selectors_and_shape():
    assert 'a[href*="/playlists/"]' in PLAYLISTS_PROBE_JS
    # the bare index link must be excluded so only real playlists are listed
    assert "/\\/playlists\\/.+/" in PLAYLISTS_PROBE_JS
    assert "JSON.stringify({items:items})" in PLAYLISTS_PROBE_JS


def test_songs_probe_selectors_and_shape():
    assert "track" in PLAYLIST_SONGS_PROBE_JS
    assert "artist" in PLAYLIST_SONGS_PROBE_JS
    assert "JSON.stringify({items:items})" in PLAYLIST_SONGS_PROBE_JS


def test_play_first_song_js_substitutes_dock():
    js = play_first_song_js(110)
    assert "__DOCK__" not in js
    assert "var dock=110;" in js
    assert "var dock=0;" in play_first_song_js(-3)
    # must click a row, and never a control inside the docked player strip
    assert "window.innerHeight-dock" in js
    assert "__CLICK__" not in js
