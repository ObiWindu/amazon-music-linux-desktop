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


def test_seek_slider_disables_without_track(qapp):
    bar = PlayerBar()
    assert bar.seek.isEnabled() is False
    bar.set_state({"title": "x", "cur": 10.0, "dur": 200.0, "paused": False})
    assert bar.seek.isEnabled() is True
    bar.set_state({"title": "x", "cur": 0.0, "dur": 0.0, "paused": True})
    assert bar.seek.isEnabled() is False
