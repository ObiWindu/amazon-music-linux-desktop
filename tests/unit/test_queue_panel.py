import pytest

from amazon_music_desktop.ui.queue_panel import QueuePanel, track_label


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def test_track_label_formatting():
    assert track_label("Song", "Artist") == "Song — Artist"
    assert track_label("Song") == "Song"
    assert track_label("", "Artist") == ""
    assert track_label("   ") == ""


def test_queue_panel_adds_song(qapp):
    panel = QueuePanel()
    panel.on_track("Never Gonna Give You Up")
    assert panel.songs() == ["Never Gonna Give You Up"]


def test_queue_panel_ignores_blank(qapp):
    panel = QueuePanel()
    panel.on_track("")
    panel.on_track("   ")
    assert panel.songs() == []


def test_queue_panel_dedupes_repeated_title(qapp):
    panel = QueuePanel()
    panel.on_track("Song A")
    panel.on_track("Song A")  # same poll tick
    panel.on_track("Song B")
    panel.on_track("Song A")  # encore later is a distinct row
    assert panel.songs() == ["Song A", "Song B", "Song A"]


def test_queue_panel_labels_artist(qapp):
    panel = QueuePanel()
    panel.on_track("Song", "Performer")
    panel.on_track("Song")  # same title without artist dedupes to last row
    assert panel.songs() == ["Song — Performer"]


def test_queue_panel_upcoming_scrape_wins(qapp):
    panel = QueuePanel()
    panel.on_track("Played Song")
    panel.set_upcoming(["Next 1", "next 2  "])
    assert panel.songs() == ["Next 1", "next 2"]


def test_queue_panel_shows_note_when_empty(qapp):
    panel = QueuePanel()
    assert panel.has_songs() is False
    assert panel.note.text() == "No songs yet — press play"
    panel.on_track("Song A")
    assert panel.has_songs() is True
    assert panel.note.text() == ""


def test_queue_panel_empty_scrape_keeps_history(qapp):
    panel = QueuePanel()
    panel.on_track("Played Song")
    panel.set_upcoming([])
    panel.set_upcoming(["", "   "])
    assert panel.songs() == ["Played Song"]
