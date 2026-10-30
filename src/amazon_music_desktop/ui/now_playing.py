"""Now Playing widget with animated visual indicator."""
from __future__ import annotations

import math

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class _Bars(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        self._phase = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(120)

    def set_active(self, active: bool) -> None:
        if active and not self._timer.isActive():
            self._timer.start()
        elif not active and self._timer.isActive():
            self._timer.stop()
        self.update()

    def _tick(self):
        self._phase = (self._phase + 1) % 20
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        bar_w = max(3, w // 8)
        gap = 4
        for i in range(5):
            if self._timer.isActive():
                h = 6 + int(10 * (0.5 + 0.5 * math.sin((self._phase + i * 2) * 0.6)))
            else:
                h = 6
            x = i * (bar_w + gap)
            y = self.height() - h
            p.fillRect(x, y, bar_w, h, QColor("#7c6af7"))
        p.end()


class NowPlayingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        self.label = QLabel("Not playing")
        self.label.setStyleSheet("color: #cdd6f4; font-size: 12px; font-weight: bold;")
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.sub = QLabel("")
        self.sub.setStyleSheet("color: #a6adc8; font-size: 11px;")
        self.sub.setWordWrap(True)
        layout.addWidget(self.sub)
        self.bars = _Bars()
        layout.addWidget(self.bars)

    def set_track(self, title: str):
        self.label.setText(title or "Not playing")

    def set_playing(self, playing: bool):
        self.bars.set_active(bool(playing))
