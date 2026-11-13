"""Native player bar: bottom-docked transport with a live time bar."""
from __future__ import annotations

import math
import time

from PySide6.QtCore import (
    Property,
    QAbstractAnimation,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSequentialAnimationGroup,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QVBoxLayout,
    QWidget,
)

ACCENT = QColor("#7c6af7")
ACCENT_LIGHT = QColor("#c4b5fd")
ACCENT_DIM = QColor("#3b3363")
IDLE = QColor("#e8e4ff")
HOVER = QColor("#2e2847")
PRESSED = QColor("#3b3363")

# Emoji glyphs are kept as stable identifiers (tests + state logic rely on
# them) but never painted directly — colorful emoji clash with the purple
# theme. Each glyph maps to a vector icon drawn in theme colors.
_GLYPH_TO_ICON = {
    "▶": "play",
    "⏸": "pause",
    "⏮": "prev",
    "⏭": "next",
    "🔀": "shuffle",
    "🔁": "repeat",
    "🔊": "volume",
    "🔇": "mute",
}


def format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 60}:{total % 60:02d}"


def clamp01(value: float) -> float:
    if value <= 0:
        return 0.0
    if value >= 1:
        return 1.0
    return float(value)


class TransportButton(QAbstractButton):
    """Vector transport button in theme purple: hover fill, press 'pop', play pulse."""

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

    def set_glyph(self, value: str) -> None:
        self._glyph = value
        self.update()

    glyph = Property(str, _get_glyph, set_glyph)

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
        # 'pressed' (connected to pop by owners) already animates; painting
        # twice per click would stack overlapping animations.
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.0, 0.0, float(self.width()), float(self.height()))
        radius = (rect.height() / 2 - 4) * max(0.6, min(self._scale, 1.25))
        center = rect.center()

        if self.isDown():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(PRESSED)
            p.drawEllipse(center, radius, radius)
        elif self.underMouse():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(HOVER)
            p.drawEllipse(center, radius, radius)

        checked = self.isChecked()
        if checked:
            halo = QColor(ACCENT)
            halo.setAlpha(56)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(halo)
            p.drawEllipse(center, radius, radius)
            ring = QColor(ACCENT)
            ring.setAlpha(140)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(ring, 1.2))
            p.drawEllipse(center, radius - 0.6, radius - 0.6)
        elif self._playing and not self.isDown():
            pen_color = QColor(ACCENT_LIGHT)
            pen_color.setAlpha(int(90 + 110 * abs(math.sin(self._phase * 0.26))))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(pen_color, 1.4))
            p.drawEllipse(center, radius + 3, radius + 3)

        icon_color = QColor(ACCENT_LIGHT if checked else IDLE)
        if self.isDown():
            icon_color = QColor("#ffffff")
        self._draw_icon(p, _GLYPH_TO_ICON.get(self._glyph, "play"), center, self._scale, icon_color)

        if checked:
            p.setPen(Qt.PenStyle.NoPen)
            p.fillRect(int(rect.width() / 2 - 9), self.height() - 5, 18, 3, ACCENT)
        p.end()

    @staticmethod
    def _draw_icon(p: QPainter, kind: str, center, scale: float, color: QColor) -> None:
        """Paint a monochrome transport glyph in theme colors."""
        s = max(0.6, min(scale, 1.25))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        cx, cy = center.x(), center.y()
        u = 1.6 * s  # base unit

        if kind == "play":
            p.drawPolygon(
                QPolygonF(
                    [
                        QPointF(cx - 3.2 * u, cy - 4.6 * u),
                        QPointF(cx + 4.4 * u, cy),
                        QPointF(cx - 3.2 * u, cy + 4.6 * u),
                    ]
                )
            )
        elif kind == "pause":
            w = 2.4 * u
            h = 8.4 * u
            p.drawRects(
                [
                    QRectF(cx - 3.6 * u, cy - h / 2, w, h),
                    QRectF(cx + 1.2 * u, cy - h / 2, w, h),
                ]
            )
        elif kind in ("prev", "next"):
            flip = -1.0 if kind == "prev" else 1.0
            # stem bar
            bar_w = 1.8 * u
            bar_h = 8.4 * u
            bar_x = cx - 5.4 * u if kind == "prev" else cx + 3.6 * u
            p.drawRect(QRectF(bar_x, cy - bar_h / 2, bar_w, bar_h))
            p.drawPolygon(
                QPolygonF(
                    [
                        QPointF(cx - flip * 3.0 * u, cy - 4.6 * u),
                        QPointF(cx + flip * 4.6 * u, cy),
                        QPointF(cx - flip * 3.0 * u, cy + 4.6 * u),
                    ]
                )
            )
        elif kind in ("shuffle", "repeat"):
            p.setBrush(Qt.BrushStyle.NoBrush)
            pen = QPen(color, 1.7 * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            # two crossing lanes
            for y0, y1 in ((-3.2 * u, 3.2 * u), (3.2 * u, -3.2 * u)):
                p.drawLine(QPointF(cx - 5.2 * u, cy + y0), QPointF(cx - 1.0 * u, cy + y0))
                p.drawLine(QPointF(cx + 1.0 * u, cy + y1), QPointF(cx + 5.2 * u, cy + y1))
                p.drawLine(QPointF(cx - 1.0 * u, cy + y0), QPointF(cx + 1.0 * u, cy + y1))
            # arrowheads on the right
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            for dy in (-3.2 * u, 3.2 * u):
                tip = QPointF(cx + 5.2 * u, cy + dy)
                p.drawPolygon(
                    QPolygonF(
                        [
                            tip,
                            QPointF(tip.x() - 3.0 * u, tip.y() - 1.8 * u),
                            QPointF(tip.x() - 3.0 * u, tip.y() + 1.8 * u),
                        ]
                    )
                )
            if kind == "repeat":
                # small loop tick underneath to distinguish repeat from shuffle
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(color, 1.4 * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawArc(QRectF(cx - 5.2 * u, cy + 4.4 * u, 10.4 * u, 3.2 * u), 200 * 16, 140 * 16)
        else:  # volume / mute
            # speaker body
            p.drawPolygon(
                QPolygonF(
                    [
                        QPointF(cx - 5.4 * u, cy - 2.2 * u),
                        QPointF(cx - 2.4 * u, cy - 2.2 * u),
                        QPointF(cx + 0.4 * u, cy - 4.8 * u),
                        QPointF(cx + 0.4 * u, cy + 4.8 * u),
                        QPointF(cx - 2.4 * u, cy + 2.2 * u),
                        QPointF(cx - 5.4 * u, cy + 2.2 * u),
                    ]
                )
            )
            if kind == "volume":
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(color, 1.5 * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawArc(QRectF(cx - 0.5 * u, cy - 3.4 * u, 4.6 * u, 6.8 * u), -55 * 16, 110 * 16)
                p.drawArc(QRectF(cx + 0.6 * u, cy - 5.4 * u, 7.4 * u, 10.8 * u), -55 * 16, 110 * 16)
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(color, 1.7 * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                d = 3.4 * u
                p.drawLine(QPointF(cx + 2.2 * u, cy - d), QPointF(cx + 6.4 * u, cy + d))
                p.drawLine(QPointF(cx + 2.2 * u, cy + d), QPointF(cx + 6.4 * u, cy - d))

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self.update()


class ThemedSlider(QSlider):
    """Horizontal slider painted in theme purple.

    The bar paints itself instead of relying on QSS ``::sub-page``: across
    Qt styles the stylesheet fill does not reliably cover the progress side
    of the groove (it renders in the style highlight color, e.g. blue), so
    the slider draws its own groove, purple fill and handle in theme colors.
    Click/drag position is mapped through the style's groove/handle geometry
    so the jump lands where the pointer is, not where the unadjusted widget
    width says it should.
    """

    TRACK = QColor("#2e2847")
    TRACK_BORDER = QColor("#3d365e")
    FILL_DISABLED = QColor("#6a58e0")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setFixedHeight(22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pressing = False

    def _ratio_at(self, x: float) -> float:
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        style = self.style()
        groove = style.subControlRect(
            QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self
        )
        handle = style.subControlRect(
            QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self
        )
        span = max(1, groove.width() - handle.width())
        pos = x - groove.x() - handle.width() / 2
        return clamp01(pos / span)

    def _set_value_at(self, x: float) -> None:
        self.setValue(self.minimum() + int((self.maximum() - self.minimum()) * self._ratio_at(x)))

    def mousePressEvent(self, event) -> None:
        if self.isEnabled() and event.button() == Qt.MouseButton.LeftButton:
            # Block the base class so its own style-dependent change (a page
            # step on groove clicks, absolute-set on some styles) does not
            # fire a second valueChanged; the groove-accurate mapping below
            # is the single value change for the press, so clicking anywhere
            # on the bar jumps straight to the pointer.
            self.blockSignals(True)
            super().mousePressEvent(event)
            self.blockSignals(False)
            self._pressing = True
            if self.isSliderDown():
                self.sliderPressed.emit()
            else:
                self.setSliderDown(True)
            self._set_value_at(event.position().x())
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        # While scrubbing, keep every move on the same accurate mapping;
        # the base class would otherwise drift with its own geometry.
        if self.isEnabled() and self._pressing and event.buttons() & Qt.MouseButton.LeftButton:
            self._set_value_at(event.position().x())
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        # Some Qt builds never emit sliderReleased from the base release
        # handler (leaving sliderDown stuck); own the press/release pair so
        # exactly one sliderPressed/sliderReleased is emitted per click.
        pressing = self._pressing
        self._pressing = False
        self.blockSignals(True)
        super().mouseReleaseEvent(event)
        if self.isSliderDown():
            self.setSliderDown(False)
        self.blockSignals(False)
        if pressing:
            self.sliderReleased.emit()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        style = self.style()
        groove = style.subControlRect(
            QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self
        )
        handle = style.subControlRect(
            QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self
        )
        if groove.width() > 0:
            radius = groove.height() / 2
            p.setPen(QPen(self.TRACK_BORDER, 1))
            p.setBrush(self.TRACK)
            p.drawRoundedRect(groove, radius, radius)
            span = max(1, groove.width() - handle.width())
            if self.maximum() > self.minimum():
                ratio = clamp01((self.value() - self.minimum()) / (self.maximum() - self.minimum()))
            else:
                ratio = 0.0
            fill_w = handle.width() / 2 + ratio * span
            fill = QColor(ACCENT) if self.isEnabled() else self.FILL_DISABLED
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(
                QRectF(groove.x(), groove.y(), max(fill_w, radius), groove.height()), radius, radius
            )
            center = handle.center()
            r = max(5.0, groove.height() / 2 + 2.5)
            p.setPen(QPen(QColor(ACCENT), 1.2))
            p.setBrush(QColor("#ffffff") if self.underMouse() else QColor(IDLE))
            p.drawEllipse(center, r, r)
        p.end()


class SeekSlider(ThemedSlider):
    """Progress slider. Clicking jumps to that spot, dragging scrubs."""

    seek_requested = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("seekSlider")
        self.setRange(0, 1000)
        self.setValue(0)
        self.setEnabled(False)

    def set_progress(self, progress: float, total_seconds: float) -> None:
        known = total_seconds > 0
        self.setEnabled(known)
        if not known or self.isSliderDown():
            return
        self.setValue(int(clamp01(progress) * self.maximum()))

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
        self.setFixedHeight(92)
        self._vol_dragging = False
        self._vol_sent: int | None = None
        self._duration = 0.0
        # Time-bar interpolation: the page probe refreshes the position once
        # per second; between polls the bar extrapolates from the last anchor
        # while the position is actually moving (and only then).
        self._playing = False
        self._advancing = False
        self._anchor_pos = 0.0
        self._anchor_at = 0.0
        self._last_cur: float | None = None
        self._clock = QTimer(self)
        self._clock.setInterval(250)
        self._clock.timeout.connect(self._tick_position)
        self._clock.start()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 6, 16, 10)
        outer.setSpacing(2)

        # time bar: full width along the top edge of the bar
        seek_row = QHBoxLayout()
        seek_row.setSpacing(8)
        self.time_cur = QLabel("0:00")
        self.time_cur.setObjectName("seekTick")
        self.time_total = QLabel("0:00")
        self.time_total.setObjectName("seekTick")
        self.seek = SeekSlider()
        seek_row.addWidget(self.time_cur)
        seek_row.addWidget(self.seek, 1)
        seek_row.addWidget(self.time_total)
        outer.addLayout(seek_row)

        # controls row: track title left, transport centered, volume right
        controls = QHBoxLayout()
        controls.setSpacing(6)

        self.shuffle_btn = TransportButton("🔀", "Shuffle", toggle=True)
        self.prev_btn = TransportButton("⏮", "Previous track")
        self.play_btn = TransportButton("▶", "Play / Pause")
        self.next_btn = TransportButton("⏭", "Next track")
        self.repeat_btn = TransportButton("🔁", "Repeat", toggle=True)
        transport = QHBoxLayout()
        transport.setSpacing(6)
        for btn in (self.shuffle_btn, self.prev_btn, self.play_btn, self.next_btn, self.repeat_btn):
            transport.addWidget(btn)

        self.track_label = QLabel("Amazon Music")
        self.track_label.setObjectName("trackTitle")
        controls.addWidget(self.track_label, 1)
        controls.addLayout(transport)

        self.volume_btn = TransportButton("🔊", "Mute", toggle=True)
        self.vol_slider = ThemedSlider()
        self.vol_slider.setObjectName("volSlider")
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.setFixedWidth(110)
        volume_area = QWidget()
        volume_layout = QHBoxLayout(volume_area)
        volume_layout.setContentsMargins(0, 0, 0, 0)
        volume_layout.setSpacing(6)
        volume_layout.addStretch(1)
        volume_layout.addWidget(self.volume_btn)
        volume_layout.addWidget(self.vol_slider)
        controls.addWidget(volume_area, 1)

        outer.addLayout(controls)

        for btn in (self.shuffle_btn, self.prev_btn, self.play_btn, self.next_btn, self.repeat_btn, self.volume_btn):
            btn.pressed.connect(btn.pop)
        self.play_btn.pressed.connect(self._flip_play_glyph)
        self.volume_btn.toggled.connect(self._set_muted)
        self.vol_slider.sliderPressed.connect(self._start_vol_drag)
        self.vol_slider.sliderReleased.connect(self._end_vol_drag)
        self.vol_slider.valueChanged.connect(self._maybe_emit_volume)
        self.seek.seek_requested.connect(self._on_seek_requested)
        self.seek.valueChanged.connect(self._preview_scrub)

    def _flip_play_glyph(self) -> None:
        self.play_btn.set_playing(not self.play_btn.playing)

    def _start_vol_drag(self) -> None:
        self._vol_dragging = True

    def _end_vol_drag(self) -> None:
        self._vol_dragging = False
        self._emit_volume(self.vol_slider.value())

    def _maybe_emit_volume(self, value: int) -> None:
        if self._vol_dragging:
            self._emit_volume(value)

    def _emit_volume(self, value: int) -> None:
        # One page update per distinct value: a click emits exactly once, a
        # drag emits per step, and a release on an unchanged value is a no-op.
        value = int(value)
        if value != self._vol_sent:
            self._vol_sent = value
            self.volume_changed.emit(value)

    def _set_muted(self, muted: bool) -> None:
        self.set_muted(muted)
        self.muted_changed.emit(muted)

    def set_muted(self, muted: bool) -> None:
        self.volume_btn.blockSignals(True)
        self.volume_btn.setChecked(bool(muted))
        self.volume_btn.blockSignals(False)
        self.volume_btn.set_glyph("🔇" if muted else "🔊")

    def _preview_scrub(self, value: int) -> None:
        # While dragging, the bar previews the scrub target immediately;
        # the poll-driven set_state takes over again on release.
        if self._duration > 0 and self.seek.isSliderDown():
            self.time_cur.setText(format_time(float(value) / self.seek.maximum() * self._duration))

    def set_state(self, state: dict) -> None:
        """Mirror a parsed page-player state onto the native widgets.

        Toggle keys (``shuffle``/``repeat``) are tri-state: True/False sync
        the button from the page, None (page exposes nothing) leaves the
        local control untouched instead of guessing. Volume and mute are
        synced only while a track is actually loaded: with no media element
        the page reports defaults (full volume, not muted) that must never
        clobber the user's local settings.
        """
        title = state.get("title") or ""
        artist = state.get("artist") or ""
        cur = float(state.get("cur") or 0)
        dur = float(state.get("dur") or 0)
        paused = bool(state.get("paused", True))
        playing = not paused

        self._duration = dur
        self._playing = playing
        # The time bar advances between polls only on evidence that the page
        # position actually moves: a frozen currentTime (the 0:00 failure,
        # wherever it sits) is never animated into fake progress. The very
        # first sighting of a moving position (app restart mid-track) is
        # taken optimistically; every later poll must show movement.
        first_sight = self._last_cur is None
        moved = (not first_sight) and cur != self._last_cur
        self._advancing = playing and dur > 0 and cur > 0 and (moved or first_sight)
        self._last_cur = cur
        self._anchor_pos = cur
        self._anchor_at = time.monotonic()

        label = f"{title} — {artist}" if title and artist else (title or "Amazon Music")
        self.track_label.setText(label)
        self.track_label.setToolTip(label)
        self.play_btn.set_playing(playing)
        self.play_btn.set_glyph("⏸" if playing else "▶")

        for btn, key in ((self.shuffle_btn, "shuffle"), (self.repeat_btn, "repeat")):
            toggled = state.get(key, None)
            if toggled is not None:
                btn.blockSignals(True)
                btn.setChecked(bool(toggled))
                btn.blockSignals(False)

        if self.seek.isSliderDown():
            # Scrub in progress: preview owns the elapsed readout and the
            # handle; the page state catches up on release.
            self.time_total.setText(format_time(dur) if dur > 0 else "0:00")
            return
        self.seek.set_progress(cur / dur if dur > 0 else 0.0, dur)
        self.time_cur.setText(format_time(cur))
        self.time_total.setText(format_time(dur) if dur > 0 else "0:00")

        if dur > 0 and not self._vol_dragging:
            volume = float(state.get("volume", self.vol_slider.value() / 100))
            self.vol_slider.blockSignals(True)
            self.vol_slider.setValue(int(clamp01(volume) * 100))
            self.vol_slider.blockSignals(False)
            self._vol_sent = self.vol_slider.value()
            self.set_muted(bool(state.get("muted", self.volume_btn.isChecked())))

    def _on_seek_requested(self, fraction: float) -> None:
        """Anchor the time bar at the seek target immediately, then forward."""
        if self._duration > 0:
            target = clamp01(fraction) * self._duration
            self._anchor_pos = target
            self._anchor_at = time.monotonic()
            self._advancing = self._playing
            self.time_cur.setText(format_time(target))
        self.seek_requested.emit(fraction)

    def _tick_position(self) -> None:
        """Advance the time bar between polls while the position moves."""
        if not self._advancing or self.seek.isSliderDown() or self._duration <= 0:
            return
        elapsed = max(0.0, time.monotonic() - self._anchor_at)
        shown = min(self._anchor_pos + elapsed, self._duration)
        self.seek.setValue(round(shown / self._duration * self.seek.maximum()))
        self.time_cur.setText(format_time(shown))
