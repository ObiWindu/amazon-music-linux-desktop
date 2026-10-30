"""Left-side queue panel: songs only.

The panel shows songs, never page titles (playlists, the browser home, etc.).
Rows come from either
* a real page-queue scrape (``set_upcoming``) — shown when the page exposes
  its up-next list, or
* actual playback events (``on_track``) — songs that played this session.
"""
from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QLabel, QListWidget, QListWidgetItem, QVBoxLayout

ACCENT = "#7c6af7"


def track_label(title: str, artist: str = "") -> str:
    """Return the single-line label for a song, or "" when not a song."""
    text = (title or "").strip()
    if not text:
        return ""
    artist = (artist or "").strip()
    return f"{text} — {artist}" if artist else text


class QueuePanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(240)
        self.setStyleSheet("background: #181825; border-left: 1px solid #313244;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 16, 10, 16)
        header = QLabel("Queue")
        header.setStyleSheet(f"color: {ACCENT}; font-size: 16px; font-weight: bold;")
        layout.addWidget(header)
        self.note = QLabel("No songs yet — press play")
        self.note.setStyleSheet("color: #a6adc8; font-size: 11px;")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.list = QListWidget()
        self.list.setStyleSheet("background: #1e1e2e; color: #cdd6f4; border: none;")
        self.list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        layout.addWidget(self.list, 1)
        self._last_key = ""
        self._bold = QFont()
        self._bold.setBold(True)
        self._sync_note()

    def on_track(self, title: str, artist: str = "") -> None:
        """Record a song that the page actually played."""
        self.add_song(title, artist)

    def add_song(self, title: str, artist: str = "") -> None:
        key = (title or "").strip()
        label = track_label(title, artist)
        if not label or key == self._last_key:
            return
        self._last_key = key
        item = QListWidgetItem(label)
        item.setToolTip(label)
        self.list.addItem(item)
        self._highlight(item)
        self.list.scrollToBottom()
        self._sync_note()

    def _highlight(self, item: QListWidgetItem) -> None:
        """Emphasize the row that is playing, reset the rest."""
        for index in range(self.list.count()):
            row = self.list.item(index)
            row.setFont(self._bold if row is item else QFont())

    def has_songs(self) -> bool:
        return self.list.count() > 0

    def set_note(self, note: str) -> None:
        self.note.setText(note or "")
        self.note.setVisible(bool(note))

    def _sync_note(self) -> None:
        if self.has_songs():
            self.set_note("")
        else:
            self.set_note("No songs yet — press play")

    def set_upcoming(self, songs: list[str]) -> None:
        """Replace the contents with the page's *real* up-next queue."""
        rows = [str(song).strip() for song in songs if str(song).strip()]
        if not rows:
            return  # no usable scrape; keep whatever songs we tracked
        self.list.clear()
        self._last_key = ""
        for text in rows:
            item = QListWidgetItem(text)
            item.setToolTip(text)
            self.list.addItem(item)
        self.list.scrollToTop()
        self._sync_note()

    def songs(self) -> list[str]:
        result = []
        for row in range(self.list.count()):
            result.append(self.list.item(row).text())
        return result

    def clear_history(self) -> None:
        self.list.clear()
        self._last_key = ""
        self._sync_note()
