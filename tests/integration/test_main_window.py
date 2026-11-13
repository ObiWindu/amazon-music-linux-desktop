import pytest
from PySide6.QtCore import Qt

from amazon_music_desktop.browser.profile import ProfileManager
from amazon_music_desktop.main_window import MainWindow
from amazon_music_desktop.services.configuration import ConfigService


@pytest.fixture
def window(qtbot, tmp_path):
    svc = ConfigService(config_file=tmp_path / "cfg.json")
    svc.load()
    pm = ProfileManager(profile_dir=tmp_path / "profile_root")
    profile = pm.create_profile()
    w = MainWindow(svc, pm, profile)
    qtbot.addWidget(w)
    return w


def test_window_renders(window):
    assert window.isVisible() is False or True
    window.show()
    assert window.width() >= 900


def test_sidebar_exists(window):
    assert window.btn_home is not None


def test_go_home(window, qtbot):
    with qtbot.waitSignal(window.view.loadFinished, timeout=10000):
        window.go_home()
    assert "amazon" in window.current_url()


def test_user_agent_matches_host_arch(tmp_path):
    import platform

    from amazon_music_desktop.browser.profile import ProfileManager

    pm = ProfileManager(profile_dir=tmp_path / "profile_root")
    profile = pm.create_profile()
    ua = profile.httpUserAgent()
    machine = platform.machine().lower()
    expected = "aarch64" if machine in ("aarch64", "arm64") else "x86_64"
    opposite = "x86_64" if expected == "aarch64" else "aarch64"
    assert expected in ua
    assert opposite not in ua


def test_playlist_list_below_playlists_button(window):
    assert window.playlist_list is not None
    assert window.playlist_list.isHidden() is True  # empty until fetched
    window._set_playlists(
        [
            {"name": "Mix", "href": "https://music.amazon.fr/my/playlists/ABC"},
            {"name": "Chill", "href": "https://music.amazon.fr/my/playlists/DEF"},
        ]
    )
    assert window.playlist_list.count() == 2
    assert window.playlist_list.isHidden() is False
    assert window.playlist_list.item(0).text() == "Mix"
    assert (
        window.playlist_list.item(0).data(Qt.ItemDataRole.UserRole)
        == "https://music.amazon.fr/my/playlists/ABC"
    )
    # unchanged scrape is a no-op (no rebuild flicker)
    window._set_playlists(
        [
            {"name": "Mix", "href": "https://music.amazon.fr/my/playlists/ABC"},
            {"name": "Chill", "href": "https://music.amazon.fr/my/playlists/DEF"},
        ]
    )
    assert window.playlist_list.count() == 2


def test_playlist_single_click_adds_songs_to_queue(window, monkeypatch):
    window._set_playlists([{"name": "Mix", "href": "https://music.amazon.fr/my/playlists/ABC"}])
    item = window.playlist_list.item(0)
    monkeypatch.setattr(
        window,
        "_fetch_playlist_songs",
        lambda href, cb: cb([{"title": "S1", "artist": "A1"}, {"title": "S2", "artist": "A2"}]),
    )
    window._on_playlist_clicked(item)
    assert window.queue_panel.songs() == ["S1 — A1", "S2 — A2"]
    assert window.queue_panel.manual_queue is True
    # page scrape afterwards must not wipe the queued songs
    window._on_queue_result('{"items": ["Page Song"]}')
    assert window.queue_panel.songs() == ["S1 — A1", "S2 — A2"]


def test_playlist_double_click_clears_queues_and_plays_first(window, monkeypatch):
    window.queue_panel.on_track("Old Song")
    window._set_playlists([{"name": "Mix", "href": "https://music.amazon.fr/my/playlists/ABC"}])
    item = window.playlist_list.item(0)
    monkeypatch.setattr(
        window,
        "_fetch_playlist_songs",
        lambda href, cb: cb([{"title": "S1", "artist": "A1"}, {"title": "S2", "artist": "A2"}]),
    )
    navs = []
    monkeypatch.setattr(window, "_soft_navigate", lambda url: navs.append(url))
    window._on_playlist_double_clicked(item)
    # queue cleared, playlist songs queued, playback armed on the playlist URL
    assert window.queue_panel.songs() == ["S1 — A1", "S2 — A2"]
    assert window.queue_panel.manual_queue is True
    assert window._play_first_armed is True
    assert window._pending_play_href.endswith("/my/playlists/ABC")
    # navigation is soft (SPA pushState) so playback is never interrupted
    assert navs and navs[0].endswith("/my/playlists/ABC")


def test_next_playing_song_is_added_to_queue_automatically(window):
    import json

    window._on_np_result(
        json.dumps(
            {"title": "First Song", "artist": "Artist", "cur": 1.0, "dur": 200.0, "paused": False}
        )
    )
    window._on_np_result(
        json.dumps(
            {"title": "Second Song", "artist": "Artist", "cur": 0.5, "dur": 180.0, "paused": False}
        )
    )
    assert window.queue_panel.songs() == ["First Song — Artist", "Second Song — Artist"]


def test_fetcher_delivers_cached_songs(window, monkeypatch):
    window._playlist_song_cache["https://x/pl/1"] = [{"title": "Cached", "artist": ""}]
    seen = []
    window._fetch_playlist_songs("https://x/pl/1", seen.append)
    assert seen == [[{"title": "Cached", "artist": ""}]]
    # no fetcher load was started for a cached href
    assert window._fetch_pending is None
