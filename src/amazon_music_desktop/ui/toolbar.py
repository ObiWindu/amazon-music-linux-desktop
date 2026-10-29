"""Navigation toolbar (modern)."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QProgressBar, QToolBar, QToolButton


class NavigationToolbar(QToolBar):
    def __init__(self, parent=None):
        super().__init__("Navigation", parent)
        self.setMovable(False)
        self.setIconSize(__import__("PySide6.QtCore", fromlist=["QSize"]).QSize(20, 20))

        self.back_btn = QToolButton()
        self.back_btn.setText("◀")
        self.back_btn.setToolTip("Back (Alt+Left)")

        self.forward_btn = QToolButton()
        self.forward_btn.setText("▶")
        self.forward_btn.setToolTip("Forward (Alt+Right)")

        self.reload_btn = QToolButton()
        self.reload_btn.setText("⟳")
        self.reload_btn.setToolTip("Reload (Ctrl+R)")

        self.home_btn = QToolButton()
        self.home_btn.setText("⌂")
        self.home_btn.setToolTip("Home (Ctrl+H)")

        self.stop_btn = QToolButton()
        self.stop_btn.setText("■")
        self.stop_btn.setToolTip("Stop")

        for b in (self.back_btn, self.forward_btn, self.reload_btn, self.home_btn, self.stop_btn):
            self.addWidget(b)

        self.addSeparator()

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(180)
        self.progress.setTextVisible(False)
        self.progress.setValue(0)
        self.addWidget(self.progress)

        self.addSeparator()

        self.status_label = QLabel("")
        self.addWidget(self.status_label)

    def set_progress(self, value: int) -> None:
        self.progress.setValue(value)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)
