"""Native player bar with animated transport controls."""
from __future__ import annotations

import math

from PySide6.QtCore import (
    Property,
    QAbstractAnimation,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSequentialAnimationGroup,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

ACCENT = QColor("#7c6af7")
IDLE = QColor("#cdd6f4")
HOVER = QColor("#313244")
PRESSED = QColor("#45475a")


def format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 60}:{total % 60:02d}"


def clamp01(value: float) -> float:
    if value <= 0:
        return 0.0
    if value >= 1:
        return 1.0
    return float(value)


def _scaled_font(size: int = 14, scale: float = 1.0):
    font = QWidget().font()
    font.setPointSize(int(size * max(0.6, min(scale, 1.25))))
    return font


class TransportButton(QAbstractButton):
    """Emoji transport button with hover fill, press 'pop' and play pulse."""

    def __init__(self, glyph: str, tooltip: str, *, toggle: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(toggle)
        self.setFixedSize(42, 42)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._glyph = glyph
        self._scale = 1.0
        self._playing = False
        self._phase = 0

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(110)
        self._pulse_timer.timeout.connect(self._advance_phase)

    def _get_scale(self) -> float:
        return self._scale

    def _set_scale(self, value: float) -> None:
        self._scale = value
        self.update()

    scale = Property(float, _get_scale, _set_scale)

    def _get_glyph(self) -> str:
        return self._glyph

    def _set_glyph(self, value: str) -> None:
        self._glyph = value
        self.update()

    glyph = Property(str, _get_glyph, _set_glyph)

    def _get_playing(self) -> bool:
        return self._playing

    playing = Property(bool, _get_playing)

    def set_playing(self, playing: bool) -> None:
        if self._playing == playing:
            return
        self._playing = playing
        if playing:
            self._pulse_timer.start()
        else:
            self._pulse_timer.stop()
            self._phase = 0
        self.update()

    def _advance_phase(self) -> None:
        self._phase = (self._phase + 1) % 24
        self.update()

    def pop(self) -> None:
        """Shrink-and-settle feedback when the button is pressed."""
        down = QPropertyAnimation(self, b"scale")
        down.setDuration(60)
        down.setStartValue(1.0)
        down.setEndValue(0.86)
        up = QPropertyAnimation(self, b"scale")
        up.setDuration(160)
        up.setStartValue(0.86)
        up.setKeyValueAt(0.35, 1.08)
        up.setEndValue(1.0)
        up.setEasingCurve(QEasingCurve.Type.OutBack)
        group = QSequentialAnimationGroup(self)
        group.addAnimation(down)
        group.addAnimation(up)
        group.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def mousePressEvent(self, event) -> None:
        self.pop()
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.0, 0.0, float(self.width()), float(self.height()))
        radius = (rect.height() / 2 - 4) * max(0.6, min(self._scale, 1.25))

        if self.isDown():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(PRESSED)
            p.drawEllipse(rect.center(), radius, radius)
        elif self.underMouse():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(HOVER)
            p.drawEllipse(rect.center(), radius, radius)

        if self.isChecked():
            halo = QColor(ACCENT)
            halo.setAlpha(70)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(halo)
            p.drawEllipse(rect.center(), radius, radius)
        elif self._playing and not self.isDown():
            pen_color = QColor(ACCENT)
            pen_color.setAlpha(int(90 + 110 * abs(math.sin(self._phase * 0.26))))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(pen_color))
            p.drawEllipse(rect.center(), radius + 3, radius + 3)

        checked = self.isChecked()
        p.setFont(_scaled_font(scale=self._scale))
        text_color = QColor(ACCENT if checked else IDLE)
        p.setPen(QPen(text_color))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._glyph)

        if checked:
            p.setPen(Qt.PenStyle.NoPen)
            p.fillRect(int(rect.width() / 2 - 9), self.height() - 5, 18, 3, ACCENT)
        p.end()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self.update()


class SeekSlider(QSlider):
    """Progress slider. Clicking jumps to that spot, dragging scrubs."""

    seek_requested = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setObjectName("seekSlider")
        self.setRange(0, 1000)
        self.setValue(0)
        self.setFixedHeight(16)
        self.setEnabled(False)

    def set_progress(self, progress: float, total_seconds: float) -> None:
        known = total_seconds > 0
        self.setEnabled(known)
        if not known or self.isSliderDown():
            return
        self.setValue(int(clamp01(progress) * self.maximum()))

    def mousePressEvent(self, event) -> None:
        if self.isEnabled() and event.button() == Qt.MouseButton.LeftButton:
            span = max(1, self.width())
            ratio = event.position().x() / span
            self.setValue(self.minimum() + int((self.maximum() - self.minimum()) * clamp01(ratio)))
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if self.isEnabled():
            self.seek_requested.emit(float(self.value()) / self.maximum())


