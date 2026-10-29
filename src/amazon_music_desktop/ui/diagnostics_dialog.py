"""Diagnostics dialog."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout

from ..browser.drm_diagnostics import (
    CDM_PATH,
    browser_info,
    detect_freeworld,
    find_usable_cdm,
    format_stage,
    run_stage_a,
)
from ..services.health_check import collect_health


class DiagnosticsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Diagnostics")
        self.resize(720, 520)
        layout = QVBoxLayout(self)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)
        btns = QHBoxLayout()
        run_btn = QPushButton("Run diagnostics")
        run_btn.clicked.connect(self.run)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btns.addWidget(run_btn)
        btns.addWidget(close_btn)
        layout.addLayout(btns)
        self.run()

    def run(self) -> None:
        lines = []
        lines.append("=== System ===")
        for k, v in collect_health().items():
            lines.append(f"{k}: {v}")
        lines.append("")
        lines.append("=== Browser ===")
        for k, v in browser_info().items():
            lines.append(f"{k}: {v}")
        lines.append("")
        lines.append("=== Widevine Stage A ===")
        lines.append(format_stage(run_stage_a()))
        lines.append("")
        lines.append(f"CDM path: {CDM_PATH}")
        lines.append(f"CDM in use: {find_usable_cdm()}")
        freeworld = detect_freeworld()
        lines.append(f"freeworld WebEngine (proprietary codecs): {freeworld}")
        if freeworld is False:
            lines.append("  -> install qt6-qtwebengine-freeworld from RPM Fusion for DRM playback")
        self.text.setPlainText("\n".join(lines))
