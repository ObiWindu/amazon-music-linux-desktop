import time

import pytest

from amazon_music_desktop.ui.player_bar import (
    PlayerBar,
    TransportButton,
    clamp01,
    format_time,
)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def test_format_time():
    assert format_time(0) == "0:00"
    assert format_time(95) == "1:35"
    assert format_time(600) == "10:00"


def test_clamp01():
    assert clamp01(-1) == 0.0
    assert clamp01(0.5) == 0.5
    assert clamp01(4) == 1.0


def test_transport_button_glyph_and_playing(qapp):
    btn = TransportButton("▶", "tooltip")
    assert btn.glyph == "▶"
    btn.glyph = "⏸"
    assert btn.glyph == "⏸"
    assert btn.playing is False
    btn.set_playing(True)
    assert btn.playing is True
    btn.set_playing(False)
    assert btn.playing is False


def test_transport_button_pop_is_bounded(qapp):
    btn = TransportButton("⏮", "tooltip")
    btn.scale = 0.86
    btn.paintEvent(None)
    btn.scale = 1.0
    assert btn.scale == 1.0


def test_transport_button_paint_does_not_crash(qapp):
    btn = TransportButton("▶", "tooltip")
    btn.show()
    btn.set_playing(True)
    assert btn.grab().size().width() >= 1
    btn.set_playing(False)
    assert btn.grab().size().width() >= 1


def test_player_bar_paint_does_not_crash(qapp):
    bar = PlayerBar()
    bar.show()
    bar.set_state({"title": "x", "cur": 12.0, "dur": 180.0, "paused": False, "volume": 0.8, "muted": False})
    bar.shuffle_btn.setChecked(True)
    bar.next_btn.pop()
    assert bar.grab().size().width() >= 1


def test_player_bar_mirrors_state(qapp):
    bar = PlayerBar()
    bar.set_state(
        {
            "title": "Never Gonna Give You Up - Amazon Music",
            "cur": 60.0,
            "dur": 300.0,
            "paused": False,
            "volume": 0.5,
            "muted": False,
        }
    )
    assert bar.track_label.text().startswith("Never Gonna Give You Up")
    assert bar.play_btn.glyph == "⏸"
    assert bar.play_btn.playing is True
    assert bar.time_cur.text() == "1:00"
    assert bar.time_total.text() == "5:00"
    assert bar.seek.isEnabled() is True
    assert bar.seek.value() == 200  # 60/300 of 1000
    assert bar.vol_slider.value() == 50
    assert bar.volume_btn.glyph == "🔊"

    bar.set_state(
        {
            "title": "Never Gonna Give You Up - Amazon Music",
            "cur": 0.0,
            "dur": 0.0,
            "paused": True,
        }
    )
    assert bar.play_btn.glyph == "▶"
    assert bar.seek.isEnabled() is False
    assert bar.time_total.text() == "0:00"


def test_player_bar_keeps_volume_while_dragging(qapp):
    bar = PlayerBar()
    bar._start_vol_drag()
    bar.set_state(
        {
            "title": "x",
            "cur": 0.0,
            "dur": 0.0,
            "paused": True,
            "volume": 0.2,
            "muted": False,
        }
    )
    assert bar.vol_slider.value() == 100  # drag wins over poll
    bar._end_vol_drag()
    assert bar.vol_slider.value() == 100


def test_player_bar_forward_seek_signal(qapp):
    bar = PlayerBar()
    seen: list[float] = []
    bar.seek_requested.connect(seen.append)
    bar.seek.setEnabled(True)
    bar.seek.seek_requested.emit(0.42)
    assert seen == [pytest.approx(0.42)]


