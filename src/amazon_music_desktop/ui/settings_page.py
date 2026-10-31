"""Embedded settings page."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..services.configuration import REGION_LABELS, AppConfig


class SettingsPage(QWidget):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel("Settings")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        form = QFormLayout()
        self.region_combo = QComboBox()
        for code, label in REGION_LABELS.items():
            self.region_combo.addItem(label, code)
        idx = self.region_combo.findData(config.region)
        if idx >= 0:
            self.region_combo.setCurrentIndex(idx)
        form.addRow("Region", self.region_combo)

        self.homepage_edit = QLineEdit(config.homepage_url)
        form.addRow("Homepage URL", self.homepage_edit)

        self.width_spin = QSpinBox(); self.width_spin.setRange(640, 4096); self.width_spin.setValue(config.window_width)
        self.height_spin = QSpinBox(); self.height_spin.setRange(480, 4096); self.height_spin.setValue(config.window_height)
        form.addRow("Window width", self.width_spin)
        form.addRow("Window height", self.height_spin)

        self.theme_combo = QComboBox(); self.theme_combo.addItems(["system", "light", "dark"]); self.theme_combo.setCurrentText(config.theme)
        form.addRow("Theme", self.theme_combo)

        self.tray_check = QCheckBox("Enable system tray"); self.tray_check.setChecked(config.tray_enabled)
        self.min_tray_check = QCheckBox("Minimize to tray"); self.min_tray_check.setChecked(config.minimize_to_tray)
        self.media_keys_check = QCheckBox("Enable media keys"); self.media_keys_check.setChecked(config.media_keys_enabled)
        self.dev_diag_check = QCheckBox("Developer diagnostics"); self.dev_diag_check.setChecked(config.developer_diagnostics)
        form.addRow("", self.tray_check)
        form.addRow("", self.min_tray_check)
        form.addRow("", self.media_keys_check)
        form.addRow("", self.dev_diag_check)

        # Playback diagnostics (remediation spec 5): dedicated actions wired
        # by the main window; the report itself is generated there so the
        # section reflects live monitor state.
        playback_row = QHBoxLayout()
        self.playback_run_btn = QPushButton("Run diagnostics")
        self.playback_run_btn.setToolTip("Collect playback and DRM diagnostics")
        self.playback_copy_btn = QPushButton("Copy diagnostic report")
        self.playback_copy_btn.setToolTip("Copy the redacted diagnostic report")
        self.playback_docs_btn = QPushButton("Open troubleshooting documentation")
        playback_row.addWidget(self.playback_run_btn)
        playback_row.addWidget(self.playback_copy_btn)
        playback_row.addWidget(self.playback_docs_btn)
        playback_row.addStretch()
        form.addRow("Playback diagnostics", playback_row)

        layout.addLayout(form)
        layout.addStretch()

        btns = QHBoxLayout()
        self.apply_btn = QPushButton("Apply")
        self.reset_btn = QPushButton("Reset to defaults")
        self.reset_btn.setStyleSheet("background:#555;")
        btns.addWidget(self.apply_btn)
        btns.addWidget(self.reset_btn)
        btns.addStretch()
        layout.addLayout(btns)

        self.status = QLabel("")
        layout.addWidget(self.status)

    def apply_to(self, config):
        code = self.region_combo.currentData()
        if code:
            config.region = code
        config.homepage_url = self.homepage_edit.text().strip() or config.homepage_url
        config.window_width = self.width_spin.value()
        config.window_height = self.height_spin.value()
        config.theme = self.theme_combo.currentText()
        config.tray_enabled = self.tray_check.isChecked()
        config.minimize_to_tray = self.min_tray_check.isChecked()
        config.media_keys_enabled = self.media_keys_check.isChecked()
        config.developer_diagnostics = self.dev_diag_check.isChecked()
        config.validate()

    def set_playback_actions(self, run, copy_report, open_docs) -> None:
        """Wire the playback diagnostics actions (provided by the main window)."""
        self.playback_run_btn.clicked.connect(run)
        self.playback_copy_btn.clicked.connect(copy_report)
        self.playback_docs_btn.clicked.connect(open_docs)
