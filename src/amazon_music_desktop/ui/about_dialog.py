"""About dialog."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

from .. import __version__


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Amazon Music Desktop {__version__}"))
        layout.addWidget(QLabel("A native desktop wrapper for Amazon Music."))
        layout.addWidget(QLabel("Uses Amazon's own website and authentication."))
        layout.addWidget(QLabel("Widevine DRM via Qt WebEngine / Chromium."))