def test_seek_click_maps_through_groove_geometry(qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    bar = PlayerBar()
    bar.seek.setEnabled(True)
    bar.resize(800, bar.height())
    bar.show()
    mid = bar.seek.width() // 2
    QTest.mouseClick(bar.seek, Qt.MouseButton.LeftButton, pos=QPoint(mid, 11))
    # middle of the groove lands near the middle of the range even with
    # style handle insets (a raw width mapping would drift at the edges)
    assert 450 <= bar.seek.value() <= 550
    QTest.mouseClick(bar.seek, Qt.MouseButton.LeftButton, pos=QPoint(3, 11))
    assert bar.seek.value() < 80
    QTest.mouseClick(bar.seek, Qt.MouseButton.LeftButton, pos=QPoint(bar.seek.width() - 3, 11))
    assert bar.seek.value() > 920


def test_scrub_preview_and_release_flow(qapp):
    bar = PlayerBar()
    bar.set_state({"title": "x", "cur": 10.0, "dur": 200.0, "paused": False})
    assert bar.time_cur.text() == "0:10"
    bar.seek.setSliderDown(True)
    bar._preview_scrub(500)  # drag to 50%: readout previews immediately
    assert bar.time_cur.text() == "1:40"
    bar.set_state({"title": "x", "cur": 12.0, "dur": 200.0, "paused": False})
    assert bar.time_cur.text() == "1:40"  # poll does not fight the scrub
    assert bar.time_total.text() == "3:20"
    seen: list[float] = []
    bar.seek_requested.connect(seen.append)
    bar.seek.setValue(1000)
    bar.seek.setSliderDown(False)
    bar.set_state({"title": "x", "cur": 200.0, "dur": 200.0, "paused": False})
    assert bar.time_cur.text() == "3:20"


def test_track_label_includes_artist(qapp):
    bar = PlayerBar()
    bar.set_state({"title": "Song", "artist": "Performer", "cur": 0.0, "dur": 0.0, "paused": True})
    assert bar.track_label.text() == "Song — Performer"
    bar.set_state({"title": "Song", "cur": 0.0, "dur": 0.0, "paused": True})
    assert bar.track_label.text() == "Song"


def test_shuffle_repeat_sync_tristate(qapp):
    bar = PlayerBar()
    bar.set_state({"title": "x", "cur": 0.0, "dur": 0.0, "paused": True, "shuffle": True, "repeat": False})
    assert bar.shuffle_btn.isChecked() is True
    assert bar.repeat_btn.isChecked() is False
    # unknown page state leaves local controls untouched
    bar.set_state({"title": "x", "cur": 0.0, "dur": 0.0, "paused": True})
    assert bar.shuffle_btn.isChecked() is True
    assert bar.repeat_btn.isChecked() is False


def test_seek_slider_disables_without_track(qapp):
    bar = PlayerBar()
    assert bar.seek.isEnabled() is False
    bar.set_state({"title": "x", "cur": 10.0, "dur": 200.0, "paused": False})
    assert bar.seek.isEnabled() is True
    bar.set_state({"title": "x", "cur": 0.0, "dur": 0.0, "paused": True})
    assert bar.seek.isEnabled() is False


def test_time_bar_follows_playback_between_polls(qapp):
    bar = PlayerBar()
    bar.set_state({"title": "x", "cur": 10.0, "dur": 200.0, "paused": False})
    assert bar.time_cur.text() == "0:10"
    # five seconds elapse since the last poll: the bar keeps moving
    bar._anchor_at = time.monotonic() - 5.0
    bar._tick_position()
    assert bar.time_cur.text() == "0:15"
    assert bar.seek.value() == 75  # 15/200 of the 1000-step range


def test_time_bar_never_animates_a_frozen_position(qapp):
    # the 0:00 failure: page claims playing but the position never moves
    bar = PlayerBar()
    bar.set_state({"title": "x", "cur": 0.0, "dur": 200.0, "paused": False})
    bar._anchor_at = time.monotonic() - 30.0
    bar._tick_position()
    assert bar.time_cur.text() == "0:00"
    # a stalled position mid-track freezes the bar too
    bar.set_state({"title": "x", "cur": 42.0, "dur": 200.0, "paused": False})
    bar.set_state({"title": "x", "cur": 42.0, "dur": 200.0, "paused": False})
    bar._anchor_at = time.monotonic() - 30.0
    bar._tick_position()
    assert bar.time_cur.text() == "0:42"


def test_time_bar_stops_at_track_end(qapp):
    bar = PlayerBar()
    bar.set_state({"title": "x", "cur": 198.0, "dur": 200.0, "paused": False})
    bar._anchor_at = time.monotonic() - 30.0
    bar._tick_position()
    assert bar.time_cur.text() == "3:20"
    assert bar.seek.value() == 1000


def test_time_bar_frozen_while_paused(qapp):
    bar = PlayerBar()
    bar.set_state({"title": "x", "cur": 30.0, "dur": 200.0, "paused": True})
    bar._anchor_at = time.monotonic() - 30.0
    bar._tick_position()
    assert bar.time_cur.text() == "0:30"


def test_seek_anchors_the_time_bar_immediately(qapp):
    bar = PlayerBar()
    bar.set_state({"title": "x", "cur": 10.0, "dur": 200.0, "paused": False})
    seen: list[float] = []
    bar.seek_requested.connect(seen.append)
    bar.seek.setEnabled(True)
    bar._on_seek_requested(0.5)
    assert seen == [pytest.approx(0.5)]
    assert bar.time_cur.text() == "1:40"
    # the clock continues from the seek target, not the old position
    bar._anchor_at = time.monotonic() - 2.0
    bar._tick_position()
    assert bar.time_cur.text() == "1:42"


def test_volume_and_mute_persist_without_loaded_track(qapp):
    bar = PlayerBar()
    bar.set_state(
        {"title": "x", "cur": 10.0, "dur": 200.0, "paused": False, "volume": 0.3, "muted": True}
    )
    assert bar.vol_slider.value() == 30
    assert bar.volume_btn.isChecked() is True
    # track gone: the page probe falls back to its defaults (full volume,
    # not muted) — the user's settings must survive
    bar.set_state({"title": "x", "cur": 0.0, "dur": 0.0, "paused": True})
    assert bar.vol_slider.value() == 30
    assert bar.volume_btn.isChecked() is True
    assert bar.volume_btn.glyph == "🔇"


def test_volume_syncs_while_track_loaded(qapp):
    bar = PlayerBar()
    bar.set_state({"title": "x", "cur": 10.0, "dur": 200.0, "paused": False, "volume": 0.4})
    assert bar.vol_slider.value() == 40
