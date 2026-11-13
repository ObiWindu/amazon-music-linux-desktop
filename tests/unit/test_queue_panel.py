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


def test_scrape_then_same_song_does_not_duplicate(qapp):
    panel = QueuePanel()
    panel.on_track("Song A", "Performer")
    panel.set_upcoming(["Song A — Performer", "Song B"])
    panel.on_track("Song A", "Performer")  # next poll tick, same song
    panel.on_track("Song A", "Performer")
    assert panel.songs() == ["Song A — Performer", "Song B"]


def test_identical_scrape_is_noop(qapp, monkeypatch):
    panel = QueuePanel()
    panel.on_track("Song A")
    panel.set_upcoming(["Song A", "Song B"])
    clears = []
    monkeypatch.setattr(panel.list, "clear", lambda: clears.append(1))
    panel.set_upcoming(["Song A", "Song B"])  # unchanged scrape: no rebuild
    assert clears == []
    assert panel.songs() == ["Song A", "Song B"]


def test_highlight_follows_current_after_scrape(qapp):
    from PySide6.QtGui import QFont

    panel = QueuePanel()
    panel.on_track("Song B")
    panel.set_upcoming(["Song A", "Song B — Performer", "Song C"])
    panel.on_track("Song B")
    bold = QFont()
    bold.setBold(True)
    assert panel.list.item(1).font() == bold
    assert panel.list.item(0).font() != bold
    assert panel.list.item(2).font() != bold


def test_scrape_without_current_then_recovery_appends_once(qapp):
    panel = QueuePanel()
    panel.on_track("Played")
    panel.set_upcoming(["Next 1"])  # page queue replaced, current missing
    assert panel.songs() == ["Next 1"]
    panel.on_track("Played")  # next poll recovers the now-playing row
    assert panel.songs() == ["Next 1", "Played"]
    panel.on_track("Played")
    assert panel.songs() == ["Next 1", "Played"]


def test_queue_panel_empty_scrape_keeps_history(qapp):
    panel = QueuePanel()
    panel.on_track("Played Song")
    panel.set_upcoming([])
    panel.set_upcoming(["", "   "])
    assert panel.songs() == ["Played Song"]


def test_current_row_gets_play_icon_and_accent_styling(qapp):
    panel = QueuePanel()
    panel.on_track("Song A")
    panel.on_track("Song B")
    current = panel.list.item(1)
    other = panel.list.item(0)
    assert not current.icon().isNull()
    assert current.font().bold()
    assert current.foreground().color().name() == "#7c6af7"
    assert current.background().color().name() == "#31324a"
    assert other.icon().isNull()
    assert other.font().bold() is False


def test_highlight_moves_when_the_song_changes(qapp):
    panel = QueuePanel()
    panel.on_track("Song A")
    panel.on_track("Song B")
    assert not panel.list.item(1).icon().isNull()
    panel.on_track("Song C")
    assert panel.list.item(1).icon().isNull()
    assert panel.list.item(1).font().bold() is False
    assert not panel.list.item(2).icon().isNull()
    assert panel.list.item(2).font().bold() is True


def test_scrape_keeps_the_current_row_distinct(qapp):
    panel = QueuePanel()
    panel.on_track("Song B", "Performer")
    panel.set_upcoming(["Song A", "Song B — Performer", "Song C"])
    assert panel.list.item(1).font().bold() is True
    assert not panel.list.item(1).icon().isNull()
    assert panel.list.item(0).icon().isNull()
    assert panel.list.item(2).icon().isNull()


def test_add_songs_appends_mixed_forms(qapp):
    panel = QueuePanel()
    added = panel.add_songs(
        [
            "Plain Song",
            ("Title Song", "Artist"),
            {"title": "Dict Song", "artist": "Someone"},
            {"title": "  "},
            "",
            ("", "no title"),
        ]
    )
    assert added == 3
    assert panel.songs() == ["Plain Song", "Title Song — Artist", "Dict Song — Someone"]
    assert panel.has_songs() is True
    assert panel.note.text() == ""


def test_add_songs_keeps_current_highlight(qapp):
    panel = QueuePanel()
    panel.on_track("Playing Now")
    panel.add_songs([{"title": "Queued 1", "artist": "A"}, {"title": "Queued 2", "artist": ""}])
    # the playing row stays highlighted; queued rows are plain
    assert panel.list.item(0).font().bold() is True
    assert not panel.list.item(0).icon().isNull()
    assert panel.list.item(1).font().bold() is False
    assert panel.list.item(1).icon().isNull()
    assert panel.songs() == ["Playing Now", "Queued 1 — A", "Queued 2"]


def test_clear_queue_empties_and_resets_note(qapp):
    panel = QueuePanel()
    panel.on_track("Song A")
    panel.add_songs(["Song B"])
    panel.clear_queue()
    assert panel.songs() == []
    assert panel.has_songs() is False
    assert panel.note.text() == "No songs yet — press play"
    # after a clear, a re-reported song appends fresh (no stale highlight)
    panel.on_track("Song A")
    assert panel.songs() == ["Song A"]


def test_manual_queue_blocks_scrape_but_not_auto_add(qapp):
    panel = QueuePanel()
    panel.set_manual_queue(True)
    panel.add_songs(["Queued Song"])
    # page scrape must not wipe the user-queued songs
    panel.set_upcoming(["Page Song 1", "Page Song 2"])
    assert panel.songs() == ["Queued Song"]
    # the next playing song is still added automatically
    panel.on_track("Next Playing", "Artist")
    assert panel.songs() == ["Queued Song", "Next Playing — Artist"]
    assert panel.list.item(1).font().bold() is True
    # empty scrapes are still fine
    panel.set_upcoming([])
    assert panel.songs() == ["Queued Song", "Next Playing — Artist"]


def test_manual_queue_off_restores_scrape(qapp):
    panel = QueuePanel()
    panel.set_manual_queue(True)
    panel.add_songs(["Queued"])
    panel.set_manual_queue(False)
    panel.set_upcoming(["Page Song"])
    assert panel.songs() == ["Page Song"]
    assert panel.manual_queue is False
