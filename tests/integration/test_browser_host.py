import pytest
from PySide6.QtWidgets import QWidget

from amazon_music_desktop.main_window import _BrowserHost


@pytest.fixture
def host(qtbot):
    view = QWidget()
    h = _BrowserHost(view)
    qtbot.addWidget(h)
    return h


def test_dock_hides_a_full_width_bottom_bar():
    # A bottom-docked bar up to 110px tall at the page viewport bottom is
    # fully inside the docked (clipped) strip.
    assert _BrowserHost.DOCK_PX >= 110


def test_view_extends_below_host(host, qtbot):
    host.show()
    host.resize(800, 600)
    expected = 600 + _BrowserHost.DOCK_PX
    qtbot.waitUntil(lambda: host._view.height() == expected)
    assert host._view.width() == 800
    assert host._view.y() == 0
    # The extra strip lies below the host rect, i.e. outside the visible area.
    assert host._view.height() > host.height()


def test_view_tracks_host_resizes(host, qtbot):
    host.show()
    host.resize(1024, 768)
    qtbot.waitUntil(lambda: host._view.height() == 768 + _BrowserHost.DOCK_PX)
    host.resize(1280, 720)
    qtbot.waitUntil(lambda: host._view.height() == 720 + _BrowserHost.DOCK_PX)
    assert host._view.width() == 1280