class PlayerBar(QFrame):
    """Native transport bar: animated buttons, seek slider and volume control."""

    volume_changed = Signal(int)
    muted_changed = Signal(bool)
    seek_requested = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("playerBar")
        self.setFixedHeight(100)
        self._vol_dragging = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 6, 16, 10)
        outer.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(6)

        self.shuffle_btn = TransportButton("🔀", "Shuffle", toggle=True)
        self.prev_btn = TransportButton("⏮", "Previous track")
        self.play_btn = TransportButton("▶", "Play / Pause")
        self.next_btn = TransportButton("⏭", "Next track")
        self.repeat_btn = TransportButton("🔁", "Repeat", toggle=True)

        top.addWidget(self.shuffle_btn)
        top.addWidget(self.prev_btn)
        top.addWidget(self.play_btn)
        top.addWidget(self.next_btn)
        top.addWidget(self.repeat_btn)

        self.track_label = QLabel("Amazon Music")
        self.track_label.setObjectName("trackTitle")
        top.addWidget(self.track_label, 1)

        self.volume_btn = TransportButton("🔊", "Mute", toggle=True)
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setObjectName("volSlider")
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.setFixedWidth(110)
        top.addWidget(self.volume_btn)
        top.addWidget(self.vol_slider)

        outer.addLayout(top)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.time_cur = QLabel("0:00")
        self.time_cur.setObjectName("seekTick")
        self.time_total = QLabel("0:00")
        self.time_total.setObjectName("seekTick")
        self.seek = SeekSlider()
        bottom.addWidget(self.time_cur)
        bottom.addWidget(self.seek, 1)
        bottom.addWidget(self.time_total)
        outer.addLayout(bottom)

        for btn in (self.shuffle_btn, self.prev_btn, self.play_btn, self.next_btn, self.repeat_btn, self.volume_btn):
            btn.pressed.connect(btn.pop)
        self.play_btn.pressed.connect(self._flip_play_glyph)
        self.volume_btn.toggled.connect(self._set_muted)
        self.vol_slider.sliderPressed.connect(self._start_vol_drag)
        self.vol_slider.sliderReleased.connect(self._end_vol_drag)
        self.vol_slider.valueChanged.connect(self._maybe_emit_volume)
        self.seek.seek_requested.connect(self.seek_requested)

    def _flip_play_glyph(self) -> None:
        self.play_btn.set_playing(not self.play_btn.playing)

    def _start_vol_drag(self) -> None:
        self._vol_dragging = True

    def _end_vol_drag(self) -> None:
        self._vol_dragging = False
        self.volume_changed.emit(self.vol_slider.value())

    def _maybe_emit_volume(self, value: int) -> None:
        if self._vol_dragging:
            self.volume_changed.emit(value)

    def _set_muted(self, muted: bool) -> None:
        self.set_muted(muted)
        self.muted_changed.emit(muted)

    def set_muted(self, muted: bool) -> None:
        self.volume_btn.blockSignals(True)
        self.volume_btn.setChecked(bool(muted))
        self.volume_btn.blockSignals(False)
        self.volume_btn.glyph = "🔇" if muted else "🔊"

    def set_state(self, state: dict) -> None:
        """Mirror a parsed page-player state onto the native widgets."""
        title = state.get("title") or ""
        cur = float(state.get("cur") or 0)
        dur = float(state.get("dur") or 0)
        paused = bool(state.get("paused", True))
        volume = float(state.get("volume", self.vol_slider.value() / 100))
        muted = bool(state.get("muted", self.volume_btn.isChecked()))

        playing = not paused
        self.track_label.setText(title)
        self.play_btn.set_playing(playing)
        self.play_btn.glyph = "⏸" if playing else "▶"

        self.seek.set_progress(cur / dur if dur > 0 else 0.0, dur)
        self.time_cur.setText(format_time(cur))
        self.time_total.setText(format_time(dur) if dur > 0 else "0:00")

        if not self._vol_dragging:
            self.vol_slider.blockSignals(True)
            self.vol_slider.setValue(int(clamp01(volume) * 100))
            self.vol_slider.blockSignals(False)
        self.set_muted(muted)
