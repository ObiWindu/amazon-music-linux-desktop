"""Right-side queue panel: songs only.

The panel shows songs, never page titles (playlists, the browser home, etc.).
Rows come from either
* a real page-queue scrape (``set_upcoming``) — shown when the page exposes
  its up-next list, or
* actual playback events (``on_track``) — songs that played this session.

One track is *current* (``_current_key``): the song the page player last
reported. The current row is visually distinct — bold, accent-colored text,
a tinted row background and a play-triangle icon — and the highlight moves
when the song changes. Scrapes replace the list but never the current song,
and re-reporting the current song only re-highlights its row instead of
appending a duplicate. A scrape that merely repeats the same rows is a
no-op so the panel does not flicker every poll.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap, QPolygonF
from PySide6.QtWidgets import QFrame, QLabel, QListWidget, QListWidgetItem, QVBoxLayout

ACCENT = "#7c6af7"
ROW_BACKGROUND = "#31324a"


def _play_icon() -> QIcon:
    """Small filled play triangle marking the now-playing row."""
    pixmap = QPixmap(12, 12)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(ACCENT))
    painter.drawPolygon(
        QPolygonF([QPointF(2.0, 1.5), QPointF(11.0, 6.0), QPointF(2.0, 10.5)])
    )
    painter.end()
    return QIcon(pixmap)


def track_label(title: str, artist: str = "") -> str:
    """Return the single-line label for a song, or "" when not a song."""
    text = (title or "").strip()
    if not text:
        return ""
    artist = (artist or "").strip()
    return f"{text} — {artist}" if artist else text


def _row_key(text: str) -> str:
    """Match a row back to a song title (labels may carry an artist suffix)."""
    return (text or "").split("—")[0].strip()


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
        self.list.setObjectName("queueList")
        self.list.setStyleSheet("background: #1e1e2e; color: #cdd6f4; border: none;")
        self.list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        layout.addWidget(self.list, 1)
        self._current_key = ""
        self._bold = QFont()
        self._bold.setBold(True)
        self._play_icon = _play_icon()
        self._row_background = QColor(ROW_BACKGROUND)
        self._accent = QColor(ACCENT)
        self._sync_note()

    def on_track(self, title: str, artist: str = "") -> None:
        """Record the song the page player is on (called every poll tick).

        Re-reporting the current song only re-affirms its highlight; a
        *different* song appends a new row (an encore later in the session
        is a distinct row, not a duplicate).
        """
        key = (title or "").strip()
        label = track_label(title, artist)
        if not label or not key:
            return
        if key == self._current_key and self._current_row_index() is not None:
            # same song, next poll tick: re-affirm the highlight only
            self._highlight_current()
            return
        self._current_key = key
        item = QListWidgetItem(label)
        item.setToolTip(label)
        self.list.addItem(item)
        self._highlight_current()
        self.list.scrollToBottom()
        self._sync_note()

    def add_song(self, title: str, artist: str = "") -> None:
        self.on_track(title, artist)

    def _current_row_index(self) -> int | None:
        """List index of the now-playing row, or None when not displayed."""
        if not self._current_key:
            return None
        for index in range(self.list.count()):
            row = self.list.item(index)
            if _row_key(row.text()) == self._current_key:
                return index
        return None

    def _highlight_current(self) -> QListWidgetItem | None:
        """Mark the now-playing row — bold, accent-colored text, tinted row
        background and a play icon — and reset every other row. Never
        scrolls: callers decide (re-highlighting every poll tick must not
        yank the user's scroll position)."""
        current = self._current_row_index()
        target = None if current is None else self.list.item(current)
        for index in range(self.list.count()):
            row = self.list.item(index)
            if current is not None and index == current:
                row.setFont(self._bold)
                row.setForeground(self._accent)
                row.setBackground(self._row_background)
                row.setIcon(self._play_icon)
            else:
                row.setFont(QFont())
                row.setData(Qt.ItemDataRole.ForegroundRole, None)
                row.setData(Qt.ItemDataRole.BackgroundRole, None)
                row.setIcon(QIcon())
        return target

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
        """Replace the contents with the page's *real* up-next queue.

        An empty scrape keeps history. An identical scrape is a no-op
        (only the highlight is re-applied). The current song keeps its
        identity across rebuilds so the next poll tick highlights instead
        of duplicating.
        """
        rows = [str(song).strip() for song in songs if str(song).strip()]
        if not rows:
            return  # no usable scrape; keep whatever songs were tracked
        current = [self.list.item(index).text() for index in range(self.list.count())]
        if current != rows:
            self.list.clear()
            for text in rows:
                item = QListWidgetItem(text)
                item.setToolTip(text)
                self.list.addItem(item)
            target = self._highlight_current()
            if target is not None:
                self.list.scrollToItem(target)
            else:
                self.list.scrollToTop()
        else:
            self._highlight_current()
        self._sync_note()

    def songs(self) -> list[str]:
        result = []
        for row in range(self.list.count()):
            result.append(self.list.item(row).text())
        return result

    def clear_history(self) -> None:
        self.list.clear()
        self._current_key = ""
        self._sync_note()
